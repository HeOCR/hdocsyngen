"""Producer drivers (design note §1): Word for Mac (P1), LibreOffice (P2) and Chrome for Testing (P5).

Every call returns a record: tool, version, options, input and output sha256, seconds. Versions are read before and
after each call; a change raises `VersionChanged`, and the caller aborts and reruns the batch (lead's rule: Microsoft
AutoUpdate is not paused, so the version is recorded per document instead).

Word for Mac is sandboxed. Inputs are copied into its container folder and outputs copied back out.
"""
from __future__ import annotations

import hashlib
import os
import plistlib
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

WORD_APP = Path("/Applications/Microsoft Word.app")
WORD_WORKDIR = Path.home() / "Library/Containers/com.microsoft.Word/Data/hdocsyngen-pilot"


class ProducerError(RuntimeError):
    pass


class VersionChanged(ProducerError):
    pass


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _run(cmd: list[str], timeout: int) -> subprocess.CompletedProcess:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired as e:
        raise ProducerError(f"timeout after {timeout}s: {cmd[0]}") from e
    if r.returncode != 0:
        raise ProducerError(f"{cmd[0]} exit {r.returncode}: {r.stderr.strip()[:300]}")
    return r


# ---------------------------------------------------------------- Word for Mac (P1)

def _osa(script: str, timeout: int = 120) -> str:
    return _run(["osascript", "-e", script], timeout).stdout.strip()


def word_version() -> str:
    return _osa('tell application "Microsoft Word" to get version', 60)


def word_bundle_version() -> str:
    return plistlib.loads((WORD_APP / "Contents/Info.plist").read_bytes())["CFBundleVersion"]


LABELS_SCRIPT = """
  set out to ""
  repeat with i from 1 to (count of paragraphs of d)
    set r to text object of paragraph i of d
    set ls to list string of list format of r
    if ls is missing value then set ls to ""
    set out to out & ls & tab & (content of r) & linefeed
  end repeat
"""


def word_convert(docx: Path, out_dir: Path, outputs=("pdf", "docx", "labels"), timeout: int = 240) -> dict:
    """Open `docx` in Word; save it as PDF and as a Word-written DOCX; read every paragraph's list string (the label
    Word renders) into `<stem>.word.labels.tsv`. Word's plain-text export is not used: it writes 8-bit text."""
    v0 = word_version()
    WORD_WORKDIR.mkdir(parents=True, exist_ok=True)
    stem = docx.stem
    src = WORD_WORKDIR / docx.name
    shutil.copyfile(docx, src)
    targets = {"pdf": (WORD_WORKDIR / f"{stem}.word.pdf", "format PDF"),
               "docx": (WORD_WORKDIR / f"{stem}.word.docx", "format document")}
    saves = "\n".join(f'  save as d file name "{targets[o][0]}" file format {targets[o][1]}'
                      for o in outputs if o in targets)
    labels = LABELS_SCRIPT if "labels" in outputs else '  set out to ""\n'
    t0 = time.time()
    got = _osa(f'''tell application "Microsoft Word"
  open file name "{src}"
  set d to active document
{labels}
{saves}
  close d saving no
  return out
end tell''', timeout)
    secs = time.time() - t0
    v1 = word_version()
    if v1 != v0:
        raise VersionChanged(f"Word {v0} -> {v1}")
    out_dir.mkdir(parents=True, exist_ok=True)
    files = {}
    for o in outputs:
        if o == "labels":
            dst = out_dir / f"{stem}.word.labels.tsv"
            dst.write_text(got + "\n", encoding="utf-8")
        else:
            p = targets[o][0]
            if not p.exists():
                raise ProducerError(f"Word wrote no {o} for {docx.name}")
            dst = out_dir / p.name
            shutil.move(p, dst)
        files[o] = {"path": dst.name, "sha256": _sha(dst)}
    src.unlink()
    return {"producer": "word_mac", "version": v1, "bundle_version": word_bundle_version(),
            "options": {"save_as": [o for o in outputs if o in targets], "pdf_route": "save as PDF (Quartz)"},
            "input_sha256": _sha(docx), "outputs": files, "seconds": round(secs, 2)}


# ---------------------------------------------------------------- LibreOffice (P2)

SOFFICE = shutil.which("soffice") or "/Applications/LibreOffice.app/Contents/MacOS/soffice"
LO_PDF = 'pdf:writer_pdf_Export:{"EmbedStandardFonts":{"type":"boolean","value":"true"}}'


def lo_version() -> str:
    return _run([SOFFICE, "--version"], 60).stdout.strip()


def lo_convert(docx: Path, out_dir: Path, outputs=("pdf", "docx", "txt"), timeout: int = 180) -> dict:
    v0 = lo_version()
    out_dir.mkdir(parents=True, exist_ok=True)
    filters = {"pdf": (LO_PDF, ".pdf"), "docx": ('docx:MS Word 2007 XML', ".docx"), "txt": ("txt:Text (encoded):UTF8", ".txt")}
    files, secs = {}, 0.0
    with tempfile.TemporaryDirectory() as profile, tempfile.TemporaryDirectory() as tmp:
        for o in outputs:
            flt, ext = filters[o]
            t0 = time.time()
            _run([SOFFICE, f"-env:UserInstallation=file://{profile}", "--headless", "--norestore",
                  "--convert-to", flt, "--outdir", tmp, str(docx)], timeout)
            secs += time.time() - t0
            p = Path(tmp) / f"{docx.stem}{ext}"
            if not p.exists():
                raise ProducerError(f"LibreOffice wrote no {o} for {docx.name}")
            dst = out_dir / f"{docx.stem}.lo{ext}"
            shutil.move(p, dst)
            files[o] = {"path": dst.name, "sha256": _sha(dst)}
    v1 = lo_version()
    if v1 != v0:
        raise VersionChanged(f"LibreOffice {v0} -> {v1}")
    return {"producer": "libreoffice", "version": v1, "options": {"pdf_filter": LO_PDF, "save_as": list(outputs)},
            "input_sha256": _sha(docx), "outputs": files, "seconds": round(secs, 2)}


# ---------------------------------------------------------------- Chrome for Testing (P5)

def chrome_binary() -> Path:
    env = os.environ.get("HDOCSYNGEN_CHROME")
    if not env:
        raise ProducerError("set HDOCSYNGEN_CHROME to a pinned Chrome for Testing binary")
    return Path(env)


def chrome_version() -> str:
    return _run([str(chrome_binary()), "--version"], 60).stdout.strip()


def chrome_convert(html: Path, out_dir: Path, timeout: int = 120) -> dict:
    v0 = chrome_version()
    out_dir.mkdir(parents=True, exist_ok=True)
    dst = out_dir / f"{html.stem}.chrome.pdf"
    opts = ["--headless=new", "--disable-gpu", "--no-first-run", "--no-default-browser-check",
            "--no-pdf-header-footer", "--run-all-compositor-stages-before-draw"]
    with tempfile.TemporaryDirectory() as profile:
        t0 = time.time()
        _run([str(chrome_binary()), *opts, f"--user-data-dir={profile}", f"--print-to-pdf={dst}",
              html.resolve().as_uri()], timeout)
        secs = time.time() - t0
    if not dst.exists():
        raise ProducerError(f"Chrome wrote no PDF for {html.name}")
    v1 = chrome_version()
    if v1 != v0:
        raise VersionChanged(f"Chrome {v0} -> {v1}")
    return {"producer": "chrome", "version": v1, "options": {"flags": opts}, "input_sha256": _sha(html),
            "outputs": {"pdf": {"path": dst.name, "sha256": _sha(dst)}}, "seconds": round(secs, 2)}
