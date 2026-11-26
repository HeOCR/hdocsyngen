"""Source-backed physical line sidecar for the native TRAIN producer pilot."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field, replace
from hashlib import sha256
import json
from pathlib import Path

from . import layout, pdfcheck
from .literal_verify import _source_visual, _visual_rows, literal
from .pilot_filter import PilotFilter
from .pilot_readback import _owned_file, _pdf_from_receipt, _sha
from .tree import Table, colour_index, iter_paragraphs, loads, text_of, twin_colours


@dataclass
class Line:
    page: int
    block_id: str
    body: str
    glyphs: list[pdfcheck.Glyph]
    source_span: tuple[int, int]
    label: str = ""
    marks: list[tuple[int, str]] = field(default_factory=list)
    table_panel: int | None = None

    @property
    def bbox(self):
        return (min(g.x0 for g in self.glyphs), min(g.y0 for g in self.glyphs),
                max(g.x1 for g in self.glyphs), max(g.y1 for g in self.glyphs))


def _page_glyphs(path):
    return [(page, glyph) for page, glyph in pdfcheck._chars(path)
            if literal(glyph.text) and pdfcheck._slot_order(glyph.text)]


def _bound_glyphs(plain, twin):
    """Match each twin glyph once to the same glyph on the plain carrier."""
    by_code = defaultdict(dict)
    for index, (page, glyph) in enumerate(_page_glyphs(plain)):
        by_code[page, glyph.text][index] = glyph
    for page, glyph in _page_glyphs(twin):
        options = by_code[page, glyph.text]
        x, y = glyph.origin
        nearest = None
        delta = 0.46
        tied = False
        for index, candidate in options.items():
            left, bottom = candidate.origin
            distance = max(abs(x-left), abs(y-bottom))
            if distance < delta:
                nearest, delta, tied = index, distance, False
            elif distance == delta and nearest is not None:
                tied = True
        if nearest is None or tied:
            raise ValueError("No unique same-position twin glyph on the plain PDF")
        yield page, replace(options.pop(nearest), rgb=glyph.rgb)
    if any(by_code.values()):
        raise ValueError("Unaccounted glyphs on the plain PDF")


def _printed_block(block, page, n_pages):
    return replace(block, runs=[
        replace(run, text=str(page if run.field == "page" else n_pages), field=None)
        if run.field else run for run in block.runs
    ])


def _visual(text):
    from bidi.algorithm import get_display

    return pdfcheck._slot_order(get_display(text, base_dir="R"))


def _parts(rows, block, label):
    """Recover source spans from physical baselines, verifying order within each baseline."""
    source = text_of(block)
    width = [len(pdfcheck._slot_order(ch)) for ch in source]
    stop = 0
    output = []
    for i, (page, row) in enumerate(rows):
        while stop < len(source) and not width[stop]:
            stop += 1
        start = stop
        shown = "".join(pdfcheck._slot_order(g.text) for g in row)
        found_label = ""
        if i == 0 and label and shown.endswith(_visual(label)):
            # Native HTML may paint list furniture in the block's own colour.
            expected = sum(width)
            if sum(len(pdfcheck._slot_order(g.text)) for _, r in rows for g in r) == expected + len(_visual(label)):
                found_label = label
                shown = shown[:-len(_visual(label))]
        remaining = len(shown)
        while stop < len(source) and remaining > 0:
            remaining -= width[stop]
            stop += 1
        if remaining != 0 or not shown or shown not in {
            pdfcheck._slot_order(text) for text in _source_visual(block, start, stop)
        }:
            raise ValueError(f"Source span and physical glyphs differ: {block.id}")
        output.append(Line(page, block.id, source[start:stop], row, (start, stop), found_label))
    if any(width[stop:]):
        raise ValueError(f"Source span left without physical glyphs: {block.id}")
    return output


def _panel(origin_x: float, page_width: float, panels: int) -> int:
    # Both writers give the table the full body width with equal side margins.
    margin = 72 * 2 / 2.54
    fraction = (page_width - margin - origin_x) / (page_width - 2 * margin)
    return min(panels - 1, max(0, int(fraction * panels)))


def _table_parts(block, by_page, page_widths, table, cell, panels, label=""):
    """Verify each printed header copy independently and keep its RTL panel identity."""
    repeated = cell.header and table.repeat_header
    if panels and cell.header:
        lines = []
        for page, glyphs in sorted(by_page.items()):
            copies = defaultdict(list)
            for glyph in glyphs:
                copies[_panel(glyph.origin[0], page_widths[page], table.blocks)].append(glyph)
            if set(copies) != set(range(table.blocks)):
                raise ValueError(f"Missing or misplaced side-by-side header copy: {block.id}")
            for panel, values in sorted(copies.items()):
                rows = [(page, row) for row in _visual_rows(values)]
                lines.extend(replace(line, table_panel=panel) for line in _parts(rows, block, label))
        if not lines and literal(text_of(block)):
            raise ValueError(f"Missing side-by-side header: {block.id}")
        return lines

    rows = [(page, row) for page, glyphs in sorted(by_page.items()) for row in _visual_rows(glyphs)]
    if repeated and len(by_page) > 1:
        return [line for page, glyphs in sorted(by_page.items())
                for line in _parts([(page, row) for row in _visual_rows(glyphs)], block, label)]
    lines = _parts(rows, block, label)
    if panels:
        panel = (cell.r - panels["header_rows"]) // panels["rows_per_block"]
        for line in lines:
            if any(_panel(g.origin[0], page_widths[line.page], table.blocks) != panel for g in line.glyphs):
                raise ValueError(f"Body cell is in the wrong side-by-side panel: {block.id}")
            line.table_panel = panel
    return lines


def _recover_bare_field(loose, expected, container, page_height, block_id):
    """Recover a single black Office page counter in the reserved margin."""
    def in_margin(glyph):
        y = glyph.origin[1]
        return y < 45 if container == "footer" else y > page_height - 45

    rows = _visual_rows([glyph for glyph in loose if in_margin(glyph)])
    candidates = [row for row in rows if "".join(g.text for g in row) == expected]
    if len(candidates) != 1:
        raise ValueError(f"Missing or ambiguous page counter: {block_id}")
    return candidates[0]


def physical_lines(doc, plain: Path, twin: Path, gold: dict, pdf_sha: str) -> list[dict]:
    """Return exact logical line texts with plain-PDF geometry and source identities."""
    import pypdfium2 as pdfium

    with pdfium.PdfDocument(str(plain)) as pdf:
        sizes = {i + 1: pdf.get_page_size(i) for i in range(len(pdf))}
    pages = len(sizes)
    page_widths = {page: size[0] for page, size in sizes.items()}
    colours = {colour_index(rgb): pid for pid, rgb in twin_colours(doc).items()}
    blocks = {block.id: (container, block) for container, block in iter_paragraphs(doc)}
    table_cells = {p.id: (table, cell) for table in doc.body if isinstance(table, Table)
                   for cell in table.cells for p in cell.paragraphs}
    panels = {table.id: layout.blocks_meta(table) for table in doc.body if isinstance(table, Table)}
    labels = {item["id"]: item.get("label_producer") or item.get("label_model", "")
              for item in gold["blocks"]}
    by_block = defaultdict(lambda: defaultdict(list))
    loose = defaultdict(list)
    for page, glyph in _bound_glyphs(plain, twin):
        pid = colours.get(colour_index(glyph.rgb or (255, 255, 255)))
        (by_block[pid][page] if pid is not None else loose[page]).append(glyph)

    # Office page counters may be black even when the rest of the margin line
    # is coloured. Rejoin by baseline before verifying the tree's field values.
    for pid, (container, block) in blocks.items():
        if container not in {"header", "footer"} or not any(run.field for run in block.runs):
            continue
        for page in range(1, pages + 1):
            glyphs = by_block[pid][page]
            if not glyphs:
                if any(literal(run.text) for run in block.runs if not run.field):
                    raise ValueError(f"Missing coloured furniture on page {page}: {pid}")
                expected = literal(text_of(_printed_block(block, page, pages)))
                recovered = _recover_bare_field(loose[page], expected, container, sizes[page][1], pid)
            else:
                recovered = [g for g in loose[page] if g.text.isdecimal()
                             and any(abs(g.origin[1] - c.origin[1]) < 1.1 for c in glyphs)]
            glyphs += recovered
            loose[page] = [g for g in loose[page] if g not in recovered]

    lines = []
    for pid, (container, block) in blocks.items():
        if pid in table_cells and not block.notes:
            table, cell = table_cells[pid]
            lines.extend(_table_parts(block, by_block[pid], page_widths, table, cell, panels[table.id],
                                      labels.get(pid, "").strip()))
            continue
        rows = []
        lifted_marks = []
        for page, glyphs in sorted(by_block[pid].items()):
            groups = _visual_rows(glyphs)
            # A note anchor is rendered as an elevated digit from the writer.
            # Its physical bounding box is retained separately from the main baseline.
            for group in groups:
                if block.notes and all(g.text.isdecimal() for g in group) and len(groups) > 1:
                    lifted_marks.extend((page, g) for g in group)
                else:
                    rows.append((page, group))
        for page, glyph in lifted_marks:
            loose[page].append(glyph)
        if container in {"header", "footer"}:
            for page in range(1, pages + 1):
                line_rows = [(pg, row) for pg, row in rows if pg == page]
                lines.extend(_parts(line_rows, _printed_block(block, page, pages), ""))
        else:
            lines.extend(_parts(rows, block, labels.get(pid, "").strip()))

    _attach_furniture_marks(lines, loose, blocks, labels)
    if sum(len(line.marks) for line in lines) != sum(len(block.notes) for _, block in blocks.values()):
        raise ValueError("Physical note anchors do not cover the source anchors")
    result = []
    ordinals = defaultdict(int)
    # Preserve tree/table reading order by block, with header first and footer last.
    order = {pid: i for i, pid in enumerate(blocks)}
    rank = {"header": 0, "footer": 2}
    table_order = {}
    for pid, (table, _) in table_cells.items():
        table_order.setdefault(table.id, order[pid])

    def reading_order(line):
        pid = line.block_id
        container = blocks[pid][0]
        group = table_order[container] if line.table_panel is not None else order[pid]
        return line.page, rank.get(container, 1), group, line.table_panel or 0, order[pid], -line.bbox[3]

    lines.sort(key=reading_order)
    for line in lines:
        ordinals[line.page] += 1
        body = line.body
        for offset, value in sorted(line.marks, reverse=True):
            body = body[:offset] + value + body[offset:]
        text = (line.label + " " if line.label else "") + body
        if not line.bbox[0] < line.bbox[2] or not line.bbox[1] < line.bbox[3]:
            raise ValueError(f"Empty physical line box: {line.block_id}")
        cell_ref = {}
        if line.block_id in table_cells:
            table, cell = table_cells[line.block_id]
            cell_ref["cell_id"] = f"{table.id}:{cell.r}:{cell.c}"
            if line.table_panel is not None:
                cell_ref["table_panel"] = line.table_panel
        result.append({"page": line.page, "order": ordinals[line.page], "block_id": line.block_id,
                       "container_id": blocks[line.block_id][0], **cell_ref,
                       "source_span": list(line.source_span),
                       "bbox_pt_bottom_left": list(line.bbox), "pdf_sha256": pdf_sha,
                       "text_sha256": sha256(text.encode()).hexdigest(), "text": text})
    return result


def _attach_furniture_marks(lines, loose, blocks, labels):
    by_page = defaultdict(list)
    for line in lines:
        by_page[line.page].append(line)
    for page, glyphs in loose.items():
        groups = []
        for row in _visual_rows(glyphs):
            for glyph in row:
                if not groups or groups[-1][-1] not in row or glyph.x0 - groups[-1][-1].x1 > 5:
                    groups.append([])
                groups[-1].append(glyph)
        for group in groups:
            y = group[0].origin[1]
            text = "".join(g.text for g in group)
            x0, x1 = min(g.x0 for g in group), max(g.x1 for g in group)
            nearby = []
            for line in by_page[page]:
                first = line.glyphs[0]
                left, _, right, _ = line.bbox
                dx = max(left - x1, x0 - right, 0)
                dy = abs(first.origin[1] - y)
                if dx < 36 and dy < 8:
                    nearby.append((dy, dx, line))
            nearby.sort(key=lambda item: item[:2])
            for dy, _, line in nearby:
                container, block = blocks[line.block_id]
                label = labels.get(line.block_id, "").strip()
                if (dy < 1.1 and not line.label and x0 >= line.bbox[2] - 1
                        and label and (_visual(label) == pdfcheck._slot_order(text)
                                       or label in {"•", "–"} and text in {"•", "–", "◦", "▪"})):
                    line.label = text if label in {"•", "–"} else label
                    break
                note_number = text.isdecimal() or bool(text) and set(text.casefold()) <= set("ivxlcdm")
                if note_number and (container.startswith("n") or block.notes):
                    if container.startswith("n") and x0 >= line.bbox[2] - 1:
                        line.label = text
                        break
                    if (block.notes and any(mark.offset == line.source_span[1] for mark in block.notes)
                            and dy >= 1.1 and x1 <= line.bbox[0] + 8):
                        line.marks.append((len(line.body), text))
                        break
            else:
                raise ValueError(f"Unbound producer mark on page {page}")
            line.glyphs.extend(group)


def audit(root: Path, out: Path) -> dict:
    """Replay the exact source and plain/twin PDF joins, then report whole-tree holds."""
    root = root.resolve()
    manifest_path = _owned_file(root, "manifest.json")
    manifest = json.loads(manifest_path.read_bytes())
    if manifest["producer_builds"] != manifest["producer_builds_after"]:
        raise ValueError("Incomplete pilot or changed producer versions")
    filtering = manifest["spec"]["protected_projections"]
    guard = PilotFilter(Path(filtering["manifest"]), filtering["sha256"])
    if guard.pins != manifest["protected_projections"]:
        raise ValueError("Pilot projection configuration has changed")

    out.mkdir(mode=0o700)
    rows = []
    for item in manifest["docs"]:
        doc_id = item["doc_id"]
        result = _owned_file(root, item["result"])
        if _sha(result) != item["result_sha256"]:
            raise ValueError("Pilot result pin changed")
        report = json.loads(result.read_bytes())
        tree_file = _owned_file(result.parent, f"{doc_id}.tree.json")
        tree_sha = _sha(tree_file)
        if tree_sha != report["sources"]["tree.json"]:
            raise ValueError("Pilot source pin changed")
        doc = loads(tree_file.read_text(encoding="utf-8"))
        if doc.doc_id != doc_id or set(report["producers"]) != set(manifest["producer_builds"]):
            raise ValueError("Pilot tree or producer identity changed")
        for route, build in manifest["producer_builds"].items():
            lane = report["producers"][route]
            row = {"doc_id": doc_id, "producer": route, "tree_sha256": tree_sha,
                   "producer_version": build["version"]}
            rows.append(row)
            if "error" in lane or lane["pdf_check"]["problems"] or lane.get("resaved_docx_check"):
                row.update(status="hold", reason="native_producer_check")
                continue
            row["label_basis"] = "producer" if "labels" in lane else "model"
            row["label_export_hold"] = "label_export_error" in lane
            if route == "word":
                row["producer_bundle_version"] = build["bundle_version"]
            ext = "html" if route == "chrome" else "docx"
            plain, twin = (
                _pdf_from_receipt(result.parent / route, lane[mode], build["version"], build=build,
                                  input_sha256=report["sources"][prefix + ext])
                for mode, prefix in (("plain", ""), ("twin", "twin."))
            )
            gold_path = _owned_file(result.parent, f"{doc_id}.{route}.gold.json")
            gold = json.loads(gold_path.read_bytes())
            pdf_sha = _sha(plain)
            if gold["producer"]["pdf_sha256"] != pdf_sha or gold["lineage"]["tree_sha256"] != tree_sha:
                raise ValueError("Producer gold is outside the pinned pilot slot")
            row.update(pdf_sha256=pdf_sha, twin_sha256=_sha(twin), gold_sha256=_sha(gold_path))
            try:
                lines = physical_lines(doc, plain, twin, gold, pdf_sha)
            except ValueError as exc:
                row.update(status="hold", reason=str(exc))
                continue

            by_page = defaultdict(list)
            hits = []
            for line in lines:
                by_page[line["page"]].append(line["text"])
                kinds = guard.hits(line["text"])
                if kinds:
                    hits.append({"page": line["page"], "order": line["order"], "kinds": sorted(kinds)})
            for page, texts in by_page.items():
                kinds = guard.hits("\n".join(texts))
                if kinds:
                    hits.append({"page": page, "kinds": sorted(kinds)})
            for unit, text in _logical_text(gold):
                kinds = guard.hits(text)
                if kinds:
                    hits.append({"unit": unit, "kinds": sorted(kinds)})
            path = out / f"{doc_id}.{route}.lines.jsonl"
            with path.open("x", encoding="utf-8") as stream:
                for line in lines:
                    stream.write(json.dumps(line, ensure_ascii=False, sort_keys=True) + "\n")
            row.update(status="hold" if hits else "pass", pages=len(by_page), lines=len(lines),
                       references=path.name, references_sha256=_sha(path), projection_hits=hits)
    held = {row["doc_id"] for row in rows if row["status"] != "pass"}
    return {"schema": "hdocsyngen.pilot_physical_lines.v1", "split": "train",
            "manifest_sha256": _sha(manifest_path), "projection_pins": guard.pins,
            "retained_doc_ids": [item["doc_id"] for item in manifest["docs"] if item["doc_id"] not in held],
            "held_doc_ids": [item["doc_id"] for item in manifest["docs"] if item["doc_id"] in held],
            "rows": rows}


def _logical_text(gold):
    for block in gold["blocks"]:
        text = block.get("text", "")
        label = block.get("label_producer") or block.get("label_model")
        yield block["id"], text
        if label:
            yield block["id"] + ":labelled", f"{label.rstrip()} {text}"
    for table in gold["tables"]:
        for cell in table["cells"]:
            yield f"{table['id']}:{cell['r']}:{cell['c']}", cell["text"]
    for blocks in gold["furniture"].values():
        for block in blocks:
            yield block["id"], block["text"]
