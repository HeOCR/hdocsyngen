# Producers, checks and the pilot (0.0.2)

## Drivers (`producers.py`, `imagepdf.py`)

| Route | Driver | Pin | Outputs |
|---|---|---|---|
| P1 Word for Mac | AppleScript (`osascript`). The work folder is Word's container, `~/Library/Containers/com.microsoft.Word/Data/hdocsyngen-pilot/`; outputs are copied out. | `get version` before and after every call; a change raises `VersionChanged` and the run is rerun | PDF (`save as … format PDF`, Quartz), Word-written DOCX, and each paragraph's list string (`*.word.labels.tsv`) |
| P2 LibreOffice | `soffice --headless` with a fresh `-env:UserInstallation` per call | `soffice --version` before and after | PDF, LibreOffice-written DOCX, UTF-8 text |
| P5 Chrome for Testing | `--headless=new --print-to-pdf`, with a fresh profile per call. The binary is set by `HDOCSYNGEN_CHROME`. | `--version` before and after | PDF |
| P9 print to image | pypdfium2 render, optional seeded grain and mottle, JPEG, img2pdf wrap | tool versions recorded | image-only PDF (+ page JPEGs) |
| P10 OCR layer | Tesseract's own PDF renderer over the P9 page JPEGs, `heb` (a correct layer) and `eng` (a garbage layer) | `tesseract --version` | sandwich PDF |

`HDOCSYNGEN_TOOLS_BIN` points at the pinned environment that holds img2pdf.

## Checks (`verify.py`, `pdfcheck.py`, `labels.py`, `fonts.py`)

- **Fonts (hard):**
  - Every font in the plain and twin PDFs must be one of the requested open family's PostScript names. Any
    substitution fails the document.
  - Microsoft-font output falls under the lo_pdf rule and is never public.
  - Variable fonts: producers name their instances, for example `MiriamLibre-Bold` (LibreOffice) or
    `AssistantRoman-Bold` (Word). The registry adds each instance's PostScript name, or the variations prefix plus the
    style.
  - Word for Mac names a variable font's instance `PSName_Style` (for example `Rubik-Light_Bold`, a synthesised bold
    of the requested face). That counts as the requested family and is listed in `synthetic_style_fonts`.
  - `fonts.fit_font` picks an allow-listed family that draws every character, including labels and bullets. A
    bullet falls back to `–` or `-` when the face lacks `•`.
- **Geometry:**
  - Each twin glyph is matched, order-free, to the nearest plain glyph with the same page and character.
  - Shifts over 0.25 pt are recorded per block; over 1 pt the block is `geometry_ok: false`.
  - A document fails only when the glyph multiset per page differs.
- **Text read-back:** each block's characters, found by its twin colour, must match the gold's as a multiset, with
  compatibility forms folded (NFKC: a ligature such as `ﬁ` counts as `fi`, and is recorded) and each mirrored bracket
  pair as one class. Whether the producer stored the logical bracket or its mirror (the glyph
  drawn in RTL) is recorded per block (`brackets`).
- **Pixels:** a block with no pixels of its colour in the rendered twin is `not_rendered`; one with pixels per glyph
  below 25% of the document's median is `partially_rendered`.
- **DOCX:** the producer-re-saved DOCX must carry the gold. numIds are matched one to one.
- **Labels (the `producer` basis):**
  - Word's list strings and LibreOffice's text export are matched to body paragraphs in order. Trailing note marks
    (a number in Word, U+0002 in LibreOffice) are stripped.
  - LibreOffice exports every bullet as `•`, so bullets agree as a class.
- **Census (`census.v0`, per page):**
  - producer and creator;
  - fonts (subtype, ToUnicode);
  - the private-use share;
  - the final-letter T2 signal in stream order;
  - space share;
  - glyph-run lengths;
  - Type 3 fonts;
  - StructTreeRoot.

## What the smoke tests found (2026-11-19, one tender document each)

| Producer | Census | Notes |
|---|---|---|
| Word for Mac 16.115 | Quartz PDFContext; Type 1C subsets, the Latin and digit subsets **without ToUnicode**; logical stream order (T2 signal 0); about half the glyph runs single glyphs | With Word's default **tab** after list labels, Word draws the tab with Arial (a substituted face). The writer uses a space inside the label instead (suffix `nothing`). |
| LibreOffice 26.2.5.2 | Type 1 with ToUnicode; **visual stream order** for Hebrew (T2 signal 1.0) | It writes the colour twin's glyphs in a different stream order, so geometry is matched order-free. Its text export writes every bullet as `•`. |
| Chrome for Testing 158 | Skia PDF; Culmus faces as **Type 3**; visual stream order (T2 signal 1.0); a tagged structure tree | Footnotes become end notes: there are no paged-media footnotes. |
| Tesseract 5.5.3 PDF over 200 dpi JPEG 55 with grain | GlyphLessFont CID layer | The `heb` layer **reversed a date's digits** on a grainy page (the reversed-numbers effect pipeline asked for). The `eng` layer is garbage (T4). |

ocrmypdf 16.13 needs Ghostscript, which is phase 2, so the pilot uses Tesseract's PDF renderer for P10.

## Running the pilot

```bash
python -m pip install -e ".[test,fonts,pdf]"
export HDOCSYNGEN_CHROME=".../Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing"
export HDOCSYNGEN_TOOLS_BIN=".../hdocsyngen-pilot-env/.venv/bin"
hdocsyngen pilot --spec spec.json --out runs/pilot-v0
hdocsyngen pilot-summary runs/pilot-v0
```

A 2-document mini run takes about 3 minutes (about 100 s a document, with every route). The 48-document pilot is a
heavy job and goes through the power scheduler.
