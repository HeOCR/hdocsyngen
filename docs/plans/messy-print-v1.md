# Messy print v1.1 / PS-v2 test plan

Revised 2026-11-20 after Shay's screen review. The pack has **24 A4 sheets**, four variants of each of six document families. The screen preview shows the layouts with disposable text and demonstration fonts. Wear and handwritten marks are applied by hand after printing. Every preview sheet is marked for screen review. The production pack gets fresh text, fonts, hashes and approval. Target print day is **Sunday, November 22**, once the office equipment is checked and Shay and eval approve the exact final pack.

## Build and register before printing

1. Use hdocsyngen for the logical NFC text, stable block IDs, reading order, bidi runs, merged tables and page furniture. Use a pinned Chrome producer. Record its version, font manifest, source tree and PDF byte hashes. Keep the normal source gold independent of PDF readback. Freeze columns, local font choices and pasted blocks in an eval-approved placement sidecar. No gold schema change is proposed.
2. Author fresh fictional text for the final pack and record provenance and rights. Have eval check the exact final text, including letterheads, inserted text and furniture, against reservations, dev and other held-out material, and training text and near duplicates. Exclude the preview text, real names, identifying details, partner branding and reserved works. Freeze the approved source and line hashes. Subsequent revisions need clearance again.
3. Resolve the final font families with eval before rendering. Use open fonts and check every face, alias and SHA-256 against the NQ1 exclusion list and historical training, calibration and dev manifests. Exclude **Drugulin CLM and Simple CLM** and replace any face whose use in prior HeOCR training, calibration or dev cannot be ruled out. Reserve the accepted PS-v2 families and hashes, including Latin, furniture and fallback faces. Verify that training denies them and that the final PDF embeds the intended fonts. The preview's demonstration fonts establish no final reservations.
4. Have Shay approve the layout, physical checklist and capture matrix. Register PS-v2 with eval as **TEST** before printing. Freeze the page IDs, source and licence hashes, PDF and font hashes, document and planned physical tags, capture and retake rules, model IDs, scoring and access owner. Eval stores the final PDF, references and captures in its restricted test area. Keep all PS-v2 sheets, altered copies, captures and references out of training, calibration, dev and model selection. Print only the exact PDF approved by Shay and registered by eval.

## Document design and references

Use fictional letterheads and original geometric logos, numbered footers, mixed Hebrew and English, quantities and dates. Vary density, face, alignment and local spacing. Use 7–8 pt selectively in tables and notices. Include both horizontal and vertical table merges. Preserve Hebrew RTL reading order across two-column blocks and isolate Latin and numerical runs. Keep watermarks faint. Add pasted blocks with a different width, spacing or face and record their place in reading order.

The generated pages have no drawn stamps, signatures, handwriting or highlighter. Make those working-paper marks with a pen, highlighter or an actual plain office stamp as assigned below. Eval checks reading order and geometry against the source tree and sidecar. Primary scoring covers printed semantic text. Handwriting and stamps are stress tags only. Skip their extraction, transcription, region references and separate scoring. Exclude logos, decorative watermark lettering and added marks from the printed-text reference. Register how deliberately occluded printed spans will be adjudicated and log exclusions and capture failures before scoring.

## Sheet checklist

Print one-sided at 100% on common matte A4 stock. Use normal toner except where marked toner save. Then copy, apply physical marks and capture, in that order. Copy generations are counted after the original print. Tick treatments as performed and record the affected area. Keep the page ID legible, using a removable label on the back as a backup if needed.

