"""DOCX writer: raw WordprocessingML from a source tree, byte-reproducible.

The style follows `heocr`'s tests/synth/docx.py (copied in spirit, not imported; nothing is copied verbatim). Real
`numbering.xml`, styles with outline levels, footnotes and endnotes with separators, a header and a footer with PAGE
and NUMPAGES fields, RTL tables (`bidiVisual`) with `gridSpan` and `vMerge`, and repeated header rows.

Tree columns are logical: column 0 is the start column (rightmost in an RTL table), which is also the first `w:tc` in
a `bidiVisual` table.
"""
from __future__ import annotations

import io
import zipfile
from xml.sax.saxutils import escape, quoteattr

from ..tree import Document, Heading, NoteAnchor, PageBreak, Paragraph, Run, Table

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
NS = f'xmlns:w="{W}" xmlns:r="{R}"'
REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/"
CT = "application/vnd.openxmlformats-officedocument.wordprocessingml."
PAGE = {"A4": (11906, 16838), "Letter": (12240, 15840)}
DOCX_EPOCH = (1980, 1, 1, 0, 0, 0)
XML_DECL = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
JC = {"start": None, "justify": "both", "center": "center", "end": "end"}
STYLE_OF = {"title": "Title"}


def _t(text: str) -> str:
    return f'<w:t xml:space="preserve">{escape(text)}</w:t>'


def _rpr(r: Run, extra: str = "") -> str:
    parts = []
    if r.bold:
        parts.append("<w:b/><w:bCs/>")
    if r.italic:
        parts.append("<w:i/><w:iCs/>")
    if r.lang == "he":
        parts.append("<w:rtl/>")
    parts.append(extra)
    inner = "".join(parts)
    return f"<w:rPr>{inner}</w:rPr>" if inner else ""


def _run(r: Run) -> str:
    if r.field:
        instr = {"page": " PAGE ", "numpages": " NUMPAGES "}[r.field]
        return f'<w:fldSimple w:instr={quoteattr(instr)}><w:r>{_rpr(r)}{_t(r.text)}</w:r></w:fldSimple>'
    return f"<w:r>{_rpr(r)}{_t(r.text)}</w:r>"


class _Notes:
    def __init__(self):
        self.ids: dict[str, tuple[str, int]] = {}      # note id -> (kind, w:id)
        self.next = {"footnote": 1, "endnote": 1}

    def ref(self, note_id: str, kind: str) -> str:
        if note_id not in self.ids:
            self.ids[note_id] = (kind, self.next[kind])
            self.next[kind] += 1
        _, wid = self.ids[note_id]
        style = "FootnoteReference" if kind == "footnote" else "EndnoteReference"
        return f'<w:r><w:rPr><w:rStyle w:val="{style}"/></w:rPr><w:{kind}Reference w:id="{wid}"/></w:r>'


def _runs_with_anchors(runs: list[Run], anchors: list[NoteAnchor], notes: _Notes, kinds: dict[str, str]) -> str:
    pending = sorted(anchors, key=lambda a: a.offset)
    out, pos = [], 0
    for r in runs:
        if r.field is not None:
            out.append(_run(r))
            continue
        text = r.text
        while pending and pos <= pending[0].offset <= pos + len(text):
            a = pending.pop(0)
            k = a.offset - pos
            if k:
                out.append(_run(Run(text[:k], r.lang, r.bold, r.italic)))
            out.append(notes.ref(a.note_id, kinds[a.note_id]))
            text, pos = text[k:], a.offset
        if text:
            out.append(_run(Run(text, r.lang, r.bold, r.italic)))
        pos += len(text)
    for a in pending:                                  # anchors at the very end of an empty run list
        out.append(notes.ref(a.note_id, kinds[a.note_id]))
    return "".join(out)


