"""Print to image and back (P9), and OCR'd layers (P10). Design note §1.

- `rasterise(pdf, out, dpi, jpeg_quality, grain, seed)`: every page rendered by pypdfium2 at `dpi`, optionally with
  seeded paper grain and mottle (the T4/T5 hazard: a grainy page at low JPEG quality), JPEG-encoded, and wrapped
  losslessly with img2pdf. The result is image-only (T5).
- `ocr_layer(pdf, out, lang)`: ocrmypdf over an image-only PDF. `heb` gives a correct OCR sandwich layer (T1,
  `text_layer_is_ocr`, keep); `eng` gives a real garbage layer (T4, replace).

img2pdf and ocrmypdf run as pinned command-line tools from their own environment (HDOCSYNGEN_TOOLS_BIN).
"""
from __future__ import annotations

import hashlib
import io
import os
import random
import subprocess
import tempfile
import time
from pathlib import Path


def _bin(name: str) -> str:
    d = os.environ.get("HDOCSYNGEN_TOOLS_BIN")
    return str(Path(d) / name) if d else name


def _version(name: str) -> str:
    r = subprocess.run([_bin(name), "--version"], capture_output=True, text=True, timeout=60)
    return (r.stdout or r.stderr).strip().splitlines()[0] if (r.stdout or r.stderr) else "?"


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _grain(img, rng: random.Random, strength: float):
    """Paper grain (per-pixel noise) and mottle (low-frequency blotches), on the paper only; ink is left dark."""
    import numpy as np
    from PIL import Image
    a = np.asarray(img.convert("L"), dtype=np.float32)
    g = np.random.default_rng(rng.randrange(1 << 32))
    paper = a > 200
    noise = g.normal(0, 7 * strength, a.shape)
    small = Image.fromarray(g.normal(0, 1, (max(1, a.shape[0] // 40), max(1, a.shape[1] // 40))).astype(np.float32))
    mottle = np.asarray(small.resize((a.shape[1], a.shape[0]), Image.BICUBIC), dtype=np.float32) * 10 * strength
    tone = 236 + g.uniform(-6, 4)
    out = np.where(paper, tone + noise + mottle, a + noise * 0.3)
    return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8), "L")


def rasterise(pdf: Path, out: Path, dpi: int = 200, jpeg_quality: int = 85, grain: float = 0.0,
              seed: int = 0, keep_pages: Path | None = None) -> dict:
    """Image-only PDF. With `keep_pages`, the page JPEGs are also kept there (input for `ocr_layer`)."""
    import pypdfium2 as pdfium
    rng = random.Random(seed)
    t0 = time.time()
    doc = pdfium.PdfDocument(str(pdf))
    with tempfile.TemporaryDirectory() as tmp:
        pages = []
        try:
            for i in range(len(doc)):
                img = doc[i].render(scale=dpi / 72).to_pil().convert("L")
                if grain > 0:
                    img = _grain(img, rng, grain)
                p = Path(tmp) / f"p{i:04d}.jpg"
                buf = io.BytesIO()
                img.save(buf, "JPEG", quality=jpeg_quality, dpi=(dpi, dpi), optimize=False)
                p.write_bytes(buf.getvalue())
                pages.append(str(p))
        finally:
            doc.close()
        subprocess.run([_bin("img2pdf"), "--output", str(out), *pages], check=True, capture_output=True, timeout=300)
        if keep_pages is not None:
            keep_pages.mkdir(parents=True, exist_ok=True)
            for p in pages:
                Path(p).replace(keep_pages / Path(p).name)
    return {"producer": "print_to_image", "tool": f"pypdfium2 + Pillow + {_version('img2pdf')}",
            "options": {"dpi": dpi, "jpeg_quality": jpeg_quality, "grain": grain, "seed": seed},
            "input_sha256": _sha(pdf), "outputs": {"pdf": {"path": out.name, "sha256": _sha(out)}},
            "seconds": round(time.time() - t0, 2)}


def ocr_layer(pages: list[Path], out: Path, lang: str = "heb", dpi: int = 200) -> dict:
    """Tesseract's own sandwich PDF over the page images (P10). `heb`: a correct OCR layer (T1, keep); `eng`: a real
    garbage layer (T4, replace). ocrmypdf needs Ghostscript, which is phase 2; Tesseract's PDF renderer is the pilot's
    OCR-layer producer."""
    t0 = time.time()
    with tempfile.TemporaryDirectory() as tmp:
        lst = Path(tmp) / "pages.txt"
        lst.write_text("\n".join(str(p) for p in pages) + "\n")
        base = Path(tmp) / "out"
        opts = ["-l", lang, "--dpi", str(dpi), "--psm", "3"]
        r = subprocess.run(["tesseract", str(lst), str(base), *opts, "pdf"], capture_output=True, text=True,
                           timeout=1800)
        if r.returncode != 0:
            raise RuntimeError(f"tesseract exit {r.returncode}: {r.stderr.strip()[:300]}")
        Path(str(base) + ".pdf").replace(out)
    v = subprocess.run(["tesseract", "--version"], capture_output=True, text=True).stdout.splitlines()[0]
    return {"producer": "tesseract_pdf", "version": v, "options": {"flags": opts},
            "input_sha256": hashlib.sha256(b"".join(p.read_bytes() for p in pages)).hexdigest(),
            "outputs": {"pdf": {"path": out.name, "sha256": _sha(out)}}, "seconds": round(time.time() - t0, 2)}
