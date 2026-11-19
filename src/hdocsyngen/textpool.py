"""The prose pool: a JSONL file, one {"id", "text", "licence", "source"} per line, logical order.

The pool is chosen and decontaminated by the caller (eval's CLEAN check against reservations, dev and test units
removed, design note §3.1). This module only cuts it into sentences and records which entries a document used.
"""
from __future__ import annotations

import json
import random
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

_SENT = re.compile(r"(?<=[.!?:;])\s+")
_HEBREW = re.compile(r"[֐-׿]")


@dataclass
class Sentence:
    entry: str
    text: str
    words: int


@dataclass
class TextPool:
    sentences: list[Sentence]
    licences: dict[str, tuple[str, str]]          # entry id -> (licence, source)
    used: dict[str, None] = field(default_factory=dict)   # insertion-ordered set

    @classmethod
    def load(cls, path: str | Path, require_licence: str | None = None) -> "TextPool":
        sentences, licences = [], {}
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            e = json.loads(line)
            if require_licence and e["licence"] != require_licence:
                continue
            licences[e["id"]] = (e["licence"], e.get("source", ""))
            for s in _SENT.split(unicodedata.normalize("NFC", e["text"]).strip()):
                s = " ".join(s.split())
                if _HEBREW.search(s):
                    sentences.append(Sentence(e["id"], s, len(s.split())))
        if not sentences:
            raise ValueError(f"{path}: no Hebrew sentences" + (f" with licence {require_licence}" if require_licence else ""))
        return cls(sentences, licences)

    def _mark(self, s: Sentence) -> str:
        self.used[s.entry] = None
        return s.text

    def sentence(self, rng: random.Random, min_words: int = 6, max_words: int = 40) -> str:
        fit = [s for s in self.sentences if min_words <= s.words <= max_words] or self.sentences
        return self._mark(rng.choice(fit))

    def paragraph(self, rng: random.Random, n_sentences: int) -> str:
        return " ".join(self.sentence(rng) for _ in range(n_sentences))

    def phrase(self, rng: random.Random, min_words: int = 2, max_words: int = 6) -> str:
        """A short span cut from a sentence (for headings and table cells), without trailing punctuation."""
        s = rng.choice(self.sentences)
        words = s.text.split()
        n = rng.randint(min_words, max_words)
        start = rng.randint(0, max(0, len(words) - n))
        self.used[s.entry] = None
        return " ".join(words[start:start + n]).rstrip(".,:;!?\"'")

    def sources(self) -> list[dict]:
        return [{"id": i, "licence": self.licences[i][0], "source": self.licences[i][1]} for i in self.used]