def _ppr(p: Paragraph | Heading, style: str | None = None) -> str:
    parts = []
    st = style or (f"Heading{p.level}" if isinstance(p, Heading) else STYLE_OF.get(p.style or ""))
    if st:
        parts.append(f'<w:pStyle w:val="{st}"/>')
    if p.num is not None:
        parts.append(f'<w:numPr><w:ilvl w:val="{p.num.level}"/><w:numId w:val="{p.num.num_id}"/></w:numPr>')
    parts.append("<w:bidi/>")
    jc = JC.get(getattr(p, "align", "start"))
    if jc:
        parts.append(f'<w:jc w:val="{jc}"/>')
    return f"<w:pPr>{''.join(parts)}</w:pPr>"


def _para(p: Paragraph | Heading, notes: _Notes, kinds: dict[str, str], style: str | None = None) -> str:
    return f"<w:p>{_ppr(p, style)}{_runs_with_anchors(p.runs, p.notes, notes, kinds)}</w:p>"


def _borders(ruled: str) -> str:
    def b(names):
        return "".join(f'<w:{n} w:val="single" w:sz="4" w:space="0" w:color="000000"/>' for n in names)
    if ruled == "all":
        return f"<w:tblBorders>{b(['top', 'left', 'bottom', 'right', 'insideH', 'insideV'])}</w:tblBorders>"
    if ruled == "rows":
        return f"<w:tblBorders>{b(['top', 'bottom', 'insideH'])}</w:tblBorders>"
    nil = "".join(f'<w:{n} w:val="nil"/>' for n in ["top", "left", "bottom", "right", "insideH", "insideV"])
    return f"<w:tblBorders>{nil}</w:tblBorders>"


def _table(t: Table, notes: _Notes, kinds: dict[str, str], text_width: int) -> str:
    widths = t.col_widths or [1.0] * t.cols
    total = sum(widths)
    tw = [max(200, int(text_width * w / total)) for w in widths]
    origin = {}
    for cell in t.cells:
        for rr in range(cell.r, cell.r + cell.rowspan):
            for cc in range(cell.c, cell.c + cell.colspan):
                origin[(rr, cc)] = cell
    header_rows = {c.r for c in t.cells if c.header}
    rows = []
    for r in range(t.rows):
        trpr = "<w:trPr><w:tblHeader/></w:trPr>" if (r in header_rows and t.repeat_header) else ""
        tcs, c = [], 0
        while c < t.cols:
            cell = origin[(r, c)]
            width = sum(tw[cell.c:cell.c + cell.colspan])
            tcpr = [f'<w:tcW w:w="{width}" w:type="dxa"/>']
            if cell.colspan > 1:
                tcpr.append(f'<w:gridSpan w:val="{cell.colspan}"/>')
            if cell.rowspan > 1:
                tcpr.append('<w:vMerge w:val="restart"/>' if cell.r == r else "<w:vMerge/>")
            if t.ruled == "header" and cell.header:
                tcpr.append('<w:tcBorders><w:bottom w:val="single" w:sz="8" w:space="0" w:color="000000"/></w:tcBorders>')
            if cell.r == r:
                content = "".join(_para(p, notes, kinds) for p in cell.paragraphs) or "<w:p><w:pPr><w:bidi/></w:pPr></w:p>"
            else:
                content = "<w:p><w:pPr><w:bidi/></w:pPr></w:p>"
            tcs.append(f"<w:tc><w:tcPr>{''.join(tcpr)}</w:tcPr>{content}</w:tc>")
            c += cell.colspan
        rows.append(f"<w:tr>{trpr}{''.join(tcs)}</w:tr>")
    grid = "".join(f'<w:gridCol w:w="{w}"/>' for w in tw)
    tblpr = (f'<w:tblPr><w:bidiVisual/><w:tblW w:w="{sum(tw)}" w:type="dxa"/>{_borders(t.ruled)}'
             f'<w:tblLayout w:type="fixed"/><w:tblCellMar><w:start w:w="80" w:type="dxa"/>'
             f'<w:end w:w="80" w:type="dxa"/></w:tblCellMar></w:tblPr>')
    return f"<w:tbl>{tblpr}<w:tblGrid>{grid}</w:tblGrid>{''.join(rows)}</w:tbl>"


