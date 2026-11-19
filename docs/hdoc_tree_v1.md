# `hdoc_tree.v1` and `hdoc_gold.v1` (draft, for heocr-eval's review)

The **owner is heocr-eval** (design note §8). This page describes what 0.0.1 writes, so eval can accept or change
it. Until eval signs it off, both schemas carry the suffix `-draft`.

## The source tree (`hdoc_tree.v1-draft`, `*.tree.json`)

The code is `src/hdocsyngen/tree.py`.

| Part | Content |
|---|---|
| `meta` | template, look, seed, page size and orientation, columns, base font and size, `text_sources` (`[{id, licence, source}]`, the pool entries the document used) |
| `body` | blocks in reading order: `paragraph`, `heading` (level 1–4), `table`, `page_break` |
| `paragraph` / `heading` | `id`, `runs`, `align` (`start`, `justify`, `center`, `end`; logical, so `start` is right in RTL), `num` (`{num_id, level}` or null), `notes` (`[{note_id, offset}]`), `style` (a writer hint) |
| `run` | `text` (logical order, NFC), `lang` (`he`, `en`, `num`), bold and italic, `kind` (`amount`, `date`, `percent`, `id`, `item_no`, `quantity`, `email`, `url`, `ref`, or null), `field` (`page`, `numpages`, or null; its text is a placeholder the producer replaces) |
| `table` | `rows`, `cols`, `cells` (`{r, c, rowspan, colspan, header, paragraphs}`), `ruled` (`all`, `header`, `rows`, `none`), `repeat_header`, `col_widths` |
| `notes` | `{id, kind: footnote or endnote, paragraphs}`; each note is anchored exactly once |
| `furniture` | `header` and `footer` paragraphs, the same on every page in 0.0.1 |
| `abstract_nums`, `nums` | Word's numbering model: levels `{fmt, text, start, restart}`; nums `{id, abstract, start_override}` |

**Conventions:**
- **Table columns are logical.** Column 0 is the start column: the rightmost in an RTL table, and the first `w:tc` in a
  `bidiVisual` table.
- **Lists are numbered paragraphs.** A bullet list is paragraphs whose `num` points to a bullet level; there is no
  separate list block.

## The gold (`hdoc_gold.v1-draft`, `*.gold.json`)

The code is `src/hdocsyngen/gold.py`. These are the layers the tree fixes exactly, before any producer:

| Field | Content |
|---|---|
| `reading_order` | the body block ids in order (a table is one entry) |
| `blocks` | every heading, paragraph, cell paragraph and note paragraph: `id`, `type`, `text` (logical, fields left out), `parent` (table or note id), `order` (index within its container: body, a table, a note), `level`, `label_model`, `values`, `ltr_runs` |
| `values` | `[{kind, start, end, text, core}]`: the whole run as written (₪, %, sign and parentheses included), and `core`, its number tokens as D-bench's `measures.NUM` finds them (digits and separators; for a Hebrew-month date, the day and the year). Hebrew unit words (`ש"ח`, `יח'`) are their own runs, outside the span. |
| `ltr_runs` | `[{start, end}]`: the spans of runs with `lang` `en` or `num`, adjacent ones merged, for the mixed-direction measure |
| `tables` | the cell grid, with spans, header flags, cell text (the cell's paragraphs joined by `\n`) and `paragraphs` (their ids) |
| `notes` | `{id, kind, anchor_block, anchor_offset, text}` |
| `furniture` | header and footer paragraphs: `id`, `order`, `text`, `fields` (`[{kind, offset}]`), `ltr_runs` |
| `lineage` | `tree_sha256` (of the `*.tree.json` it was computed from), the hdocsyngen version and commit |
| `label_basis` | `model`. Eval's rule: the **`producer`** basis is the scored reference, and `model` is a diagnostic. The verifier adds `label_producer` per block from the producer's own export (next PR). |

**Not yet written:** these are producer-dependent, and come with the producer stage (design note §3.3):
- pages and geometry, from the colour twin;
- `label_producer`;
- `not_rendered`;
- drawn text.

**Offsets:** every offset (`values`, `ltr_runs`, note anchors, `fields`) is into the block's stored `text`, after
field runs are removed.

**Reading order and scoring units** (eval, 2026-11-19, review of #1):
- **Cells are the scoring unit.** A cell's `text` is its paragraphs joined by `\n`. `line_fold_v1` collapses `\n` to a
  space, so line breaks inside a cell are never charged. Cells are read in `(r, c)` order, with `c` logical (start
  column first: right to left in RTL tables), and a merged cell appears once, at its top-start corner.
- **Notes** form their own sequence, and their attachment is a separate measure.
- **Columns:** in multi-column pages each column is read to the end before the next, and a block spanning the columns
  breaks the flow.
- **Furniture** is its own sequence, header before footer. A header read into the body counts as an interleaving.
- **Field runs** are left out of `text`, and their place is in `fields`. The producer stage adds the value rendered on
  each page (`page_values`). A page number's reference is the producer basis, like labels. Until then, furniture
  scoring ignores a number at a field's offset.

**Sign-off:** eval signs both schemas off (dropping `-draft`) in the PR that adds the producer layers, because the
`producer` label basis is the scored reference.
