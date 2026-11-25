"""HTML + CSS writer, for Chrome print-to-PDF (P5) and later WeasyPrint (P5w).

The same tree as the DOCX, as semantic HTML in `dir="rtl"`:
- **numbering:** CSS counters (`counter(x, hebrew)` for hebrew1), so the label is the browser's own, the `producer`
  basis;
- **tables:** `rowspan` and `colspan`, with a `thead` that repeats on every page;
- **furniture:** CSS page-margin boxes, with `counter(page)` and `counter(pages)`;
- **notes:** Chrome has no paged-media footnotes, so footnotes and endnotes are written as notes at the end, with
  superscript anchors. Their text and anchors are the same gold; their place on the page is the producer's.

With `twin=True` every block gets its near-black twin colour (tree.twin_colours).
"""
from __future__ import annotations

from base64 import b64encode
from hashlib import sha256
from html import escape
from io import BytesIO
from pathlib import Path

from ..fonts import FontFile

from ..layout import printed
from ..tree import Document, Heading, PageBreak, Paragraph, Run, Table, text_of, twin_colours

CSS_FMT = {"decimal": "decimal", "hebrew1": "hebrew", "lowerLetter": "lower-latin"}
ALIGN = {"start": "start", "justify": "justify", "center": "center", "end": "end"}


def _css_label(abstract_id: int, levels, lvl: int) -> str:
    text = levels[lvl].text
    if levels[lvl].fmt == "bullet":
        return '"' + text.replace('"', '\\"') + ' "'
    parts, i = [], 0
    while i < len(text):
        if text[i] == "%" and i + 1 < len(text) and text[i + 1].isdigit():
            k = int(text[i + 1]) - 1
            parts.append(f"counter(n{abstract_id}l{k}, {CSS_FMT[levels[k].fmt]})")
            i += 2
        else:
            j = i
            while j < len(text) and not (text[j] == "%" and j + 1 < len(text) and text[j + 1].isdigit()):
                j += 1
            parts.append('"' + text[i:j].replace('"', '\\"') + '"')
            i = j
    return " ".join(parts) + ' " "'


def _numbering_css(doc: Document) -> str:
    rules, resets = [], []
    nums = {n.id: n for n in doc.nums}
    for a in doc.abstract_nums:
        for k, lv in enumerate(a.levels):
            resets.append(f"n{a.id}l{k} {lv.start - 1}")
            deeper = " ".join(f"n{a.id}l{d} {a.levels[d].start - 1}" for d in range(k + 1, len(a.levels))
                              if a.levels[d].restart != 0)
            reset = f" counter-set: {deeper};" if deeper else ""
            rules.append(f".n{a.id}-{k} {{ counter-increment: n{a.id}l{k};{reset} }}\n"
                         f".n{a.id}-{k}::before {{ content: {_css_label(a.id, a.levels, k)}; }}")
    for n in nums.values():
        for lvl, start in n.start_override.items():
            rules.append(f".so{n.id}-{lvl} {{ counter-set: n{n.abstract}l{lvl} {start - 1}; }}")
    return f"body {{ counter-reset: {' '.join(resets)}; }}\n" + "\n".join(rules)


def _runs(runs: list[Run], anchors, note_no: dict[str, int]) -> str:
    out, pos = [], 0
    pending = sorted(anchors, key=lambda a: a.offset)

    def span(r: Run, text: str) -> str:
        t = escape(text)
        if r.lang != "he":
            t = f'<bdi dir="ltr">{t}</bdi>' if r.lang == "en" else f"<bdi>{t}</bdi>"
        if r.bold:
            t = f"<b>{t}</b>"
        if r.italic:
            t = f"<i>{t}</i>"
        return t

    for r in runs:
        text = r.text
        while pending and pos <= pending[0].offset <= pos + len(text):
            a = pending.pop(0)
            k = a.offset - pos
            if k:
                out.append(span(r, text[:k]))
            out.append(f'<sup class="nref">{note_no[a.note_id]}</sup>')
            text, pos = text[k:], a.offset
        if text:
            out.append(span(r, text))
        pos += len(text)
    for a in pending:
        out.append(f'<sup class="nref">{note_no[a.note_id]}</sup>')
    return "".join(out)