def _styles(doc: Document) -> str:
    f = escape(doc.meta.font)
    sz = int(doc.meta.font_size_pt * 2)
    heads = "".join(
        f'<w:style w:type="paragraph" w:styleId="Heading{i}"><w:name w:val="heading {i}"/><w:basedOn w:val="Normal"/>'
        f'<w:next w:val="Normal"/><w:qFormat/><w:pPr><w:keepNext/><w:spacing w:before="{240 - 40 * i}" w:after="80"/>'
        f'<w:outlineLvl w:val="{i - 1}"/></w:pPr><w:rPr><w:b/><w:bCs/><w:sz w:val="{sz + 2 * (5 - i)}"/>'
        f'<w:szCs w:val="{sz + 2 * (5 - i)}"/></w:rPr></w:style>' for i in range(1, 5))

    def simple(sid, name, ppr="", rpr="", kind="paragraph"):
        return (f'<w:style w:type="{kind}" w:styleId="{sid}"><w:name w:val="{name}"/>'
                + ('<w:basedOn w:val="Normal"/>' if kind == "paragraph" else "")
                + (f"<w:pPr>{ppr}</w:pPr>" if ppr else "") + (f"<w:rPr>{rpr}</w:rPr>" if rpr else "") + "</w:style>")
    small = f'<w:sz w:val="{sz - 4}"/><w:szCs w:val="{sz - 4}"/>'
    sup = '<w:vertAlign w:val="superscript"/>'
    return (XML_DECL + f'<w:styles {NS}><w:docDefaults><w:rPrDefault><w:rPr>'
            f'<w:rFonts w:ascii="{f}" w:hAnsi="{f}" w:cs="{f}" w:eastAsia="{f}"/><w:sz w:val="{sz}"/>'
            f'<w:szCs w:val="{sz}"/><w:lang w:val="en-US" w:bidi="he-IL"/></w:rPr></w:rPrDefault>'
            f'<w:pPrDefault><w:pPr><w:spacing w:after="120" w:line="264" w:lineRule="auto"/></w:pPr></w:pPrDefault>'
            f'</w:docDefaults>'
            f'<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/><w:qFormat/>'
            f'<w:pPr><w:bidi/></w:pPr></w:style>'
            + heads
            + simple("Title", "Title", '<w:jc w:val="center"/><w:spacing w:after="200"/>',
                     f'<w:b/><w:bCs/><w:sz w:val="{sz + 12}"/><w:szCs w:val="{sz + 12}"/>')
            + simple("FootnoteText", "footnote text", '<w:spacing w:after="0"/>', small)
            + simple("EndnoteText", "endnote text", '<w:spacing w:after="0"/>', small)
            + simple("Header", "header", '<w:spacing w:after="0"/>', small)
            + simple("Footer", "footer", '<w:spacing w:after="0"/>', small)
            + simple("FootnoteReference", "footnote reference", rpr=sup, kind="character")
            + simple("EndnoteReference", "endnote reference", rpr=sup, kind="character")
            + "</w:styles>")


def _numbering(doc: Document) -> str:
    out = []
    for a in doc.abstract_nums:
        lvls = []
        for i, lv in enumerate(a.levels):
            restart = f'<w:lvlRestart w:val="{lv.restart}"/>' if lv.restart is not None else ""
            ind = 360 * (i + 1) + (360 if lv.fmt != "bullet" else 0) * (1 if i else 0)
            lvls.append(f'<w:lvl w:ilvl="{i}"><w:start w:val="{lv.start}"/><w:numFmt w:val="{lv.fmt}"/>{restart}'
                        f'<w:lvlText w:val={quoteattr(lv.text)}/><w:lvlJc w:val="left"/>'
                        f'<w:pPr><w:ind w:start="{ind + 360}" w:hanging="{360 + 180 * i}"/></w:pPr></w:lvl>')
        out.append(f'<w:abstractNum w:abstractNumId="{a.id}"><w:multiLevelType w:val="multilevel"/>'
                   f'{"".join(lvls)}</w:abstractNum>')
    for n in doc.nums:
        ov = "".join(f'<w:lvlOverride w:ilvl="{lvl}"><w:startOverride w:val="{s}"/></w:lvlOverride>'
                     for lvl, s in sorted(n.start_override.items()))
        out.append(f'<w:num w:numId="{n.id}"><w:abstractNumId w:val="{n.abstract}"/>{ov}</w:num>')
    return XML_DECL + f'<w:numbering {NS}>{"".join(out)}</w:numbering>'


