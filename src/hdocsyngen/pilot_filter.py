"""Verify and apply a local, digest-only protected-text projection to TRAIN pilot units."""
from __future__ import annotations

from hashlib import sha256
from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
import re

from .numbering import model_labels
from .tree import Document, Run, Table, iter_paragraphs, text_of

_REQUIRED = {"short_whole_line", "unicode_whole_line"}
_OPTIONAL = {"normalized_whole_line", "six_word"}


def _pinned(path: Path, pin: str) -> bytes:
    raw = path.read_bytes()
    if sha256(raw).hexdigest() != pin:
        raise ValueError(f"Pilot projection pin mismatch: {path.name}")
    return raw


class PilotFilter:
    def __init__(self, manifest: Path, pin: str):
        manifest = manifest.resolve()
        config = json.loads(_pinned(manifest, pin))
        if config["schema"] != "hdocsyngen.pilot_projections.v1":
            raise ValueError("Unsupported pilot projection schema")
        layers = config["layers"]
        if not _REQUIRED <= layers.keys() <= _REQUIRED | _OPTIONAL:
            raise ValueError("Pilot projections must contain both whole-line layers")
        self.targets = {}
        for kind, layer in layers.items():
            path = (manifest.parent / layer["path"]).resolve()
            if not path.is_relative_to(manifest.parent):
                raise ValueError("Pilot projection file is outside its manifest directory")
            rows = _pinned(path, layer["sha256"]).decode("ascii").splitlines()
            if (len(rows) != layer["rows"] or len(set(rows)) != len(rows)
                    or any(not re.fullmatch("[0-9a-f]{64}", key) for key in rows)):
                raise ValueError(f"Invalid pilot projection digest rows: {kind}")
            self.targets[kind] = frozenset(rows)
        helper = manifest.parent / config["helpers"]["path"]
        code = _pinned(helper, config["helpers"]["sha256"])
        spec = spec_from_file_location("_hdocsyngen_ph1keys", helper)
        self.keys = module_from_spec(spec)
        exec(compile(code, str(helper), "exec"), vars(self.keys))
        _pinned(Path(self.keys.N.__file__), config["normalizer_sha256"])
        self.pins = {
            "manifest_sha256": pin,
            "key_helpers_sha256": config["helpers"]["sha256"],
            "normalizer_sha256": config["normalizer_sha256"],
            "layers": {kind: layer["sha256"] for kind, layer in layers.items()},
        }

    def hits(self, text: str) -> set[str]:
        keys = {
            "short_whole_line": {self.keys.key_short(text)},
            "unicode_whole_line": {self.keys.key_uni(text)},
        }
        if "normalized_whole_line" in self.targets:
            words = self.keys.words(text)
            keys["normalized_whole_line"] = {self.keys.H(" ".join(words))} if words else set()
        if "six_word" in self.targets:
            keys["six_word"] = self.keys.key_six(text)
        return {kind for kind, values in keys.items() if values & self.targets[kind]}

    def prepare(self, doc: Document) -> bool:
        """Regenerate fixed text when possible. Reject a tree if its dependent values hit."""
        # A naked page counter is a short template line regardless of seed.
        for foot in doc.furniture.footer:
            if not text_of(foot).strip() and any(run.field for run in foot.runs):
                foot.runs.insert(0, Run("דפדוף ברשומת המעקב: "))
        labels = model_labels(doc)
        for container, block in iter_paragraphs(doc):
            text = text_of(block)
            if self.hits(text) and not block.notes and not any(char.isdigit() for char in text):
                # Keep original runs, directions and styles. Only items with no anchored
                # offsets may change here. Numeric tables are regenerated as a whole.
                prefixes = ("לפי ", "לעניין ", "רישום לפי ", "במסגרת סקירתנו: ")
                if container.startswith("t") and len(text.split()) == 1:
                    # Narrow cells must not wrap back to the rejected original string.
                    prefixes = ("ל", "ב", "מ", "כ") + prefixes
                for prefix in prefixes:
                    if not self.hits(prefix + text):
                        block.runs.insert(0, Run(prefix))
                        text = text_of(block)
                        break
            if self.hits(text) or (block.id in labels and self.hits(labels[block.id].rstrip() + " " + text)):
                return False
        return not any(
            self.hits("\n".join(text_of(p) for p in cell.paragraphs))
            for table in doc.body if isinstance(table, Table) for cell in table.cells
        )
