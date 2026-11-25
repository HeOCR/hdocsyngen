# Native producer pilot

Run a directory of screened `hdoc_tree.v1` files through Word for Mac, LibreOffice and local Chrome. Each input tree must have single-column body paragraphs or headings. A `PageBreak` starts each later page. The audit handles producer-specific wrapping within each page. Use the table and form checks for structural gold.

```sh
python -m pip install -e ".[pdf,fonts,readback]"
hdocsyngen native-pilot --trees path/to/trees --font-dir path/to/open/fonts --out out/native
```

Install Poppler’s `pdftotext` on the run host and allow local AppleScript automation of Word. LibreOffice uses a disposable profile. The Chrome driver uses the installed app or the local binary specified in `HDOCSYNGEN_CHROME`. Chrome loads the exact declared fonts as local data URLs and writes its PDF from the RTL HTML. Word uses the local Quartz export. Each producer verifies its version around export, and the pilot pins versions across the whole batch. Word’s app build is also recorded.

The caller supplies the screened trees and open font files. The audit checks the held-out font registry, each declared file hash and its PostScript face. The output directory contains producer PDFs, the literal page records and a manifest binding each PDF, page record and tree by SHA-256. A failed slot has a failure reason in the manifest and the command exits nonzero.

## Literal page check

1. PDFium groups glyphs by baseline, sorts each row by physical position and compares it with the corresponding source block in visual order. The ground truth has logical text, its source block ID and the PDF line bounding box. Whitespace is ignored in the literal comparison.
2. The only recoverable transitions are `(` ↔ `)`, `[` ↔ `]` and `“` ↔ `”`. Each changed slot requires a unique painted MuPDF glyph at the same origin within 0.45 pt, with a positive glyph ID, the same declared PostScript face and a mapped codepoint in that font file. The page record includes the witnessed transitions.
3. PDFMiner, Poppler and the MuPDF painted trace check the glyph inventory of each page. Their sequence classifications record logical, visual or differing stream order. MuPDF supplies the glyph witness independently of ActualText. PDFMiner can use ActualText for its secondary readback.

Some Word builds return AppleScript error `-1708` when closing an exported document. The driver records `close_event_unsupported` in that case. The completed PDF still goes through the full literal audit. The bridge’s temporary files are cleaned up and Word may retain a document window until the application closes it.

The generated source trees, PDFs and page records are local artifacts. The pilot summary records aggregate counts and provenance pins.

## Pilot result

The [readback receipt](native_pilot_audit.json) covers 48 newly authored trees. Each producer verified all 48 PDFs, covering 93 pages and 1,023 lines per producer. The complete run replayed 144 PDFs, 279 pages and 3,069 lines. It recorded 837 punctuation changes with a painted glyph witness for each change.

The local protected-text check found zero matches across 936 distinct rendered lines and page units. The source pool was screened before tree generation. This pilot used Alef and David Libre and ran on the Mac at $0. The exact PDFs and page GT are retained for review under the local manifest pinned in the receipt.

## Modern page layout

Pass `--layout-plan layout.json` to verify one structured page per tree. The JSON object maps each tree ID to the first left-column body block ID for a two-column page, or `null` for a single-column page. Word and LibreOffice use native DOCX columns. Chrome uses an explicit RTL CSS column grid. The body supports literal numbered lists and letterhead styles. The verifier also checks one running head, one footer with a PAGE field, and one short footnote.

The verifier assigns PDFium glyphs to the declared physical regions and checks every line against the corresponding logical block. Its order is header, right column, left column, footnote, footer. Raised footnote numbers are joined to their visible baseline. Numeric fields are checked against the actual page number. The amendment-3-style rules still apply to each eligible punctuation transition.

`layout_record.image_record` exports the verified page in the `heocr_document.v1` contract. The ordered blocks carry region and line boxes in top-left points at the actual image DPI. Each line also carries its projected pixel polygon. The clean view uses native PDF coordinates. A Scanifier or 3D caller supplies the polygons from its warp or mesh projection. The image, native PDF, and exact logical text are bound in the pilot intake inventory. The contract can support layout and reading-order calibration and the separate TRAIN intake.
