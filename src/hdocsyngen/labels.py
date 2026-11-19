"""The `producer` label basis (design note §3.3, check 2; eval: the scored reference).

Word and LibreOffice export plain text with list labels as the producer rendered them. Body paragraphs are matched to
export lines in order (a line must end with the paragraph's gold text), and the text before it is the label.
"""
from __future__ import annotations

import re
import unicodedata
from pathlib import Path

from .tree import Document, Heading, Paragraph, text_of


def read_export(path: Path) -> list[str]:
    raw = path.read_bytes()
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        text = raw.decode("utf-16")
    else:
        text = raw.decode("utf-8-sig", errors="replace")
    return [unicodedata.normalize("NFC", line.replace("‏", "").replace("‎", "")).rstrip()
            for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")]


def producer_labels(doc: Document, lines: list[str]) -> tuple[dict[str, str], list[str]]:
    """Paragraph id -> producer label, for numbered body paragraphs; and the ids that could not be matched."""
    labels, unmatched = {}, []
    i = 0
    for b in doc.body:
        if not isinstance(b, (Paragraph, Heading)):
            continue
        t = text_of(b).strip()
        if not t:
            continue
        def body_of(line: str) -> str | None:
            """The line without its trailing note mark, if it ends with the paragraph's text. Producers export note
            anchors inline: Word as the note number, LibreOffice as U+0002. Template anchors sit at the end."""
            line = line.replace("\x02", "").strip()
            if line.endswith(t):
                return line
            if b.notes:
                cut = re.sub(r"[0-9*]{1,3}$", "", line).strip()
                if cut.endswith(t):
                    return cut
            return None

        j = i
        while j < len(lines) and body_of(lines[j]) is None:
            j += 1
        if j == len(lines):
            if b.num is not None:
                unmatched.append(b.id)
            continue
        if b.num is not None:
            line = body_of(lines[j])
            labels[b.id] = line[: len(line) - len(t)].strip()
        i = j + 1
    return labels, unmatched
