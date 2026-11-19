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
| `blocks` | every heading, paragraph, cell paragraph and note paragraph: `id`, `type`, `text` (logical, fields left out), `parent` (table or note id), `level`, `label_model`, `values` (`[{kind, start, end, text}]` character spans) |
| `tables` | the cell grid, with spans, header flags and cell text (the cell's paragraphs joined by `\n`) |
| `notes` | `{id, kind, anchor_block, anchor_offset, text}` |
| `furniture` | header and footer text, with the field kinds they hold |
| `label_basis` | `model`. Eval's rule: the **`producer`** basis is the scored reference, and `model` is a diagnostic. The verifier adds `label_producer` per block from the producer's own export (next PR). |

**Not yet written:** these are producer-dependent, and come with the producer stage (design note §3.3):
- pages and geometry, from the colour twin;
- `label_producer`;
- `not_rendered`;
- drawn text.

**Reading-order conventions,** from eval's review (2026-11-19), to be confirmed here before any set is scored:
- table cells are read in row order, right to left in RTL tables;
- notes form their own sequence;
- in multi-column pages each column is read to the end before the next, and a block spanning the columns breaks the
  flow.

## Questions for eval

1. **Cell text:** is a cell's text its paragraphs joined by `\n` the right scoring unit, or should each cell paragraph
   be its own unit?
2. **Values:** should `values` spans count digits and separators only, or the whole run? The `₪` sign is part of the
   run today.
3. **Placeholder text:** for a field run (a page number), is leaving its text out of `text` right, with the furniture
   recording the field?
