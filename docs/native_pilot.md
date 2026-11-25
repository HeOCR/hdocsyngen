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
