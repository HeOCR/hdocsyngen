# Phase 2, P8: Ghostscript re-distil on pilot v0 (2026-11-19)

**Inputs:** the plain PDFs of the 12 image-sample documents per producer from pilot v0 (Word for Mac, LibreOffice,
Chrome for Testing; open fonts; htext CC0 text, tuning and census only).

**Ghostscript:** 10.08.0 (Homebrew), unchanged through the run, with four variants:
- `default` (`pdfwrite`);
- `screen` (`-dPDFSETTINGS=/screen`);
- `nooutputfonts` (`-dNoOutputFonts`: glyphs become vector paths);
- `ps_roundtrip` (`ps2write`, then `pdfwrite`).

**How survival is checked:** with `pdfcheck.verify_chain`. A re-distil may convert colours, which breaks the colour
twin, so each output glyph is attributed by position (glyph origin, read with pdfium) to the input glyph whose block
the input's twin gives. A block survives when its characters are all found (multiset, brackets and NFKC folded, as in
`verify_pdf`).

**Not byte-reproducible:** Ghostscript writes fresh subset tags each run, even with SOURCE_DATE_EPOCH, and qpdf's
deterministic-ID rewrite does not remove them. P8 outputs are therefore tier V: stored, not regenerated.

## Results (12 documents, 1,761 body blocks per producer)

| Chain | Blocks surviving | What the text layer becomes |
|---|---|---|
| Word + default | 1,761 (100%) | intact; Type1 and TrueType, the Latin and digit subsets still without ToUnicode; logical order |
| Word + screen | 1,761 | the same |
| Word + nooutputfonts | 0 | **no text layer** on every page: all text drawn as vectors (T6 everywhere / image-only) |
| Word + ps_roundtrip | 1,132 (64%) | **broken:** on the inspected document the Hebrew comes back as **Dingbats** (✽ ✛ ❀ …). ToUnicode is lost and the codes are read through a standard encoding: a real T3 case |
| LibreOffice + default | 1,758 | intact; visual order; Type3 kept where the input had it |
| LibreOffice + screen | 1,758 | the same |
| LibreOffice + nooutputfonts | 0 | no text layer |
| LibreOffice + ps_roundtrip | 688 (39%) | partly broken: some documents keep their Hebrew whole, others lose ToUnicode (26 of 43 pages have a font without one) |
| Chrome + default | 1,756 | intact; visual order; Type3 kept |
| Chrome + screen | 1,756 | the same |
| Chrome + nooutputfonts | 0 | no text layer |
| Chrome + ps_roundtrip | **0** | **broken:** the Hebrew comes out as raw `(cid:N)` codes, every font Type3 |

**What it gives the generator:**
- **`ps_roundtrip`:** real broken-ToUnicode layers (T3). Word-origin ones read as Dingbats; Chrome-origin ones have no
  Unicode at all. These come without hand-written byte tricks.
- **`nooutputfonts`:** real vector-only pages: the T6-everywhere case.
- **`default` and `screen`:** they keep the text. They are only realistic "re-saved through Ghostscript" variants.
- The few blocks lost under `default` and `screen` (3 to 5 of 1,761) are attribution limits of the position mapping,
  not text loss.

## Reader notes (also correcting pilot v0)

- **pdfminer misplaces Hebrew glyphs in Quartz (Word for Mac) PDFs,** by up to about 200 pt. Its character order and
  fill colours are right; its positions there are not.
- **pdfium (heocr's engine) places glyphs correctly,** but its text page reorders right-to-left text and mirrors
  brackets. It sometimes gives a Type3 glyph a neighbouring object's fill colour.
- **The checks now use:**
  - pdfminer's interpreter for stream order and colours (the census's T2 signal and glyph runs; text read-back by
    colour; pages; page values);
  - pdfium for positions (twin geometry; the chain mapping).
- **Pilot v0, corrected:** with pdfium positions, LibreOffice's twin moves **19** blocks (0.3%) by more than 1 pt, not
  171. The other 152 were pdfminer position errors. Every other pilot figure is unchanged.
- **What heocr sees:**
  - **brackets:** read through pdfium, Word's look logical (pdfium's bidi undoes Word's mirrored glyph characters),
    while LibreOffice's and Chrome's look mirrored;
  - **ligatures:** pdfium decomposes them into their letters.

  The pilot report's bracket finding describes what the producers *store* (stream order, pdfminer). What a
  pdfium-based reader receives is the reverse for each producer.

— synth-gen[claude/claude-code#shay-macbook-m4]@heocr/opensource
