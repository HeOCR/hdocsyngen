"""Number formats and the `model` label basis.

The `model` basis is what our numbering model expects a producer to show. The scored reference is the `producer` basis
(read back from the producer's own export, see the design note §3.3); `model` is a diagnostic. Counters follow Word's
semantics as far as they are modelled here: counters per abstractNum (shared by every num that uses it), startOverride
applied when its num is first used, deeper levels restarting unless lvlRestart says otherwise.
"""
from __future__ import annotations

from .tree import Document, iter_paragraphs

_UNITS = "אבגדהוזחט"
_TENS = "יכלמנסעפצ"
_HUNDREDS = "קרשת"
_LETTERS = "אבגדהוזחטיכלמנסעפצקרשת"


def hebrew1(n: int) -> str:
    """Hebrew counting by letter value (gematria), as Word's hebrew1: 15 is טו and 16 is טז, not יה / יו."""
    if not 1 <= n <= 999:
        raise ValueError(f"hebrew1 supports 1-999, got {n}")
    out = ""
    h, rest = divmod(n, 100)
    while h >= 4:
        out += "ת"
        h -= 4
    if h:
        out += _HUNDREDS[h - 1]
    if rest in (15, 16):
        return out + ("טו" if rest == 15 else "טז")
    t, u = divmod(rest, 10)
    if t:
        out += _TENS[t - 1]
    if u:
        out += _UNITS[u - 1]
    return out


def hebrew2(n: int) -> str:
    """Hebrew letters in order (א..ת), as Word's hebrew2. Past ת the producers disagree, so the model refuses."""
    if not 1 <= n <= 22:
        raise ValueError(f"hebrew2 is modelled for 1-22 only, got {n}")
    return _LETTERS[n - 1]


def fmt(n: int, kind: str) -> str:
    if kind == "decimal":
        return str(n)
    if kind == "hebrew1":
        return hebrew1(n)
    if kind == "hebrew2":
        return hebrew2(n)
    if kind == "lowerLetter":
        if not 1 <= n <= 26:
            raise ValueError("lowerLetter modelled for 1-26")
        return chr(ord("a") + n - 1)
    if kind == "bullet":
        return ""
    raise ValueError(f"unknown number format {kind!r}")


def model_labels(doc: Document) -> dict[str, str]:
    """Paragraph id -> the label the numbering model expects, for every numbered paragraph."""
    abstract = {a.id: a for a in doc.abstract_nums}
    nums = {n.id: n for n in doc.nums}
    counters: dict[int, list[int | None]] = {}
    seen: set[int] = set()
    labels: dict[str, str] = {}
    for container, p in iter_paragraphs(doc):
        if container in ("header", "footer") or p.num is None:
            continue
        num = nums[p.num.num_id]
        a = abstract[num.abstract]
        state = counters.setdefault(a.id, [None] * len(a.levels))
        if num.id not in seen:
            seen.add(num.id)
            for lvl, start in num.start_override.items():
                state[lvl] = start - 1
        lvl = p.num.level
        level = a.levels[lvl]
        state[lvl] = level.start if state[lvl] is None else state[lvl] + 1
        for deeper in range(lvl + 1, len(a.levels)):
            w = a.levels[deeper].restart
            w = deeper if w is None else w          # default: restart after any shallower level
            if w != 0 and lvl + 1 <= w:
                state[deeper] = None
        if level.fmt == "bullet":
            labels[p.id] = level.text
            continue
        label = level.text
        for k in range(len(a.levels), 0, -1):       # %10 never occurs (9 levels max); go high to low anyway
            token = f"%{k}"
            if token in label:
                v = state[k - 1]
                v = a.levels[k - 1].start if v is None else v
                label = label.replace(token, fmt(v, a.levels[k - 1].fmt))
        labels[p.id] = label
    return labels
