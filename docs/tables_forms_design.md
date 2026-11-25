# Tables and forms: generator design (draft for eval review)

Status: design plus PR 1 (2026-11-25). Owner: tables. Review: eval, for anything that touches `hdoc_tree.v1` or `hdoc_gold.v1`.

The goal is synthetic training and selection data for the tables and forms category (decision 0032), with exact structural gold. Following the no-eval-on-synthetic rule, none of it is ever used as an evaluation set.

## Coverage of the Phase 0 DEV failure taxonomy

The codes come from heocr-agent-wiki `records/tables/phase0-2026-11-25`.

| Code | What it covers | Where it lives | Status |
|---|---|---|---|
| F2 ROW-WRAP | two-line row labels; multi-sentence cells | `sections`, `wrapped` | PR 1 |
| F3 HDR-HIER | a group header spanning sub-columns; `header_rows` = 2 | `grouped_header` | PR 1 |
| F4 SECTION-ROW | a section label in column 0 with the other cells empty, an optional `(n)` enumerator, an optional trailing colon | `sections` | PR 1 |
| merged body cells | a row header spanning several rows | `row_groups` | PR 1 |
| F6 BORDERLESS | `ruled` drawn from all, header, rows or none | every variant | PR 1 |
| F8 GLYPH-GAPS | decimals, percentages and grouped amounts in many fonts | every variant | PR 1 (the fault itself comes through producers and layer faults, PR 3) |
| F11 CROSS-PAGE | 45–90 rows, header repeated in about 60% of tables | `long` | PR 1 |
| F13 MATRIX | a triangular matrix with diagonal labels and no header row | `matrix` | PR 1 |
| F13 dense | a staircase matrix of 15–22 names (detector row bands drift: two printed rows in one band) | template `tables_dense` | PR 3 |
| F10 OPEN-SIDES | rulings without outer verticals | `ruled: "inner"`, drawn by every variant | PR 2 |
| F12 SNAKE | one logical table printed as side-by-side blocks | `table.blocks` (k), `layout.printed()` and `blocks` gold metadata; `snake` variant | PR 2 |
| F14 ROTATED | a landscape section holding a table | per-section orientation | PR 2b |
| F9 / F5 / F1 layer faults | visual-order runs, split runs, hidden OCR layers, missing `.` glyphs | a PDF post-process on producer output, with the gold unchanged | PR 3 |
| scans and photos | image-only variants | hocrsyngen scanifier and 3D capture, used as libraries with the commit pinned | PR 4 |
| F15 FORM-TREE | sections, labelled fields, value slots, checkboxes, mini-tables, side-by-side sections | a `form` template plus a form-tree gold | PR 5 (schema) |

## Gold export for the scorer

`hdocsyngen.table_export` writes each gold table as `heocr_table.v1`, the format heocr-bench's table scorers read.
- The mapping is exact: logical columns, spans, and cell text with paragraphs joined by `\n`.
- `header_rows` is the number of leading rows made entirely of header cells.
- `pages` is filled once a producer layer gives the table's pages.

## Schema additions (approved by eval, 2026-11-25; code in PR 2 and PR 5)

- **`table.ruled`** gains `"inner"`: rulings between cells, with no outer border.
- **`table.blocks`** (k, default 1) prints the logical table as `k` side-by-side copies of its columns, each with the header repeated. Body rows are cut into runs of `ceil(body_rows / k)`, and block 0 is the start (rightmost) block. The gold keeps the logical table, plus a `blocks` record: `{k, header_rows, rows_per_block, ranges}`, where `ranges` are logical body-row ranges (convention a). Writers and the DOCX verifier share `layout.printed()`. Side-by-side tables need leading header rows and no body row spans. (This is the approved `layout: {"blocks": k}`, flattened to one field.)
- **Section orientation**: `meta.sections[]` with `orientation: landscape` for a page range.
- **The form tree, `hdoc_form.v1`**: `form → section* → (field | table | group)`.
  - **`field`:** `{id, label, value, kind, slot, pages}`.
    - `id` is stable in gold; predictions don't need one.
    - `kind` is one of `text`, `number`, `date`, `checkbox`, `choice` or `signature`. A `slot` is `line`, `box` or `cell`.
    - **Label:** as printed.
    - **Value:** the whole value as printed. Multi-line values are joined with one space, and an unfilled field is `""`, never null.
    - Checkbox values are `checked` or `unchecked`. A choice value is the printed option text.
  - **`section`:** `{title?, children, pages}`. A section may nest inside another section, but doesn't have to.
  - **`group`:** `{columns, children}`, layout only (side-by-side sections or fields): `columns` is the number of columns, and `children` lists column 0 (the right one) top to bottom, then the next column, as heocr-bench `docs/forms.md` has it. The tree metric flattens a group into its section.
  - **Generated values** are fictional (`values.py`). Generated IDs fail the check digit.