def _notes_part(doc: Document, kind: str, notes: _Notes, kinds: dict[str, str]) -> str:
    tag = kind
    style = "FootnoteText" if kind == "footnote" else "EndnoteText"
    refstyle = "FootnoteReference" if kind == "footnote" else "EndnoteReference"
    parts = [f'<w:{tag} w:type="separator" w:id="-1"><w:p><w:pPr><w:spacing w:after="0"/></w:pPr>'
             f'<w:r><w:separator/></w:r></w:p></w:{tag}>',
             f'<w:{tag} w:type="continuationSeparator" w:id="0"><w:p><w:pPr><w:spacing w:after="0"/></w:pPr>'
             f'<w:r><w:continuationSeparator/></w:r></w:p></w:{tag}>']
    by_id = {n.id: n for n in doc.notes}
    for note_id, (k, wid) in sorted(notes.ids.items(), key=lambda x: x[1][1]):
        if k != kind:
            continue
        paras = []
        for i, p in enumerate(by_id[note_id].paragraphs):
            mark = (f'<w:r><w:rPr><w:rStyle w:val="{refstyle}"/></w:rPr><w:{kind}Ref/></w:r>'
                    f'<w:r>{_t(" ")}</w:r>') if i == 0 else ""
            paras.append(f'<w:p><w:pPr><w:pStyle w:val="{style}"/><w:bidi/></w:pPr>{mark}'
                         f'{_runs_with_anchors(p.runs, [], notes, kinds)}</w:p>')
        parts.append(f'<w:{tag} w:id="{wid}">{"".join(paras)}</w:{tag}>')
    return XML_DECL + f'<w:{tag}s {NS}>{"".join(parts)}</w:{tag}s>'


def _hf(paras, tag: str, style: str, notes, kinds) -> str:
    body = "".join(_para(p, notes, kinds, style) for p in paras) or f'<w:p><w:pPr><w:pStyle w:val="{style}"/></w:pPr></w:p>'
    return XML_DECL + f"<w:{tag} {NS}>{body}</w:{tag}>"


