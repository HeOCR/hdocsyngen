"""Open-font registry and coverage (design note §5; lead's rule: a substituted face fails the document).

Only allow-listed open families are used: OFL and Apache faces, and Culmus under GPL with the font exception. The
registry scans font directories, records every file's sha256 and PostScript names, and answers two questions:
- which characters of a document a family cannot draw (the document is then built with another family, or not at
  all); and
- whether a PDF font name belongs to the requested family (the verifier's hard check).

Needs fontTools (the `fonts` extra).
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path

# Allow-list: the open families installed for the pilot (lead, 2026-11-19). Scribal (Stam) and display-only faces
# are left out; Microsoft and Office faces are never listed.
OPEN_FAMILIES = {
    "Alef": "OFL-1.1", "Assistant": "OFL-1.1", "Bellefair": "OFL-1.1", "David Libre": "OFL-1.1",
    "Frank Ruhl Libre": "OFL-1.1", "Heebo": "OFL-1.1", "Miriam Libre": "OFL-1.1", "Noto Sans Hebrew": "OFL-1.1",
    "Noto Serif Hebrew": "OFL-1.1", "Noto Rashi Hebrew": "OFL-1.1", "Rubik": "OFL-1.1",
    "David CLM": "GPL-2.0-with-font-exception", "Frank Ruehl CLM": "GPL-2.0-with-font-exception",
    "Miriam CLM": "GPL-2.0-with-font-exception", "Miriam Mono CLM": "GPL-2.0-with-font-exception",
    "Nachlieli CLM": "GPL-2.0-with-font-exception", "Hadasim CLM": "GPL-2.0-with-font-exception",
    "Simple CLM": "GPL-2.0-with-font-exception", "Shofar": "GPL-2.0-with-font-exception",
    "Keter YG": "GPL-2.0-with-font-exception", "Ellinia CLM": "GPL-2.0-with-font-exception",
    "Drugulin CLM": "GPL-2.0-with-font-exception", "Aharoni CLM": "GPL-2.0-with-font-exception",
}


@dataclass
class FontFile:
    path: str
    family: str
    subfamily: str
    postscript: str
    sha256: str
    instances: tuple[str, ...] = ()            # PostScript names of a variable font's named instances
    cmap: frozenset[int] = field(repr=False, default=frozenset())


@dataclass
class Registry:
    files: list[FontFile]

    @classmethod
    def scan(cls, dirs: list[Path]) -> "Registry":
        from fontTools.ttLib import TTFont
        files = []
        for d in dirs:
            for p in sorted(Path(d).iterdir()):
                if p.suffix.lower() not in (".otf", ".ttf"):
                    continue
                try:
                    f = TTFont(p, lazy=True, fontNumber=0)
                except Exception:
                    continue
                n = f["name"]
                fam = n.getDebugName(16) or n.getDebugName(1) or ""
                if fam not in OPEN_FAMILIES:
                    continue
                ps = n.getDebugName(6) or ""
                instances: list[str] = []
                if "fvar" in f:
                    # Producers name a variable font's instances: the instance's own PostScript name if it has one,
                    # else the variations prefix (name 25, or the PostScript name's family part) plus the style.
                    prefix = n.getDebugName(25) or ps.split("-", 1)[0]
                    for inst in f["fvar"].instances:
                        own = n.getDebugName(inst.postscriptNameID) if inst.postscriptNameID not in (0xFFFF, None) else None
                        style = (n.getDebugName(inst.subfamilyNameID) or "").replace(" ", "")
                        instances += [x for x in (own, f"{prefix}-{style}" if style else None,
                                                  f"{ps.split('-', 1)[0]}-{style}" if style else None) if x]
                files.append(FontFile(path=str(p), family=fam, subfamily=n.getDebugName(17) or n.getDebugName(2) or "",
                                      postscript=ps, instances=tuple(sorted(set(instances))),
                                      sha256=hashlib.sha256(p.read_bytes()).hexdigest(),
                                      cmap=frozenset((f.getBestCmap() or {}).keys())))
        return cls(files)

    def families(self) -> list[str]:
        return sorted({f.family for f in self.files})

    def missing(self, family: str, chars: set[str]) -> set[str]:
        """Characters no file of `family` covers (whitespace and controls are not checked)."""
        cover = frozenset().union(*[f.cmap for f in self.files if f.family == family]) if self.files else frozenset()
        return {c for c in chars if not c.isspace() and ord(c) not in cover}

    def postscript_names(self, family: str) -> set[str]:
        """The family's PostScript names, variable-font instance names included."""
        out = set()
        for f in self.files:
            if f.family == family:
                out.add(f.postscript)
                out.update(f.instances)
        return out

    def manifest(self, family: str) -> list[dict]:
        return [{"file": Path(f.path).name, "postscript": f.postscript, "sha256": f.sha256,
                 "licence": OPEN_FAMILIES[f.family]} for f in self.files if f.family == family]


def doc_chars(doc) -> set[str]:
    """Every character a writer may draw for the document, numbering labels and bullets included."""
    from .tree import iter_paragraphs
    from .numbering import model_labels
    chars = set()
    for _, p in iter_paragraphs(doc):
        for r in p.runs:
            chars |= set(r.text)
    for label in model_labels(doc).values():
        chars |= set(label)
    for a in doc.abstract_nums:
        for lv in a.levels:
            if lv.fmt == "bullet":
                chars |= set(lv.text)
    return chars


def pdf_font_ok(pdf_font_name: str, allowed_postscript: set[str]) -> bool:
    """A PDF font name (with or without the subset prefix) belongs to the allowed PostScript names."""
    base = pdf_font_name.split("+", 1)[-1]
    return base in allowed_postscript


BULLET_FALLBACKS = ["•", "–", "-"]


def fit_font(doc, registry: Registry, rng, prefer: list[str] | None = None) -> list[dict]:
    """Choose an open family that draws every character of `doc` (bullets may fall back to – or -), set it in
    `doc.meta.font`, and return its font-file manifest. Raises ValueError when no family fits."""
    fams = prefer or registry.families()
    fams = [f for f in fams if f in registry.families()]
    rng.shuffle(fams)
    bullet_levels = [lv for a in doc.abstract_nums for lv in a.levels if lv.fmt == "bullet"]
    for fam in fams:
        for lv in bullet_levels:
            lv.text = next((b for b in BULLET_FALLBACKS if not registry.missing(fam, {b})), lv.text)
        if not registry.missing(fam, doc_chars(doc)):
            doc.meta.font = fam
            return registry.manifest(fam)
    raise ValueError(f"{doc.doc_id}: no open family draws every character")