- **Scoring:** defined in heocr-bench.
  - **Field/value F1:** fields are matched one-to-one within each form by a Hungarian assignment on label similarity, then each match is checked for exact label and value after normalisation. The scorer strips one trailing colon or dash from labels. Results are pooled per document, with a document bootstrap.
  - **Section-tree similarity:** TEDS over form → section → field-label nodes, with values excluded.
- **Implementation (PR 5):** the `forms` template (`templates/forms.py`) draws a form with ordinary blocks: headings for section titles, paragraphs for line fields, check marks and choices, and tables for box and cell fields and for item tables inside a form. The structure goes in `Document.forms` (tree) and `gold["forms"]`, where each field names the paragraphs that print it. `form_export.export(gold, producer_gold=None)` writes `hdoc_form.v1`, with pages taken from a producer layer.
  - **Check marks** are "[X]"/"[ ]" or "(X)"/"( )": none of the open Hebrew families draws ☐/☒, and `fit_font` needs one family for every character.
  - **Values** are only fictional: the standard sample names of Israeli forms, "לדוגמה" places, `values.py` IDs, dates, amounts and example.com addresses. There are no phone numbers.
- **Generated forms are DEV and training only.** The same schema serves the real held-out gold, but generated forms are never scored as results.

## Gold conventions for 0032 (agreed with eval, 2026-11-25)

- **(a) Side-by-side blocks** with repeated headers form one logical table, read in block order with the right block first. The block boundaries are recorded as `blocks` metadata.
- **(b) A matrix's diagonal labels** sit in their printed grid cell. There is no synthetic header row.
- **(c) A section label** is its own row, and it follows the print. If the label spans the table, it is one cell with `colspan = cols`. If it sits in the first column only, its text goes in column 0 and the other cells stay empty. `sections` draws both styles.
- **(d) A margin enumerator** such as `(1)` joins the row label only when it is printed outside the grid. If it has its own printed column, that column is kept.
- **(e) A cross-page table** is one table. A repeated header is kept once, and `pages` is `[first, last]`. `page_breaks` records the logical row index at which each new page starts, for the stitch measure; it comes from `table_export.page_breaks` on a producer layer.
- **(f) Footnote markers** stay in the cell text as printed. The footnote text below the table is not part of the table.
- **(g) Empty cells** are explicit (`""`), and merged header cells follow the print.

## Layer faults (PR 3): `hdocsyngen.layer_faults`

A post-process on producer PDFs. The page looks the same and the gold stays unchanged; only the text layer changes.

- **How:** the producer's text is turned into outlines (Ghostscript `-dNoOutputFonts`). For `hidden_ocr` the page is rasterised instead. An invisible text layer (render mode 3) is then written over it from the producer's own characters, positions and order, with the faults applied. The layer font must be an open family and never a held-out one; this is checked.
- **Faults:**
  - `visual_order` (F9): each Hebrew word's letters sit at mirrored positions, so a reader gets the word backwards.
  - `split_runs` (F5): about 30% of the words get a gap inside them, so readers break them.
  - `drop_dots`: a decimal point between digits is drawn but missing from the layer.
  - `hidden_ocr` (F1): an image-only page with an invisible layer up to 1.5 pt off.
- **Record:** `OUT.faults.json` holds the faults, seed, font and per-page counts.
- **Check:** `layer_faults.check(original, faulted)` reports, per page, the share of visibly changed pixels and the characters the layer lost or gained.
- **Known limit:** a rebuild with no faults reads the same as the producer's page, except around brackets that RTL text mirrors (`(1)`). There pdfium orders the rebuilt runs differently. heocr's bracket repair covers that case.
- **Dense staircases:** the `tables_dense` template (`hdocsyngen build --template tables_dense`) makes born-digital pages of 15–22-name triangular matrices, so a fix for them can be selected on TRAIN. Each matrix draws a top style (the first name with its own row, or only its diagonal label), an optional header over the name column, whole or half-step values, and no rulings or row rulings.
- **Use:**
  - CLI: `python -m hdocsyngen.layer_faults IN.pdf OUT.pdf --font FONT --faults visual_order,split_runs --seed S`.
  - Install with the `faults` extra, plus Ghostscript.
  - TRAIN pages made with it go through heocr-clean as usual.