def _embedded_faces(family: str, faces: tuple[FontFile, ...]) -> str:
    from fontTools.ttLib import TTFont

    rules = []
    for face in faces:
        blob = Path(face.path).read_bytes()
        if face.family != family or sha256(blob).hexdigest() != face.sha256:
            raise ValueError("Embedded face differs from the document font pin")
        with TTFont(BytesIO(blob)) as font:
            mime = "font/otf" if font.sfntVersion == "OTTO" else "font/ttf"
            italic = "italic" if font["head"].macStyle & 2 else "normal"
            weight = font["OS/2"].usWeightClass
            if "fvar" in font:
                for axis in font["fvar"].axes:
                    if axis.axisTag == "wght":
                        weight = f"{axis.minValue:g} {axis.maxValue:g}"
        data = b64encode(blob).decode("ascii")
        rules.append(
            f'@font-face {{ font-family: "{family}"; font-style: {italic}; font-weight: {weight}; '
            f'src: url(data:{mime};base64,{data}); }}'
        )
    return "\n".join(rules)


def write(doc: Document, twin: bool = False, *, embedded_fonts: tuple[FontFile, ...] = (),
          page_layout: bool = False, second_column_at: str | None = None) -> bytes:
    colours = twin_colours(doc) if twin else {}
    nums = {n.id: n for n in doc.nums}
    note_no, seen_nums = {}, set()

    def numbered_order(paragraphs):
        for p in paragraphs:
            for a in sorted(p.notes, key=lambda a: a.offset):
                note_no.setdefault(a.note_id, len(note_no) + 1)

    # note numbers in reading order of their anchors
    from ..tree import iter_paragraphs
    numbered_order([p for c, p in iter_paragraphs(doc) if c not in ("header", "footer")])

    def style(p) -> str:
        parts = []
        if p.id in colours:
            parts.append("color: rgb(%d,%d,%d)" % colours[p.id])
        al = ALIGN.get(getattr(p, "align", "start"), "start")
        if al != "start":
            parts.append(f"text-align: {al}")
        return f' style="{"; ".join(parts)}"' if parts else ""

    def classes(p) -> str:
        cl = []
        if p.num is not None:
            n = nums[p.num.num_id]
            cl.append(f"n{n.abstract}-{p.num.level}")
            if n.id not in seen_nums:
                seen_nums.add(n.id)
                cl += [f"so{n.id}-{lvl}" for lvl in n.start_override]
            cl.append(f"lvl{p.num.level}")
        if isinstance(p, Paragraph) and p.style:
            cl.append(p.style)
        return f' class="{" ".join(cl)}"' if cl else ""

    def para(p, tag: str | None = None) -> str:
        tag = tag or (f"h{p.level}" if isinstance(p, Heading) else "p")
        return f'<{tag} id="{p.id}"{classes(p)}{style(p)}>{_runs(p.runs, p.notes, note_no)}</{tag}>'

    body = []
    if second_column_at is not None:
        body.append('<main class="page-columns"><section>')
    for b in doc.body:
        if b.id == second_column_at:
            body.append("</section><section>")
        if isinstance(b, PageBreak):
            body.append('<div class="pb"></div>')
        elif isinstance(b, Table):
            b = printed(b)
            origin = {(c.r, c.c): c for c in b.cells}
            head_rows = sorted({c.r for c in b.cells if c.header})
            widths = b.col_widths or [1.0] * b.cols
            total = sum(widths)
            cols = "".join(f'<col style="width:{100 * w / total:.1f}%">' for w in widths)
            rows_html = []
            for r in range(b.rows):
                tds = []
                for c in range(b.cols):
                    cell = origin.get((r, c))
                    if cell is None:
                        continue
                    tag = "th" if cell.header else "td"
                    span = (f' rowspan="{cell.rowspan}"' if cell.rowspan > 1 else "") + \
                           (f' colspan="{cell.colspan}"' if cell.colspan > 1 else "")
                    inner = "".join(para(p, "div") for p in cell.paragraphs)
                    tds.append(f"<{tag}{span}>{inner}</{tag}>")
                rows_html.append((r, f"<tr>{''.join(tds)}</tr>"))
            thead = "".join(h for r, h in rows_html if r in head_rows)
            tbody = "".join(h for r, h in rows_html if r not in head_rows)
            body.append(f'<table id="{b.id}" class="ruled-{b.ruled}"><colgroup>{cols}</colgroup>'
                        + (f"<thead>{thead}</thead>" if thead and b.repeat_header else "")
                        + f"<tbody>{'' if (thead and b.repeat_header) else thead}{tbody}</tbody></table>")
        else:
            body.append(para(b))
    if second_column_at is not None:
        body.append("</section></main>")
    if doc.notes:
        by_id = {n.id: n for n in doc.notes}
        items = []
        for nid, k in sorted(note_no.items(), key=lambda x: x[1]):
            n = by_id[nid]
            inner = "".join(para(p, "div") for p in n.paragraphs)
            items.append(f'<div class="note {n.kind}" id="{n.id}"><span class="nmark">{k}</span> {inner}</div>')
        body.append('<section class="notes"><hr>' + "".join(items) + "</section>")

    def margin_box(paras) -> str:
        parts = []
        for p in paras:
            for r in p.runs:
                if r.field == "page":
                    parts.append("counter(page)")
                elif r.field == "numpages":
                    parts.append("counter(pages)")
                else:
                    parts.append('"' + r.text.replace('"', '\\"') + '"')
        return " ".join(parts) or '""'

    def box_colour(paras) -> str:
        return ("color: rgb(%d,%d,%d);" % colours[paras[0].id]) if (paras and paras[0].id in colours) else ""

    m = doc.meta
    size = "A4" if m.page == "A4" else "letter"
    css = f"""
@page {{ size: {size} {m.orientation}; margin: 2cm 2cm 2cm 2cm;
  @top-center {{ content: {margin_box(doc.furniture.header)}; font-family: "{m.font}"; font-size: {m.font_size_pt - 2}pt; {box_colour(doc.furniture.header)} }}
  @bottom-center {{ content: {margin_box(doc.furniture.footer)}; font-family: "{m.font}"; font-size: {m.font_size_pt - 2}pt; {box_colour(doc.furniture.footer)} }} }}
html {{ font-family: "{m.font}"; font-size: {m.font_size_pt}pt; }}
body {{ margin: 0; line-height: 1.3; }}
p, div {{ margin: 0 0 0.5em 0; }}
h1 {{ font-size: 1.4em; }} h2 {{ font-size: 1.2em; }} h3, h4 {{ font-size: 1.05em; }}
.title {{ font-size: 1.6em; font-weight: bold; text-align: center; }}
.lvl1 {{ margin-inline-start: 1.5em; }} .lvl2 {{ margin-inline-start: 3em; }} .lvl3 {{ margin-inline-start: 4.5em; }}
table {{ border-collapse: collapse; width: 100%; margin: 0.5em 0; table-layout: fixed; }}
td, th {{ padding: 2pt 4pt; vertical-align: top; text-align: start; font-weight: normal; }}
td div, th div {{ margin: 0; }}
thead {{ display: table-header-group; }} tr {{ break-inside: avoid; }}
.ruled-all td, .ruled-all th {{ border: 0.5pt solid black; }}
.ruled-header th {{ border-bottom: 1pt solid black; }}
.ruled-rows tr {{ border-top: 0.5pt solid black; border-bottom: 0.5pt solid black; }}
.ruled-inner td, .ruled-inner th {{ border: 0.5pt solid black; }}
.ruled-inner tr:first-child td, .ruled-inner tr:first-child th {{ border-top: none; }}
.ruled-inner tr:last-child td, .ruled-inner tr:last-child th {{ border-bottom: none; }}
.ruled-inner td:first-child, .ruled-inner th:first-child {{ border-right: none; }}
.ruled-inner td:last-child, .ruled-inner th:last-child {{ border-left: none; }}
.notes {{ font-size: 0.85em; margin-top: 1.5em; }} .notes hr {{ width: 30%; margin-inline-start: 0; }}
.nref {{ font-size: 0.7em; }}
.pb {{ break-after: page; }}
{_numbering_css(doc)}
"""
    if page_layout:
        css += """
.page-columns { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10mm; }
.notes { position: fixed; bottom: 0; inset-inline: 0; }
.notes hr { margin-inline-start: 0; }
.letterhead { border-bottom: .5pt solid #555; padding-bottom: .35em; margin-bottom: .75em; font-weight: bold; }
.list { margin-inline-start: 4mm; }
"""
    policy = ""
    if embedded_fonts:
        css = _embedded_faces(m.font, embedded_fonts) + css
        css += "html { font-synthesis: none; font-variant-ligatures: none; hyphens: none; }"
        policy = (
            "<meta http-equiv=\"Content-Security-Policy\" content=\"default-src 'none'; "
            "style-src 'unsafe-inline'; font-src data:; base-uri 'none'; form-action 'none'\">"
        )
    html = (f'<!DOCTYPE html>\n<html lang="he" dir="rtl"><head><meta charset="utf-8">'
            f"{policy}<title>{escape(doc.doc_id)}</title><style>{css}</style></head><body>{''.join(body)}</body></html>\n")
    return html.encode("utf-8")
