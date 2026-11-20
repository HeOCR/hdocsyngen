# Messy print v1 / PS-v2 test plan

Proposed 2026-11-20. The objective is to test OCR on physical pages that look like working documents, with layout irregularities and wear that are missing from freshly generated printouts. The pack has **24 A4 sheets**, four variants of each of six document families. The approval preview uses invented, disposable text and demonstration fonts. It is marked on every sheet and is for screen review only. The production test pack gets its own text, fonts, hashes and approval.

## Build and register before printing

1. Use the hdocsyngen source tree for logical NFC text, stable block IDs, reading order, mixed-direction runs, merged tables and page furniture. Print the HTML through one pinned Chrome producer. Record its version, font manifest, source tree and PDF byte hashes. Keep the normal source gold independent of PDF readback. The current HTML writer supports tables and bidi runs; the preview layers ink, two-column groups, local fonts and pasted blocks around its output. For the final pack, freeze those placements and their region roles in an eval-approved sidecar. No gold schema change is proposed.
2. Author new fictional text for the final pack, with recorded provenance and rights suitable for the project. Use no preview text, dev text, real names, identifying details, partner branding, or reserved source works. Have eval check every proposed work and the exact final text, including letterhead, inserted text and furniture, against reservations, dev and other held-out material, and training text and near duplicates. Freeze the approved source and line hashes. New revisions invalidate that clearance.
3. Resolve the final font families with eval before rendering. Use only open fonts and check every face, alias and SHA-256 against the NQ1 exclusion list and the actual historical render manifests for training, calibration and dev. **Drugulin CLM and Simple CLM are always excluded from PS-v2**, even under an eval render flag. Replace any proposed PS-v2 face whose use in prior HeOCR training, calibration or dev cannot be ruled out. Reserve all approved PS-v2 families and hashes across the production and training registries, including faces for Latin runs, annotations, furniture and fallbacks. Make training deny their use, verify the deny checks before launch, and inspect the final PDF's embedded fonts for substitution. The preview's demonstration fonts establish no final reservation.
4. After Shay approves the design and capture matrix, send eval the PS-v2 **TEST** registration for acceptance before any printing. The private registration must fix the page IDs, source and licence hashes, PDF and font hashes, document and physical tags, capture and retake policy, model IDs, scoring and reference protocol, and the evaluation access owner. Eval stores the final PDF, references and captures in its restricted test area. Public documents contain the design and aggregate metadata. Print only the exact version approved by Shay and registered by eval. Keep all PS-v2 sheets, captures and references out of training, calibration, dev, prompt examples and model selection; this applies to recaptures and altered copies.

## Document design and references

Use fictional letterheads and original geometric marks, numbered footers, and mixed Hebrew, English, quantities and dates. Vary base type family, local font changes, page density and alignment. The table below fixes the primary document stresses. Record all additional observed tags in the final manifest.

- Put some translucent stamps, vector signatures and highlighter directly over text. Place short handwritten notes in the margin. Vary prominence while preserving mostly legible text. Give all lexical overlay text its own region IDs and references. Draw decorative signatures and marks without real names or copied insignia.
- Use 7–8 pt selectively in tables, notices and dense passages. Include horizontal and vertical table merges. Preserve Hebrew RTL flow across columns while isolating English and numerical runs, including dates.
- Add faint watermarks behind text. Add pasted blocks with visibly different width, alignment, line spacing and face. Keep the underlying logical order and mark real changes in block boundaries.
- Eval checks page count, logical order and geometry, including table spans and visible overlay collisions, against the tree plus the placement sidecar. Register reference policy before capture. Primary scoring covers the printed semantic text. Score legible stamp and generated handwritten text separately where supported. Exclude logos, graphical signatures, decorative watermark lettering and physical annotations from the primary text reference. Register how deliberately occluded spans are adjudicated, and log exclusions and capture failures before scoring.

## Sheet checklist

Print one-sided at 100% on the same matte A4 stock. Print all sheets with normal toner except those marked toner save. Then copy, apply physical changes, and capture, in that order. Copy generations are counted **after the original print**. At each checkpoint tick the assignment and log the actual result. The page ID stays visible in the footer. Use a removable backside label if an ID is at risk. Keep a copy of this checklist separate from the sheets.

