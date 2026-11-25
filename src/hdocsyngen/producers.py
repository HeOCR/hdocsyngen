"""Producer drivers (design note §1): Word for Mac (P1), LibreOffice (P2) and local Chrome (P5).

Every call returns a record: tool, version, options, input and output sha256, seconds. Versions are read before and
after each call; a change raises `VersionChanged`, and the caller aborts and reruns the batch (lead's rule: Microsoft
AutoUpdate is not paused, so the version is recorded per document instead).

Word for Mac is sandboxed. Inputs are copied into its container folder and outputs copied back out.
"""
from __future__ import annotations

import hashlib
from contextlib import contextmanager
import os
import plistlib
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

WORD_APP = Path("/Applications/Microsoft Word.app")
WORD_WORKDIR = Path.home() / "Library/Containers/com.microsoft.Word/Data/hdocsyngen-pilot"
CHROME_APP = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")


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


@contextmanager
def _word_bridge():
    # Serialize local automation and give every call its own sandbox files.
    import fcntl

    WORD_WORKDIR.mkdir(parents=True, exist_ok=True)
    with (WORD_WORKDIR / ".automation.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        with tempfile.TemporaryDirectory(prefix=".export-", dir=WORD_WORKDIR) as scratch:
            yield Path(scratch)


def word_convert(docx: Path, out_dir: Path, outputs=("pdf", "docx", "labels"), timeout: int = 240) -> dict:
    """Use Word's local save-as PDF or DOCX and native list strings."""
    formats = {"pdf": "format PDF", "docx": "format document"}
    if set(outputs) - (formats.keys() | {"labels"}):
        raise ValueError("Unsupported Word export")
    stem = docx.stem
    out_dir.mkdir(parents=True, exist_ok=True)
    files = {}
    with _word_bridge() as bridge:
        v0, b0 = word_version(), word_bundle_version()
        # Word can already have an unrelated document with the same name.
        src = bridge / f"{bridge.name}-{stem}.docx"
        shutil.copyfile(docx, src)
        targets = {
            ext: bridge / (f"{src.stem}.word.docx" if ext == "docx" else f"{stem}.word.pdf")
            for ext in outputs if ext in formats
        }

        def filepath(path: Path) -> str:
            escaped = str(path).replace(chr(92), chr(92) * 2).replace('"', chr(92) + '"')
            return f'"{escaped}"'

        saves = []
        for ext, path in targets.items():
            saves.append(f"    save as d file name {filepath(path)} file format {formats[ext]}")
            if ext == "docx":
                renamed = f"document {filepath(Path(path.name))}"
                saves.append(f"    if exists {renamed} then set d to {renamed}")
        save_script = "\n".join(saves)
        labels = LABELS_SCRIPT if "labels" in outputs else '  set out to ""\n'
        script = f'''tell application "Microsoft Word"
  open file name {filepath(src)} without add to recent files
  set d to document {filepath(Path(src.name))}
  try
{labels}
{save_script}
  on error messageText number messageNumber
    try
      if exists d then close d saving no
    end try
    error messageText number messageNumber
  end try
  set closeStatus to "closed"
  try
    if exists d then close d saving no
  on error messageText number messageNumber
    if messageNumber is not -1708 then error messageText number messageNumber
    set closeStatus to "close_event_unsupported"
  end try
  return closeStatus & linefeed & out
end tell'''
        t0 = time.monotonic()
        close_status, _, got = _osa(script, timeout).partition("\n")
        secs = time.monotonic() - t0
        v1, b1 = word_version(), word_bundle_version()
        if (v0, b0) != (v1, b1):
            raise VersionChanged(f"Word {v0} ({b0}) -> {v1} ({b1})")
        if any(not path.is_file() for path in targets.values()):
            raise ProducerError(f"Word wrote incomplete exports for {docx.name}")
        for output in outputs:
            ext = "labels.tsv" if output == "labels" else output
            dst = out_dir / f"{stem}.word.{ext}"
            if output == "labels":
                dst.write_text(got + "\n", encoding="utf-8")
            else:
                shutil.copyfile(targets[output], dst)
            files[output] = {"path": dst.name, "sha256": _sha(dst)}
    return {"producer": "word_mac", "version": v1, "bundle_version": b1,
            "options": {"save_as": list(targets), "pdf_route": "save as PDF (Quartz)"},
            "input_sha256": _sha(docx), "outputs": files, "seconds": round(secs, 2),
            "word_close_status": close_status}


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
            _run([SOFFICE, f"-env:UserInstallation={Path(profile).as_uri()}", "--headless", "--norestore",
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


# ---------------------------------------------------------------- local Chrome (P5)

def chrome_binary() -> Path:
    env = os.environ.get("HDOCSYNGEN_CHROME")
    if env:
        return Path(env)
    if CHROME_APP.is_file():
        return CHROME_APP
    installed = shutil.which("google-chrome")
    if installed:
        return Path(installed)
    raise ProducerError("Set HDOCSYNGEN_CHROME to a local Chrome binary")


def chrome_version() -> str:
    return _run([str(chrome_binary()), "--version"], 60).stdout.strip()


def chrome_convert(html: Path, out_dir: Path, timeout: int = 120) -> dict:
    v0 = chrome_version()
    out_dir.mkdir(parents=True, exist_ok=True)
    dst = (out_dir / f"{html.stem}.chrome.pdf").resolve()
    opts = ["--headless", "--disable-gpu", "--no-first-run", "--no-default-browser-check",
            "--disable-background-networking", "--disable-component-update", "--disable-sync",
            "--host-resolver-rules=MAP * ~NOTFOUND", "--no-pdf-header-footer",
            "--run-all-compositor-stages-before-draw"]
    with tempfile.TemporaryDirectory() as scratch:
        temp = Path(scratch)
        fresh_pdf = temp / "output.pdf"
        t0 = time.monotonic()
        _run([str(chrome_binary()), *opts, f"--user-data-dir={temp / 'profile'}",
              f"--print-to-pdf={fresh_pdf}", html.resolve().as_uri()], timeout)
        secs = time.monotonic() - t0
        if not fresh_pdf.is_file():
            raise ProducerError(f"Chrome wrote no PDF for {html.name}")
        v1 = chrome_version()
        if v1 != v0:
            raise VersionChanged(f"Chrome {v0} -> {v1}")
        shutil.move(fresh_pdf, dst)
    return {"producer": "chrome", "version": v1, "options": {"flags": opts}, "input_sha256": _sha(html),
            "outputs": {"pdf": {"path": dst.name, "sha256": _sha(dst)}}, "seconds": round(secs, 2)}


# ---------------------------------------------------------------- Ghostscript re-distil (P8)

GS = shutil.which("gs") or "/opt/homebrew/bin/gs"
GS_VARIANTS = {
    "default": ["-sDEVICE=pdfwrite"],
    "screen": ["-sDEVICE=pdfwrite", "-dPDFSETTINGS=/screen"],
    "nooutputfonts": ["-sDEVICE=pdfwrite", "-dNoOutputFonts"],   # every glyph becomes a vector path: no text layer
    "ps_roundtrip": None,                                         # ps2write, then pdfwrite
}


def gs_version() -> str:
    return _run([GS, "--version"], 60).stdout.strip()


def gs_redistil(pdf: Path, out: Path, variant: str, timeout: int = 300) -> dict:
    """Re-distil a PDF through Ghostscript (design note §1, P8). SOURCE_DATE_EPOCH fixes the dates Ghostscript writes,
    so the same input and version give the same bytes (checked by the P8 runner)."""
    v0 = gs_version()
    base = ["-q", "-dNOPAUSE", "-dBATCH", "-dSAFER", "-dCompatibilityLevel=1.7"]
    env_epoch = {"SOURCE_DATE_EPOCH": "1767225600"}               # 2026-01-01, for reproducible metadata
    t0 = time.time()
    if variant == "ps_roundtrip":
        with tempfile.TemporaryDirectory() as tmp:
            ps = Path(tmp) / "x.ps"
            _run_env([GS, *base, "-sDEVICE=ps2write", f"-sOutputFile={ps}", str(pdf)], timeout, env_epoch)
            _run_env([GS, *base, "-sDEVICE=pdfwrite", f"-sOutputFile={out}", str(ps)], timeout, env_epoch)
    else:
        _run_env([GS, *base, *GS_VARIANTS[variant], f"-sOutputFile={out}", str(pdf)], timeout, env_epoch)
    secs = time.time() - t0
    v1 = gs_version()
    if v1 != v0:
        raise VersionChanged(f"Ghostscript {v0} -> {v1}")
    if not out.exists():
        raise ProducerError(f"Ghostscript wrote no PDF for {pdf.name} ({variant})")
    return {"producer": f"ghostscript_{variant}", "version": v1, "options": {"variant": variant},
            "input_sha256": _sha(pdf), "outputs": {"pdf": {"path": out.name, "sha256": _sha(out)}},
            "seconds": round(secs, 2)}


def _run_env(cmd: list[str], timeout: int, extra_env: dict[str, str]) -> subprocess.CompletedProcess:
    env = dict(os.environ, **extra_env)
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=env)
    except subprocess.TimeoutExpired as e:
        raise ProducerError(f"timeout after {timeout}s: {cmd[0]}") from e
    if r.returncode != 0:
        raise ProducerError(f"{cmd[0]} exit {r.returncode}: {r.stderr.strip()[:300]}")
    return r
