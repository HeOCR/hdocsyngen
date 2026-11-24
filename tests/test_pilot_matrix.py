from hashlib import sha256

import pytest

from hdocsyngen.pilot_matrix import _ROUTES, _native_pdf, _validate_slot


def test_native_matrix_uses_archive_receipt_hashes(tmp_path):
    doc = "tender-42"
    folder = tmp_path/doc
    (folder/"word").mkdir(parents=True)
    result = folder/f"{doc}.result.json"
    tree = folder/f"{doc}.tree.json"
    plain = folder/"word"/f"{doc}.word.pdf"
    for path in (result, tree, plain):
        path.write_bytes(path.name.encode())
    row = {"doc_id": doc, "producer": "word"}
    for key, path in (("producer_result_sha256", result), ("tree_sha256", tree), ("plain_sha256", plain)):
        row[key] = sha256(path.read_bytes()).hexdigest()
    entry = {"result": result.relative_to(tmp_path).as_posix()}
    assert _native_pdf(tmp_path, entry, row) == plain

    plain.write_bytes(b"changed synthetic PDF fixture")
    with pytest.raises(ValueError, match="plain_sha256"):
        _native_pdf(tmp_path, entry, row)


def test_resume_rejects_missing_routes_and_changed_pdf(tmp_path):
    source = {"doc_id": "report-7", "producer": "lo", "producer_version": "fixture", "plain_sha256": "a"}
    rows = []
    for route in _ROUTES[1:]:
        asset = tmp_path/f"{route}.pdf"
        asset.write_bytes(route.encode())
        rows.append({"doc_id": source["doc_id"], "native_producer": "lo", "native_version": "fixture",
                     "native_sha256": "a", "route": route, "artifact": asset.name,
                     "pdf_sha256": sha256(asset.read_bytes()).hexdigest()})
    _validate_slot(tmp_path, rows, source)
    with pytest.raises(ValueError, match="Incomplete"):
        _validate_slot(tmp_path, rows[:-1], source)
    (tmp_path/rows[-1]["artifact"]).write_bytes(b"a different fixture")
    with pytest.raises(ValueError, match="PDF changed"):
        _validate_slot(tmp_path, rows, source)