| Sheet | Document family | Primary generated stresses | Assigned treatments |
| --- | --- | --- | --- |
| P01 | Quote and order | merged table, mixed fonts, stamp | Copy ×2; Toner save |
| P02 | Quote and order | 7–8 pt cells, highlight, paste | Four-way fold; Pen notes |
| P03 | Quote and order | mixed bidi values, signature, watermark | Held in hand; Phone shadow |
| P04 | Quote and order | dense table, handwritten margin, stamp | Scan app pair; Underline |
| P05 | Service log | merged table, signature, 7–8 pt labels | Copy ×3; Staple |
| P06 | Service log | highlighter, margin note, pasted correction | Coffee stain |
| P07 | Service log | small time stamps, bilingual labels, watermark | Toner save; Cross out |
| P08 | Service log | stamped work record, 7–8 pt table | Crumple and flatten; Held in hand |
| P09 | Circulation bulletin | two columns, pasted notice, different faces | Scan app pair; Four-way fold |
| P10 | Circulation bulletin | two columns, highlight, small end note | Copy ×2 |
| P11 | Circulation bulletin | two columns, handwritten margin, stamp | Pen notes; Underline |
| P12 | Circulation bulletin | two columns, watermark, mixed bidi schedule | Phone shadow; Staple |
| P13 | Dispatch sheet | merged table, small bilingual data, stamp | Copy ×3; Toner save |
| P14 | Dispatch sheet | signature, pasted correction, 7–8 pt entries | Crumple and flatten; Cross out |
| P15 | Dispatch sheet | watermark, margin note, highlight | Coffee stain; Held in hand |
| P16 | Dispatch sheet | merged table, offsets, stamp | Scan app pair |
| P17 | Archive letter | letterhead, stamp, signature | Four-way fold; Toner save |
| P18 | Archive letter | pasted paragraph, mixed face, watermark | Staple; Pen notes |
| P19 | Archive letter | margin note, highlight, mixed bidi dates | Phone shadow; Underline |
| P20 | Archive letter | signature, dense small annex, stamp | Copy ×2; Crumple and flatten |
| P21 | Committee minutes | two columns, mixed face, 7–8 pt agenda | Copy ×3; Cross out |
| P22 | Committee minutes | signed decision, faint watermark, paste | Coffee stain |
| P23 | Committee minutes | two columns, stamp, margin note | Four-way fold; Held in hand |
| P24 | Committee minutes | two columns, merged summary, highlight | Scan app pair; Phone shadow |

- **Copy ×2 / ×3.** Copy the prior generation each time at 100%. Capture only the assigned last generation. **Toner save.** Use the printer's economy mode and log the device setting. If neither device offers it, ask Shay and eval to approve a revised matrix before printing.
- **Four-way fold.** Fold twice across the middle, making four quarters, then unfold without ironing. **Crumple and flatten.** Crumple once and flatten by hand. **Staple.** Use one staple at a corner through a sacrificial blank backing sheet. Leave the staple in place and keep its corner in the frame.
- **Coffee stain.** Lightly dab one small area near text and allow it to dry. **Pen notes.** Use a short approved fictional phrase in one margin. **Underline.** Underline one printed phrase. **Cross out.** Draw one thin strike through a printed phrase while leaving the text readable. Log the location of each action and avoid the ID.
- **Held in hand.** Hold one edge in the frame with a natural bend and keep all page borders visible. **Phone shadow.** Let a recognizable phone shadow fall over part of the text without darkening the entire page. **Scan app pair.** Capture the same sheet in place with the plain camera and then the named scan app, logging app version and automatic crop, contrast and deskew settings. Each pair counts as one assigned treatment. Use the plain camera for the primary capture on every sheet.

## Capture and scoring

Default to one phone, steady room light and full page framing, with sheets flat unless assigned to be held. Capture one primary plain-camera image per sheet and four additional matched app captures, for **28 files**. Log sheet and capture IDs, performed tags, copy generation, paper, printer or copier, phone, app/version, mode and any retakes. Pre-register the retake rule for failures such as the wrong sheet or an out-of-frame edge. Keep the first compliant capture and log excluded files. Avoid selecting the sharpest take.

Eval scores the registered real captures once after the model set is frozen. Predeclare the primary printed-text CER, page-level aggregation and the confidence interval or minimum sample size for comparisons, plus reading order, table, and annotation metrics if their reference coverage permits. Publish counts and scores by document family and per-page mess tag as strata, with actual denominators and a record of overlap. Treat sparse strata as descriptive. Measure app-versus-camera with matched within-sheet comparisons. The extra app captures do not increase the weight of those sheets in the primary aggregate. Record unknown or missed tags distinctly. Avoid attributing an effect to one treatment from co-treated pages.

## Decisions for Shay

- Approve the six document families, 24-sheet size, and visible mess level, especially small type, overlapping ink and heavy wear. Say which should be stronger or lighter.
- Confirm the printer and copier, toner-save availability, stock and whether coffee, stapling and hand-held capture are practical.
- Pick the phone and scan app, and confirm the four matched app pairs and the proposed ordinary room lighting.
- Decide whether annotation recognition should be a scored secondary target or only a stress tag. Confirm that the clean printed text remains the main target.
