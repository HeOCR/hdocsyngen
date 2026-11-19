# Pilot v0 report (2026-11-19)

The pilot of the design note (hocrsyngen `docs/document_generator_design.md` §9). It covers 48 documents, each made
by three real producers, plus print-to-image and OCR-layer routes. All figures are synthetic: they diagnose the
producers and the checks. They are not a claim about any reader (design note §7).

## What ran

- **Documents:** 48, 24 `tender` and 24 `report`.
  - Seeds 20261119 + i (tender) and 20361119 + i (report).
  - Fonts fitted from the open allow-list by coverage: 15 families, Culmus and OFL.
- **Text:** htext pool v1.1, pby-v3 il_us (CC0), 3,981 entries, sha 1ac260b5….
  - **Eval's CLEAN check finished before the run started** (clean_htext_synth_pool_v1.json). The run checks the pool's
    sha at start.
  - Scope: tuning and census only. Training needs its own CLEAN.
  - The text is Revival-era Hebrew (1910s–1950s works), not today's register.
- **Producers:** Word for Mac 16.115, LibreOffice 26.2.5.2 and Chrome for Testing 158.0.8127.36. Each version was
  identical at start and end, and every call recorded it.
- **Image and OCR routes,** on 12 documents per producer:
  - P9 at 200 and 300 dpi (JPEG 85);
  - P9 at 200 dpi with grain, JPEG 40–70;
  - P10, Tesseract 5.5.3's PDF renderer, with `heb` and `eng` over the 200-dpi pages.
- **Code:**
  - **Producers:** a frozen worktree at 5e4ecfb, before hdocsyngen#2 merged. #2's merged head (b646caa) differs from
    5e4ecfb on the pilot's producer and writer paths only in the schema string, which dropped `-draft`. The pilot's
    trees carry `hdoc_tree.v1-draft`, and v1 loads them.
  - **Checks:** re-run offline on the stored outputs with main 802668c (#2's rules as eval signed them off, plus #3's
    stream-order fix), and with this PR's two checker fixes (below). No producer was rerun for that.
- **Run:** in the power scheduler, about 80 minutes of producer time.
  - **Reruns:**
    - STOP-timeout documents: none.
    - One LibreOffice failure (report-20361126): LibreOffice's text export hangs on it. A rerun outside the scheduler
      hung again, so it is a **real producer failure**, counted apart. Its PDF and DOCX exports work.
- **Files:** outputs in `tasks/hdocsyngen-pilot/runs/pilot-v0`, which is local. The summaries are
  `pilot-v0.recheck_summary.json` and `pilot-v0.grain_ocr.json`.

## Gold checks

| | Word for Mac | LibreOffice | Chrome |
|---|---|---|---|
| documents | 48 | 47 (+1 text-export hang) | 48 |
| **gold carried** (no hard failure) | **48** | **45** | **48** |
| font substitution (hard failure) | 0 | 2: Helvetica for runs of underscores in David Libre, which has `_` | 0 |
| re-saved DOCX carries the gold | 48 / 48 | 47 / 47 | n/a |
| producer labels = model labels | 2,449 / 2,450 | 2,311, plus 125 bullets equal as a class, of 2,437 | n/a (CSS counters) |
| page numbers read back correctly (`page_values`) | 93 / 93 | 91 / 91 | 160 / 160 |
| blocks `not_rendered` / `partially_rendered` | 0 / 0 | 0 / 0 | 0 / 0 |
| blocks with twin shift over 1 pt (`geometry_ok: false`) | 0 | **171** of 5,691 | 0 |

- **The one label disagreement** (the same block in both producers) is a matcher artefact. A short bullet's text is
  also the end of an earlier line, so the matcher took the wrong line. It is a known limitation of order-based
  matching.
- **LibreOffice's twin is not a faithful layout twin** for about 3% of blocks: changing their colour moves them by
  more than 1 pt. Those blocks are marked, and their boxes from the twin are not trusted.

## Census (true content-stream order, #3)

| | Word for Mac | LibreOffice | Chrome |
|---|---|---|---|
| producer string | macOS Quartz PDFContext | LibreOffice 26.2.5.2 | Skia/PDF m158 |
| pages | 158 | 153 | 160 |
| **T2 signal ≥ 0.5 (visual stream order)** | **0** (0.0 on all 158) | **153 / 153** | **160 / 160** |
| pages with a Type 3 font | 0 | 65 | 127 |
| pages with a font lacking ToUnicode | **158** (the Latin and digit subsets) | 0 | 0 |
| font subtypes (font objects) | TrueType 1,002, Type1 289 | TrueType 150, Type1 58, Type3 80 | CIDFontType2 202, Type3 760 |
| median glyph run per page (median over pages) | 2 | 36 | 37 |
| tagged structure tree | no | no | yes |
| blocks with mirrored brackets | 50 | 0 | 57 |
| ligature characters in the text layer (e.g. U+FB01) | 121 | 117 | 124 |
| documents with a synthesised style (variable font, `PSName_Style`) | 16 | 0 | 0 |

