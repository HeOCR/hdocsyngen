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

## The producer layers (`<doc>.<producer>.gold.json`, PR 2)

For each producer's PDF, the pilot writes the tree gold plus what that producer did (design note §3.2):

| Field | Content |
|---|---|
| `producer` | name, version, PDF file and its sha256 |
| `label_basis` | `producer` where the producer's own labels were read back (Word's list strings, LibreOffice's text export); `model` otherwise (Chrome: labels are CSS counters) |
| `blocks[].label_producer` | the label the producer rendered: **the scored reference** (eval) |
| `blocks[].pages` | the pages the block's glyphs land on, found through the colour twin |
| `blocks[].not_rendered` | true when the block has no pixels of its colour in the rendered twin (clipped or hidden). Out of the reference, and counted per chain. |
| `blocks[].twin_shift_pt` | the largest shift of the block's glyphs between the twin and the plain PDF, when over the recording bound |
| `furniture[].pages`, `furniture[].page_values` | for paragraphs with fields: `[{page, field_offset, text}]`, the value printed on each page. A field's reference is the producer basis, like labels. |
| `checks` | the bounds the set was checked to, recorded in the gold |

**The `checks` bounds:**
- **Twin geometry:** each twin glyph is matched, order-free, to the nearest plain glyph with the same page and
  character. A shift over 0.25 pt is recorded in `twin_shift_pt`; a glyph more than 3 pt from any plain glyph fails the
  document. Coordinates are compared after rounding to 0.1 pt, so 0.25 pt is the smallest bound above rounding noise.
- **Fonts:** a hard check. Every PDF font must be a PostScript name of the requested open family.
- **Labels:** compared exactly after stripping. **Bullets are a class:** any bullet glyph (`•`, `–`, `-`, `*`, `◦`,
  `▪`, `·`) equals any other, so a LibreOffice `•` against a Word `▪` is not a label disagreement. LibreOffice's text
  export writes every bullet as `•`, whatever the PDF draws.

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

**Sign-off:** eval signs both schemas off (dropping `-draft`) in this PR, once it has the producer layers and
`page_values`.
