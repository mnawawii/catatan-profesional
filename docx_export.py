"""Ekspor catatan ke Word (.docx) tanpa pustaka tambahan: penulis OOXML minimal.

Tata letak: tabel Cornell (kepala, kolom Petunjuk | Catatan, lalu Ringkasan). Mendukung tebal, miring,
garis bawah, coret, warna teks, sorotan, ukuran dan jenis huruf, subskrip/superskrip, judul, rata teks,
daftar bullet dan bernomor (bertingkat), serta tautan.
"""
import re
import zipfile
from datetime import date, datetime
from xml.sax.saxutils import escape

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QTextCharFormat, QTextDocument, QTextFormat, QTextListFormat

from pdf_export import BULAN, DEFAULT_FONT, format_date

W_NS = ('xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"')
_BAD = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\ufffe\uffff]")

PAPERS = {"A4": (11906, 16838), "Letter": (12240, 15840), "Legal": (12240, 20160)}
MARGIN = 1134  # 2 cm


def esc(s: str) -> str:
    return escape(_BAD.sub("", s))


def _hex(color) -> str:
    return f"{color.red():02X}{color.green():02X}{color.blue():02X}"


class Builder:
    def __init__(self):
        self.rels: list[tuple[str, str]] = []     # (rId, url) untuk tautan
        self.abstract: list[str] = []             # xml abstractNum
        self.nums: list[int] = []                 # numId -> abstractId
        self.list_ids: dict[int, int] = {}        # kunci daftar Qt -> numId
        self.default_family = DEFAULT_FONT[0]
        self.default_pt = DEFAULT_FONT[1]

    # ------------------------------------------------------------- run
    def run_props(self, fmt: QTextCharFormat, heading=False, force: dict | None = None) -> str:
        p = []
        fam = ""
        if fmt.hasProperty(QTextFormat.Property.FontFamilies):
            fams = fmt.fontFamilies()
            fam = fams[0] if fams else ""
        elif fmt.hasProperty(QTextFormat.Property.FontFamily):
            fam = fmt.fontFamily()
        if fam and fam.strip("'\"") != self.default_family:
            f = esc(fam.strip("'\""))
            p.append(f'<w:rFonts w:ascii="{f}" w:hAnsi="{f}" w:cs="{f}"/>')
        bold = fmt.fontWeight() >= 600
        if bold:
            p.append("<w:b/><w:bCs/>")
        if fmt.fontItalic():
            p.append("<w:i/><w:iCs/>")
        if fmt.fontStrikeOut():
            p.append("<w:strike/>")
        fg = fmt.foreground()
        link = fmt.isAnchor()
        if link:
            p.append('<w:color w:val="0563C1"/>')
        elif fg.style() != Qt.BrushStyle.NoBrush and fg.color().isValid():
            c = _hex(fg.color())
            if c not in ("000000", "111111", "1F1F1F"):
                p.append(f'<w:color w:val="{c}"/>')
        pt = fmt.fontPointSize()
        if force and force.get("sz"):
            pt = force["sz"]
        if pt and abs(pt - self.default_pt) > 0.05:
            p.append(f'<w:sz w:val="{int(round(pt * 2))}"/><w:szCs w:val="{int(round(pt * 2))}"/>')
        bg = fmt.background()
        if bg.style() != Qt.BrushStyle.NoBrush and bg.color().isValid() and bg.color().alpha() > 0:
            pass  # dipasang sebagai shd di bawah (urutan skema: u, shd, vertAlign)
        if fmt.fontUnderline() or link:
            p.append('<w:u w:val="single"/>')
        if bg.style() != Qt.BrushStyle.NoBrush and bg.color().isValid() and bg.color().alpha() > 0:
            p.append(f'<w:shd w:val="clear" w:color="auto" w:fill="{_hex(bg.color())}"/>')
        va = fmt.verticalAlignment()
        if va == QTextCharFormat.VerticalAlignment.AlignSuperScript:
            p.append('<w:vertAlign w:val="superscript"/>')
        elif va == QTextCharFormat.VerticalAlignment.AlignSubScript:
            p.append('<w:vertAlign w:val="subscript"/>')
        return f"<w:rPr>{''.join(p)}</w:rPr>" if p else ""

    def runs(self, text: str, rpr: str) -> str:
        out = []
        for part in re.split(r"(\t|\u2028|\n)", text):
            if part == "":
                continue
            if part == "\t":
                out.append(f"<w:r>{rpr}<w:tab/></w:r>")
            elif part in ("\u2028", "\n"):
                out.append(f"<w:r>{rpr}<w:br/></w:r>")
            else:
                part = part.replace("\ufffc", "")
                if part:
                    out.append(f'<w:r>{rpr}<w:t xml:space="preserve">{esc(part)}</w:t></w:r>')
        return "".join(out)

    # ----------------------------------------------------------- daftar
    def num_id(self, tl) -> tuple[int, int]:
        lf = tl.format()
        style = lf.style()
        level = max(0, min(8, lf.indent() - 1))
        key = id_of_list(tl)
        if key not in self.list_ids:
            LS = QTextListFormat.Style
            table = {
                LS.ListDisc: ("bullet", "•", "Arial"), LS.ListCircle: ("bullet", "o", "Courier New"),
                LS.ListSquare: ("bullet", "▪", "Arial"), LS.ListDecimal: ("decimal", "%{n}.", None),
                LS.ListLowerAlpha: ("lowerLetter", "%{n}.", None), LS.ListUpperAlpha: ("upperLetter", "%{n}.", None),
                LS.ListLowerRoman: ("lowerRoman", "%{n}.", None), LS.ListUpperRoman: ("upperRoman", "%{n}.", None),
            }
            fmt_name, txt, font = table.get(style, ("bullet", "•", "Arial"))
            start = max(1, lf.start()) if fmt_name != "bullet" else 1
            lvls = []
            for i in range(9):
                t = txt.replace("{n}", str(i + 1))
                rpr = f'<w:rPr><w:rFonts w:ascii="{font}" w:hAnsi="{font}" w:cs="{font}" w:hint="default"/></w:rPr>' if font else ""
                lvls.append(
                    f'<w:lvl w:ilvl="{i}"><w:start w:val="{start}"/><w:numFmt w:val="{fmt_name}"/>'
                    f'<w:lvlText w:val="{esc(t)}"/><w:lvlJc w:val="left"/>'
                    f'<w:pPr><w:ind w:left="{720 * (i + 1)}" w:hanging="360"/></w:pPr>{rpr}</w:lvl>')
            aid = len(self.abstract)
            self.abstract.append(f'<w:abstractNum w:abstractNumId="{aid}"><w:multiLevelType w:val="hybridMultilevel"/>'
                                 + "".join(lvls) + "</w:abstractNum>")
            self.nums.append(aid)
            self.list_ids[key] = len(self.nums)  # numId mulai dari 1
        return self.list_ids[key], level

    # --------------------------------------------------------- paragraf
    def paragraph(self, block, hyperlink_rid) -> str:
        bf = block.blockFormat()
        ppr = []
        hl = bf.headingLevel()
        if 1 <= hl <= 3:
            ppr.append(f'<w:pStyle w:val="Heading{hl}"/>')
        tl = block.textList()
        if tl:
            nid, lvl = self.num_id(tl)
            ppr.append(f'<w:numPr><w:ilvl w:val="{lvl}"/><w:numId w:val="{nid}"/></w:numPr>')
        ind = bf.indent() if not tl else 0
        if ind > 0:
            ppr.append(f'<w:ind w:left="{720 * ind}"/>')
        al = bf.alignment()
        jc = None
        if al & Qt.AlignmentFlag.AlignHCenter:
            jc = "center"
        elif al & Qt.AlignmentFlag.AlignRight:
            jc = "right"
        elif al & Qt.AlignmentFlag.AlignJustify:
            jc = "both"
        if jc:
            ppr.append(f'<w:jc w:val="{jc}"/>')
        body = []
        it = block.begin()
        while not it.atEnd():
            frag = it.fragment()
            if frag.isValid():
                fmt = frag.charFormat()
                x = self.runs(frag.text(), self.run_props(fmt, heading=hl > 0))
                if fmt.isAnchor() and fmt.anchorHref():
                    rid = hyperlink_rid(fmt.anchorHref())
                    x = f'<w:hyperlink r:id="{rid}" w:history="1">{x}</w:hyperlink>'
                body.append(x)
            it += 1
        pp = f"<w:pPr>{''.join(ppr)}</w:pPr>" if ppr else ""
        return f"<w:p>{pp}{''.join(body)}</w:p>"

    def doc_xml(self, html: str, hyperlink_rid) -> str:
        doc = QTextDocument()
        f = QFont(self.default_family)
        f.setPointSizeF(self.default_pt)
        doc.setDefaultFont(f)
        doc.setHtml(html or "")
        out = []
        b = doc.begin()
        while b.isValid():
            out.append(self.paragraph(b, hyperlink_rid))
            b = b.next()
        return "".join(out) if out else "<w:p/>"