**Text order (the lead's question): verified on every page, in true stream order.** Word for Mac writes logical order.
LibreOffice and Chrome write visual order. That is the opposite of the folklore, which blames Word.
- The real corpus's visual-order PDFs are likely Windows Word's (eval's producer families will tell).
- This pilot cannot reproduce Windows Word.
- **The Windows question is now open** (§10 #13): Word for Mac gave no visual-order layer.

## The smoke findings, checked on the full pilot

| Smoke finding | Full pilot |
|---|---|
| Word for Mac logical, LibreOffice and Chrome visual (T2) | **Verified** on all 471 pages, in true stream order |
| Chrome draws Culmus as Type 3 | **True, but too narrow.** Chrome writes Type 3 for **every variable font and every CFF (OTF) face**: all Culmus, Bellefair, and the variable Noto, Rubik, Heebo, Miriam Libre, Frank Ruhl Libre and Assistant. It uses CID TrueType only for static TTFs (Alef, David Libre). LibreOffice also writes Type 3 for variable fonts. |
| The Hebrew OCR layer reversed a date's digits on a grainy 200-dpi JPEG 55 page | **Not reproduced, and retracted.** In true stream order the Hebrew layers kept every number token (3 or more digits) as written. Clean 200-dpi pages: 664 as written, 0 reversed, 86 not found. Grain pages at JPEG 40–70: 616, 0 and 134. The smoke observation came from pdftotext's own bidi display of the layer, not from the layer. |
| Word's tab after list labels comes out in Arial | **Handled.** The writer puts a space inside the label (`suff nothing`), and no Arial appears in any Word PDF. |

## New findings

1. **Brackets are stored three different ways:**
   - **Word:** logical order, but with the *glyph's* character. In RTL, `(x)` is stored as `)x(`, so a logical reader
     sees swapped brackets.
   - **Chrome:** visual order, with the glyph's characters.
   - **LibreOffice:** visual order, with the logical characters.

   A T2 repair that reverses a line must mirror brackets for Chrome-like layers and not for LibreOffice-like ones.
   Word-like layers need mirroring without reversal.
2. **Ligatures in the text layer:** all three producers write `ﬁ`-type ligature characters for Latin runs (e-mail
   addresses and URLs). The checks fold them (NFKC) and count them.
3. **Variable fonts:**
   - Producers name instances by style, for example `MiriamLibre-Bold`, `AssistantRoman-Bold` and `Rubik-Light_Bold`.
     Word synthesises bold for some (`_Bold`).
   - Before this PR's fix, the font check failed these as substitutions. They are the requested face.
4. **LibreOffice:**
   - It draws runs of underscores in Helvetica even when the face has `_`: a real substitution, so a hard failure (2
     documents).
   - Its text export can hang (1 document).
5. **OCR layers:** Tesseract's layers are logical order (T2 0 on all 87 `heb` and 87 `eng` pages). The `eng` layers
   misread Hebrew text, as a real wrong-language layer does, while the digits come through: 744 of 750 number tokens
   are kept.

## Checker fixes in this PR (found by the pilot)

- **Brackets:** the text check compares each mirrored bracket pair as one class, and records per block whether the
  producer stored the logical bracket or its mirror.
- **NFKC:** the text check folds compatibility forms, so a ligature counts as its letters, and counts them per block.
- **Variable-font instances:**
  - the font registry adds each named instance's PostScript name, or the variations prefix (name ID 25) plus the
    style;
  - Word's `PSName_Style` names are accepted as the requested face and listed in `synthetic_style_fonts`.

Before these fixes, the pilot's gold checks failed on false grounds: Word 17 font and 29 text failures, Chrome 27 text
failures. After them, the only hard failures left are LibreOffice's 2 real Helvetica substitutions.

## Not done in the pilot

- **No reader scores.** heocr and stock Tesseract scores per chain wait for eval's `hdoc_measures_v1`, which eval
  freezes now that pilot gold exists.
- **Not covered:** Ghostscript (P8), Quartz print (P7), Typst (P6), XLSX and PPTX.
- **Partial clipping** is a flagged heuristic. No pilot block tripped it.

## Go or no-go: go, for phase 2

1. **P8 Ghostscript re-distil first** (pipeline's priority 4). It needs Ghostscript and qpdf (lead).
2. **The mixed-direction amounts case** (pipeline's priority 2) is not reproduced by any producer here. Numbers kept
   their order in every layer. The remaining candidate is Word for Windows. **The costed Windows VM proposal to Shay
   (lead's call) is triggered:** Word for Mac gave no visual-order layer.
3. **Calibration:** ask eval for the private dev aggregate table, and weight chains by producer family.
4. **Formats:** XLSX re-saved by Excel, then PPTX.

— synth-gen[claude/claude-code#shay-macbook-m4]@heocr/opensource
