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
| F10 OPEN-SIDES | rulings without outer verticals | needs `ruled: "inner"` | PR 2 (schema) |
| F12 SNAKE | one logical table printed as side-by-side blocks | needs a `layout` field and a printed-grid → logical-table map | PR 2 (schema) |
| F14 ROTATED | a landscape section holding a table | needs per-section orientation | PR 2 (schema) |
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
- **`table.layout`**: `{"blocks": k}` prints the logical table as `k` side-by-side copies of its columns, each with the header repeated. The gold keeps the logical table, plus a `blocks` record of the block boundaries (convention a).
- **Section orientation**: `meta.sections[]` with `orientation: landscape` for a page range.
- **The form tree, `hdoc_form.v1`**: `form → section* → (field | table | group)`.
  - **`field`:** `{id, label, value, kind, slot, pages}`.
    - `id` is stable in gold; predictions don't need one.
    - `kind` is one of `text`, `number`, `date`, `checkbox`, `choice` or `signature`. A `slot` is `line`, `box` or `cell`.
    - **Label:** as printed.
    - **Value:** the whole value as printed. Multi-line values are joined with one space, and an unfilled field is `""`, never null.
    - Checkbox values are `checked` or `unchecked`. A choice value is the printed option text.
  - **`section`:** `{title?, children, pages}`. A section may nest inside another section, but doesn't have to.
  - **`group`:** `{columns}`, layout only (side-by-side sections or fields). The tree metric flattens a group into its section.
  - **Generated values** are fictional (`values.py`). Generated IDs fail the check digit.
- **Scoring:** defined in heocr-bench.
  - **Field/value F1:** fields are matched one-to-one within each form by a Hungarian assignment on label similarity, then each match is checked for exact label and value after normalisation. The scorer strips one trailing colon or dash from labels. Results are pooled per document, with a document bootstrap.
  - **Section-tree similarity:** TEDS over form → section → field-label nodes, with values excluded.
- **Generated forms are DEV and training only.** The same schema serves the real held-out gold, but generated forms are never scored as results.

## Gold conventions for 0032 (agreed with eval, 2026-11-25)

- **(a) Side-by-side blocks** with repeated headers form one logical table, read in block order with the right block first. The block boundaries are recorded as `blocks` metadata.
- **(b) A matrix's diagonal labels** sit in their printed grid cell. There is no synthetic header row.
- **(c) A section label** is its own row, and it follows the print. If the label spans the table, it is one cell with `colspan = cols`. If it sits in the first column only, its text goes in column 0 and the other cells stay empty. `sections` draws both styles.
- **(d) A margin enumerator** such as `(1)` joins the row label only when it is printed outside the grid. If it has its own printed column, that column is kept.
- **(e) A cross-page table** is one table. A repeated header is kept once, and `pages` is `[first, last]`. `page_breaks` records the logical row index at which each new page starts, for the stitch measure; it comes from `table_export.page_breaks` on a producer layer.
- **(f) Footnote markers** stay in the cell text as printed. The footnote text below the table is not part of the table.
- **(g) Empty cells** are explicit (`""`), and merged header cells follow the print.