def id_of_list(tl) -> int:
    return tl.item(0).position()


def _label(text: str) -> str:
    return (f'<w:p><w:pPr><w:spacing w:after="40"/></w:pPr><w:r><w:rPr><w:b/><w:color w:val="7A7566"/>'
            f'<w:spacing w:val="20"/><w:sz w:val="15"/></w:rPr><w:t>{esc(text)}</w:t></w:r></w:p>')


def export_docx(path: str, note: dict, paper: str = "A4", cue_ratio: float = 0.3):
    pw, ph = PAPERS.get(paper, PAPERS["A4"])
    usable = pw - 2 * MARGIN
    cue_w = int(usable * max(0.2, min(0.45, cue_ratio)))
    notes_w = usable - cue_w
    b = Builder()
    rels: dict[str, str] = {}

    def hyperlink_rid(url: str) -> str:
        if url not in rels:
            rels[url] = f"rIdL{len(rels) + 1}"
        return rels[url]

    title = (note.get("title") or "").strip() or "Tanpa judul"
    subs = []
    if (note.get("course") or "").strip():
        subs.append(f"Mata kuliah: {note['course'].strip()}")
    if note.get("date"):
        subs.append(f"Tanggal: {format_date(note['date'])}")
    border = '<w:{0} w:val="single" w:sz="6" w:space="0" w:color="6B6658"/>'
    borders = "".join(border.format(n) for n in ("top", "left", "bottom", "right", "insideH", "insideV"))
    cell_mar = '<w:tcMar><w:top w:w="80" w:type="dxa"/><w:left w:w="140" w:type="dxa"/><w:bottom w:w="80" w:type="dxa"/><w:right w:w="140" w:type="dxa"/></w:tcMar>'

    header = (f'<w:tr><w:trPr><w:cantSplit/></w:trPr><w:tc><w:tcPr><w:tcW w:w="{usable}" w:type="dxa"/><w:gridSpan w:val="2"/>'
              f'<w:shd w:val="clear" w:color="auto" w:fill="F4F1E8"/>{cell_mar}</w:tcPr>'
              f'<w:p><w:pPr><w:spacing w:after="40"/></w:pPr><w:r><w:rPr><w:b/><w:bCs/><w:sz w:val="36"/><w:szCs w:val="36"/></w:rPr>'
              f'<w:t xml:space="preserve">{esc(title)}</w:t></w:r></w:p>'
              f'<w:p><w:pPr><w:spacing w:after="0"/></w:pPr><w:r><w:rPr><w:color w:val="7A7566"/><w:sz w:val="20"/></w:rPr>'
              f'<w:t xml:space="preserve">{esc("    •    ".join(subs))}</w:t></w:r></w:p></w:tc></w:tr>')
    main = (f'<w:tr><w:tc><w:tcPr><w:tcW w:w="{cue_w}" w:type="dxa"/>{cell_mar}</w:tcPr>'
            f'{_label("PETUNJUK")}{b.doc_xml(note.get("cue", ""), hyperlink_rid)}</w:tc>'
            f'<w:tc><w:tcPr><w:tcW w:w="{notes_w}" w:type="dxa"/>{cell_mar}</w:tcPr>'
            f'{_label("CATATAN")}{b.doc_xml(note.get("notes", ""), hyperlink_rid)}</w:tc></w:tr>')
    summary = (f'<w:tr><w:tc><w:tcPr><w:tcW w:w="{usable}" w:type="dxa"/><w:gridSpan w:val="2"/>'
               f'<w:shd w:val="clear" w:color="auto" w:fill="FAF8F2"/>{cell_mar}</w:tcPr>'
               f'{_label("RINGKASAN")}{b.doc_xml(note.get("summary", ""), hyperlink_rid)}</w:tc></w:tr>')
    table = (f'<w:tbl><w:tblPr><w:tblW w:w="{usable}" w:type="dxa"/><w:tblBorders>{borders}</w:tblBorders>'
             f'<w:tblLayout w:type="fixed"/></w:tblPr><w:tblGrid><w:gridCol w:w="{cue_w}"/><w:gridCol w:w="{notes_w}"/></w:tblGrid>'
             f'{header}{main}{summary}</w:tbl>')
    document = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document {W_NS}><w:body>{table}'
                f'<w:p/><w:sectPr><w:footerReference w:type="default" r:id="rIdFooter"/>'
                f'<w:pgSz w:w="{pw}" w:h="{ph}"/><w:pgMar w:top="{MARGIN}" w:right="{MARGIN}" w:bottom="{MARGIN}" '
                f'w:left="{MARGIN}" w:header="567" w:footer="567" w:gutter="0"/></w:sectPr></w:body></w:document>')

    styles = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:styles {W_NS}>'
              f'<w:docDefaults><w:rPrDefault><w:rPr><w:rFonts w:ascii="Calibri" w:hAnsi="Calibri" w:eastAsia="Calibri" w:cs="Calibri"/>'
              f'<w:sz w:val="{int(DEFAULT_FONT[1] * 2)}"/><w:szCs w:val="{int(DEFAULT_FONT[1] * 2)}"/><w:lang w:val="id-ID"/></w:rPr></w:rPrDefault>'
              f'<w:pPrDefault><w:pPr><w:spacing w:after="80" w:line="264" w:lineRule="auto"/></w:pPr></w:pPrDefault></w:docDefaults>'
              f'<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/><w:qFormat/></w:style>'
              + "".join(
                  f'<w:style w:type="paragraph" w:styleId="Heading{i}"><w:name w:val="heading {i}"/><w:basedOn w:val="Normal"/>'
                  f'<w:next w:val="Normal"/><w:qFormat/><w:pPr><w:keepNext/><w:spacing w:before="160" w:after="80"/><w:outlineLvl w:val="{i - 1}"/></w:pPr>'
                  f'<w:rPr><w:b/><w:bCs/><w:sz w:val="{sz}"/><w:szCs w:val="{sz}"/></w:rPr></w:style>'
                  for i, sz in ((1, 40), (2, 32), (3, 26)))
              + '</w:styles>')
    numbering = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:numbering {W_NS}>' + "".join(b.abstract)
                 + "".join(f'<w:num w:numId="{i + 1}"><w:abstractNumId w:val="{aid}"/></w:num>' for i, aid in enumerate(b.nums))
                 + "</w:numbering>")
    footer = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:ftr {W_NS}><w:p><w:pPr><w:jc w:val="right"/></w:pPr>'
              f'<w:r><w:rPr><w:color w:val="7A7566"/><w:sz w:val="16"/></w:rPr><w:t xml:space="preserve">Halaman </w:t></w:r>'
              f'<w:r><w:rPr><w:color w:val="7A7566"/><w:sz w:val="16"/></w:rPr><w:fldChar w:fldCharType="begin"/></w:r>'
              f'<w:r><w:rPr><w:color w:val="7A7566"/><w:sz w:val="16"/></w:rPr><w:instrText xml:space="preserve"> PAGE </w:instrText></w:r>'
              f'<w:r><w:rPr><w:color w:val="7A7566"/><w:sz w:val="16"/></w:rPr><w:fldChar w:fldCharType="separate"/></w:r>'
              f'<w:r><w:rPr><w:color w:val="7A7566"/><w:sz w:val="16"/></w:rPr><w:t>1</w:t></w:r>'
              f'<w:r><w:rPr><w:color w:val="7A7566"/><w:sz w:val="16"/></w:rPr><w:fldChar w:fldCharType="end"/></w:r></w:p></w:ftr>')
    rel_items = ('<Relationship Id="rIdStyles" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
                 '<Relationship Id="rIdNum" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/numbering" Target="numbering.xml"/>'
                 '<Relationship Id="rIdFooter" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/footer" Target="footer1.xml"/>'
                 + "".join(f'<Relationship Id="{rid}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink" '
                           f'Target="{esc(url)}" TargetMode="External"/>' for url, rid in rels.items()))
    doc_rels = f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">{rel_items}</Relationships>'
    content_types = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                     '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                     '<Default Extension="xml" ContentType="application/xml"/>'
                     '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
                     '<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>'
                     '<Override PartName="/word/numbering.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.numbering+xml"/>'
                     '<Override PartName="/word/footer1.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.footer+xml"/>'
                     '<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>'
                     '<Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/></Types>')
    root_rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                 '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
                 '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>'
                 '<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/></Relationships>')
    now = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    core = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
            'xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
            f'<dc:title>{esc(title)}</dc:title><dc:creator>Catatan Cornell</dc:creator>'
            f'<dcterms:created xsi:type="dcterms:W3CDTF">{now}</dcterms:created><dcterms:modified xsi:type="dcterms:W3CDTF">{now}</dcterms:modified></cp:coreProperties>')
    app = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties">'
           '<Application>Catatan Cornell</Application></Properties>')

    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", content_types)
        z.writestr("_rels/.rels", root_rels)
        z.writestr("word/document.xml", document)
        z.writestr("word/styles.xml", styles)
        z.writestr("word/numbering.xml", numbering)
        z.writestr("word/footer1.xml", footer)
        z.writestr("word/_rels/document.xml.rels", doc_rels)
        z.writestr("docProps/core.xml", core)
        z.writestr("docProps/app.xml", app)
