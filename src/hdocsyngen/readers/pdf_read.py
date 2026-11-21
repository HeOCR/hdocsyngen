"""Independent page text extraction for the synthetic PDF audit."""
from __future__ import annotations

import subprocess
from pathlib import Path


def poppler_pages(pdf: Path) -> list[str]:
    """Read through pdftotext, including empty pages between form feeds."""
    result = subprocess.run(
        ["pdftotext", "-raw", "-enc", "UTF-8", str(pdf.resolve()), "-"],
        check=True, capture_output=True, encoding="utf-8", timeout=120,
    )
    return result.stdout.removesuffix("\f").split("\f")


def mupdf_pages(pdf: Path) -> list[str]:
    import pymupdf

    with pymupdf.open(pdf) as doc:
        return [page.get_text(sort=False) for page in doc]