| Sheet | Document family | Primary generated stresses | Assigned treatments |
| --- | --- | --- | --- |
| P01 | Quote and order | merged table, mixed fonts | Copy ×2; Toner save |
| P02 | Quote and order | 7–8 pt cells, pasted text | Four-way fold; Pen notes |
| P03 | Quote and order | mixed bidi values, watermark | Held in hand; Phone shadow |
| P04 | Quote and order | dense table, 7–8 pt entries | Highlighter; Underline |
| P05 | Service log | merged table, 7–8 pt labels | Copy ×3; Staple |
| P06 | Service log | pasted correction, offset text | Coffee stain; Pen notes |
| P07 | Service log | small time labels, bilingual labels, watermark | Toner save; Cross out |
| P08 | Service log | 7–8 pt table, mixed fonts | Crumple and flatten; Held in hand |
| P09 | Circulation bulletin | two columns, pasted notice, different faces | Four-way fold |
| P10 | Circulation bulletin | two columns, small end note | Copy ×2; Highlighter |
| P11 | Circulation bulletin | two columns, offset table | Pen notes; Underline |
| P12 | Circulation bulletin | two columns, watermark, mixed bidi schedule | Phone shadow; Staple |
| P13 | Dispatch sheet | merged table, small bilingual data | Copy ×3; Toner save |
| P14 | Dispatch sheet | pasted correction, 7–8 pt entries | Crumple and flatten; Cross out |
| P15 | Dispatch sheet | watermark, mixed faces | Coffee stain; Held in hand |
| P16 | Dispatch sheet | merged table, offsets | Office stamp; Highlighter |
| P17 | Archive letter | letterhead, mixed fonts | Four-way fold; Toner save |
| P18 | Archive letter | pasted paragraph, mixed face, watermark | Staple; Pen notes |
| P19 | Archive letter | mixed bidi dates, 7–8 pt notice | Phone shadow; Underline |
| P20 | Archive letter | dense small annex, mixed fonts | Copy ×2; Crumple and flatten |
| P21 | Committee minutes | two columns, mixed face, 7–8 pt agenda | Copy ×3; Cross out |
| P22 | Committee minutes | faint watermark, pasted decision | Coffee stain |
| P23 | Committee minutes | two columns, uneven spacing | Four-way fold; Held in hand |
| P24 | Committee minutes | two columns, merged summary | Office stamp; Phone shadow |

- **Copy ×2 / ×3.** Copy the prior generation each time at 100%. Capture the assigned last generation. **Toner save.** Use the printer's economy mode and record the actual setting. Resolve copier and toner-save availability in the office. If a capability is missing, ask Shay and eval to approve the revised allocation before printing.
- **Four-way fold.** Fold twice into quarters, then unfold by hand. **Crumple and flatten.** Crumple once and flatten by hand. **Staple.** Staple a corner through a blank backing sheet and keep the corner in frame.
- **Coffee stain.** Dab a small area near text and allow it to dry. **Pen notes.** Write a short fictional remark by hand in a margin. **Underline / Cross out / Highlighter.** Mark one printed phrase with the indicated implement while keeping it readable. **Office stamp.** If a suitable generic stamp is available, put a single impression slightly across printed text while preserving legibility. Exclude names, contact details and office branding. If no suitable stamp is available, assign pen notes to P16 and P24 before registration and omit the stamp stratum.
- **Held in hand.** Hold one edge in frame with a natural bend. **Phone shadow.** Cast a recognizable phone shadow across part of the text. Keep all page borders visible in the primary camera images.

## Capture matrix

Capture the same physical sheet and copy generation for every condition. The 12 additional files use the same three sheets (P01, P09, P16), covering copied/economy print, a fold, and added ink with relatively stable framing. Keep room, light and sheet placement as close as practical for the paired captures. Use the plain Camera app's photo mode for device comparisons.

| Device | App or mode | Sheets | Files |
| --- | --- | --- | --- |
| Shay's main Pixel | Plain camera | P01–P24 | 24 |
| One older Pixel | Plain camera | P01, P09, P16 | 3 |
| iPhone | Plain camera | P01, P09, P16 | 3 |
| Main Pixel | Adobe Scan | P01, P09, P16 | 3 |
| Main Pixel | Google Drive scan | P01, P09, P16 | 3 |
| **Total** | | | **36** |

Use the installed [Google Drive Android scanner](https://support.google.com/a/users/answer/9308884?co=GENIE.Platform%3DAndroid). Shay and eval confirm approved private storage for scan-app files and their originals before capture. Record device model, app/version, filter, automatic crop, deskew, actual tags, copy generation and retake reasons. Capture each app as ordinarily used and skip manual cleanup or removal of page marks. Keep the first fully framed, correctly identified capture; log missing conditions and objective retakes without ranking takes for sharpness.

Eval scores the registered real captures once after the model set is frozen. Predeclare printed-text CER and its page aggregation. Report counts and CER by document family and recorded mess strata, with denominators and overlap. The main Pixel camera set defines the primary aggregate. Report the other captures as descriptive paired comparisons over the three matched sheets. Keep one weight per sheet in the primary score.

## Sunday checks for Shay

- Confirm printer, copier, toner-save, matte A4 and access to a plain office stamp. Confirm the checklist is practical with the office supplies at hand.
- Confirm the main and older Pixel and iPhone models, the two scanner apps on the main Pixel, and the private export destination with eval.
- Approve the screen preview's layouts and where the handwritten or stamped marks will go. Once the final text and fonts are cleared, approve the exact production PDF and wait for eval to accept the PS-v2 registration before printing.
