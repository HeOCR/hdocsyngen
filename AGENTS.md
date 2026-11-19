# AGENTS.md

Static rules for agents working in this repository.

## Commands

```bash
python -m pip install -e ".[test]"
python -m pytest
```

## Rules

- The source tree is the single source of truth. Gold is computed from the tree, never from a writer's or a producer's
  output. Producer-dependent gold (pages, geometry, `producer` labels, `not_rendered`) is observed and verified.
- The gold format (`hdoc_tree.v1`, `hdoc_gold.v1`) is owned by heocr-eval. Any change needs eval's review.
- Readers in `readers/` are independent verifiers. They never import writers, and nothing here imports `heocr`.
  Code copied in spirit from `heocr` tests/synth keeps the Apache-2.0 header and says where it was derived from.
- **Text and data:**
  - Tests and examples use invented text only.
  - No real person's name, ID, phone number or address is ever generated. Generated IDs fail the Israeli check digit;
    e-mail addresses and URLs use example.com.
  - No partner or customer names, in code, docs or commits.
- **Fonts:**
  - Only open fonts go into anything public: OFL, Apache, or Culmus under GPL with the font exception.
  - Font files are never committed or shipped in datasets; manifests record their sha256.
  - Microsoft and Office fonts are local only, never public, never training.
- **Outputs:** generated documents are not committed here. Pinned sets live where heocr-eval pins them (D-bench).
- **Producers:**
  - Producer drivers record the tool version for every document.
  - A run whose producer version changes midway is aborted and rerun.
  - Heavy runs go through the power scheduler.