def write(doc: Document) -> bytes:
    kinds = {n.id: n.kind for n in doc.notes}
    notes = _Notes()
    pw, ph = PAGE[doc.meta.page]
    if doc.meta.orientation == "landscape":
        pw, ph = ph, pw
    margin = 1134
    text_width = pw - 2 * margin
    body = []
    for b in doc.body:
        if isinstance(b, PageBreak):
            body.append('<w:p><w:r><w:br w:type="page"/></w:r></w:p>')
        elif isinstance(b, Table):
            body.append(_table(b, notes, kinds, text_width))
        else:
            body.append(_para(b, notes, kinds))
    orient = ' w:orient="landscape"' if doc.meta.orientation == "landscape" else ""
    cols = f'<w:cols w:num="{doc.meta.columns}" w:space="567"/>' if doc.meta.columns > 1 else '<w:cols w:space="708"/>'
    sect = (f'<w:sectPr><w:headerReference w:type="default" r:id="rIdHeader1"/>'
            f'<w:footerReference w:type="default" r:id="rIdFooter1"/>'
            f'<w:pgSz w:w="{pw}" w:h="{ph}"{orient}/><w:pgMar w:top="1134" w:right="{margin}" w:bottom="1134" '
            f'w:left="{margin}" w:header="567" w:footer="567" w:gutter="0"/>{cols}<w:bidi/></w:sectPr>')
    document = XML_DECL + f'<w:document {NS}><w:body>{"".join(body)}{sect}</w:body></w:document>'
    header = _hf(doc.furniture.header, "hdr", "Header", notes, kinds)
    footer = _hf(doc.furniture.footer, "ftr", "Footer", notes, kinds)
    footnotes = _notes_part(doc, "footnote", notes, kinds)
    endnotes = _notes_part(doc, "endnote", notes, kinds)
    settings = (XML_DECL + f'<w:settings {NS}><w:defaultTabStop w:val="720"/><w:characterSpacingControl w:val="doNotCompress"/>'
                '<w:footnotePr><w:footnote w:id="-1"/><w:footnote w:id="0"/></w:footnotePr>'
                '<w:endnotePr><w:endnote w:id="-1"/><w:endnote w:id="0"/></w:endnotePr>'
                '<w:compat><w:compatSetting w:name="compatibilityMode" w:uri="http://schemas.microsoft.com/office/word" '
                'w:val="15"/></w:compat><w:themeFontLang w:val="en-US" w:bidi="he-IL"/></w:settings>')
    rels = (XML_DECL + '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            f'<Relationship Id="rIdStyles" Type="{REL}styles" Target="styles.xml"/>'
            f'<Relationship Id="rIdNumbering" Type="{REL}numbering" Target="numbering.xml"/>'
            f'<Relationship Id="rIdSettings" Type="{REL}settings" Target="settings.xml"/>'
            f'<Relationship Id="rIdFootnotes" Type="{REL}footnotes" Target="footnotes.xml"/>'
            f'<Relationship Id="rIdEndnotes" Type="{REL}endnotes" Target="endnotes.xml"/>'
            f'<Relationship Id="rIdHeader1" Type="{REL}header" Target="header1.xml"/>'
            f'<Relationship Id="rIdFooter1" Type="{REL}footer" Target="footer1.xml"/>'
            '</Relationships>')
    root_rels = (XML_DECL + '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                 f'<Relationship Id="rId1" Type="{REL}officeDocument" Target="word/document.xml"/>'
                 '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/'
                 'core-properties" Target="docProps/core.xml"/>'
                 f'<Relationship Id="rId3" Type="{REL}extended-properties" Target="docProps/app.xml"/>'
                 '</Relationships>')
    ct = (XML_DECL + '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
          '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
          '<Default Extension="xml" ContentType="application/xml"/>'
          f'<Override PartName="/word/document.xml" ContentType="{CT}document.main+xml"/>'
          f'<Override PartName="/word/styles.xml" ContentType="{CT}styles+xml"/>'
          f'<Override PartName="/word/numbering.xml" ContentType="{CT}numbering+xml"/>'
          f'<Override PartName="/word/settings.xml" ContentType="{CT}settings+xml"/>'
          f'<Override PartName="/word/footnotes.xml" ContentType="{CT}footnotes+xml"/>'
          f'<Override PartName="/word/endnotes.xml" ContentType="{CT}endnotes+xml"/>'
          f'<Override PartName="/word/header1.xml" ContentType="{CT}header+xml"/>'
          f'<Override PartName="/word/footer1.xml" ContentType="{CT}footer+xml"/>'
          '<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>'
          '<Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>'
          '</Types>')
    core = (XML_DECL + '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
            'xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" '
            'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
            f'<dc:title>{escape(doc.doc_id)}</dc:title><dc:creator>hdocsyngen</dc:creator>'
            '<dcterms:created xsi:type="dcterms:W3CDTF">2026-01-01T00:00:00Z</dcterms:created>'
            '<dcterms:modified xsi:type="dcterms:W3CDTF">2026-01-01T00:00:00Z</dcterms:modified>'
            '</cp:coreProperties>')
    app = (XML_DECL + '<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties">'
           '<Application>hdocsyngen</Application></Properties>')
    parts = [("[Content_Types].xml", ct), ("_rels/.rels", root_rels), ("docProps/core.xml", core),
             ("docProps/app.xml", app), ("word/document.xml", document), ("word/_rels/document.xml.rels", rels),
             ("word/styles.xml", _styles(doc)), ("word/numbering.xml", _numbering(doc)),
             ("word/settings.xml", settings), ("word/footnotes.xml", footnotes), ("word/endnotes.xml", endnotes),
             ("word/header1.xml", header), ("word/footer1.xml", footer)]
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, data in parts:
            info = zipfile.ZipInfo(name, DOCX_EPOCH)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            z.writestr(info, data.encode("utf-8"))
    return buf.getvalue()
