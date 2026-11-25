import hashlib
import json

import pytest

from hdocsyngen.pilot_filter import PilotFilter
from hdocsyngen.tree import Cell, Document, Furniture, Heading, Meta, Paragraph, Run, Table, text_of


def digest(data):
    return hashlib.sha256(data).hexdigest()


@pytest.fixture
def filter_manifest(tmp_path):
    # Stand-ins for the external pinned helpers. All target values are invented.
    normalizer = tmp_path / "fixture_normalizer.py"
    normalizer.write_text("fixture\n")
    keys = tmp_path / "ph1keys.py"
    keys.write_text(
        "from hashlib import sha256\nfrom types import SimpleNamespace\n"
        "N = SimpleNamespace(__file__=" + repr(str(normalizer)) + ")\n"
        "def H(text): return sha256(text.encode()).hexdigest()\n"
        "def words(text): return text.split()\n"
        "def key_short(text): return H(' '.join(words(text))) if 1 <= len(words(text)) <= 5 else None\n"
        "def key_uni(text): return H(' '.join(text.split())) if text.strip() else None\n"
    )
    manifest = {"schema": "hdocsyngen.pilot_projections.v1",
                "helpers": {"path": keys.name, "sha256": digest(keys.read_bytes())},
                "normalizer_sha256": digest(normalizer.read_bytes()), "layers": {}}
    for kind, text in (("short_whole_line", "מפתח בדוי"), ("unicode_whole_line", "72138")):
        path = tmp_path / kind
        path.write_text(digest(text.encode()) + "\n")
        manifest["layers"][kind] = {"path": path.name, "sha256": digest(path.read_bytes()), "rows": 1}
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest))
    return path, digest(path.read_bytes())


def test_guard_repairs_heading_and_keeps_dynamic_footer(filter_manifest):
    guard = PilotFilter(*filter_manifest)
    heading = Heading("h1", 1, [Run("מפתח בדוי")])
    footer = Paragraph("p2", [Run("1", "num", field="page")])
    doc = Document("fixture", Meta("report", "report", 9), [heading], furniture=Furniture(footer=[footer]))
    assert guard.hits(text_of(heading)) == {"short_whole_line"}
    assert guard.prepare(doc)
    assert not guard.hits(text_of(heading))
    assert len(footer.runs) == 2 and footer.runs[1].field == "page"


def test_guard_rejects_cell_without_changing_dependent_number(filter_manifest):
    guard = PilotFilter(*filter_manifest)
    cell = Paragraph("p1", [Run("72138", "num")])
    table = Table("t0", 1, 1, [Cell(0, 0, [cell])])
    doc = Document("fixture", Meta("report", "report", 9), [table])
    assert not guard.prepare(doc)
    assert text_of(cell) == "72138"


def test_guard_rejects_a_changed_digest_list(filter_manifest):
    path, _ = filter_manifest
    (path.parent / "unicode_whole_line").write_text("0" * 64 + "\n")
    with pytest.raises(ValueError, match="pin mismatch"):
        PilotFilter(*filter_manifest)


def test_tender_rejection_keeps_figures_linked():
    from hdocsyngen.templates import tender
    from hdocsyngen.textpool import Sentence, TextPool

    words = "בבוקר הענן נשאר מעל החלון הקטן והציפור נחה בצד."
    pool = TextPool([Sentence("fixture", words, len(words.split()))], {"fixture": ("CC0-1.0", "invented")})
    doc = tender.build("tender-42", 42, pool, reject_cell=lambda value: value.isdecimal() and int(value) <= 300)
    table = next(block for block in doc.body if isinstance(block, Table))
    cells = {(cell.r, cell.c): text_of(cell.paragraphs[0]) for cell in table.cells}

    def integer(row, column):
        return int(cells[row, column].replace(",", ""))

    subtotals = []
    for row in range(1, table.rows - 1):
        if (row, 3) not in cells:  # full-width group heading
            continue
        qty = integer(row, 3)
        assert qty > 300
        subtotal = integer(row, 5)
        assert subtotal == qty * integer(row, 4)
        subtotals.append(subtotal)
    assert integer(table.rows - 1, 5) == sum(subtotals)
