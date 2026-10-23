"""Ekspor catatan ke PDF dengan tata letak Cornell (tanpa pustaka tambahan).

Per halaman: kepala (topik, mata kuliah, tanggal), kolom Petunjuk di kiri dan Catatan di kanan
(mengalir ke halaman berikutnya bila panjang), dan kotak Ringkasan di bagian bawah halaman terakhir.
"""
import math
from datetime import date

from PySide6.QtCore import QMarginsF, QRectF, QSizeF, Qt
from PySide6.QtGui import (QColor, QFont, QFontMetricsF, QPageLayout, QPageSize, QPainter, QPdfWriter,
                           QPen, QTextDocument)

DEFAULT_FONT = ("Sans Serif", 11)
DPI = 300
BULAN = ["Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli", "Agustus", "September",
         "Oktober", "November", "Desember"]

PAPERS = {"A4": QPageSize.PageSizeId.A4, "Letter": QPageSize.PageSizeId.Letter, "Legal": QPageSize.PageSizeId.Legal}


def format_date(iso: str) -> str:
    try:
        d = date.fromisoformat(iso)
        return f"{d.day} {BULAN[d.month - 1]} {d.year}"
    except (ValueError, TypeError):
        return iso or ""


def make_doc(html: str, width: float, page_h: float, device) -> QTextDocument:
    doc = QTextDocument()
    doc.documentLayout().setPaintDevice(device)
    doc.setDocumentMargin(0)
    f = QFont(DEFAULT_FONT[0])
    f.setPointSizeF(DEFAULT_FONT[1])
    doc.setDefaultFont(f)
    doc.setDefaultStyleSheet("body { color: #111111; }")
    doc.setHtml(html or "")
    doc.setPageSize(QSizeF(width, page_h))
    return doc


def content_bottom(doc: QTextDocument) -> float:
    if doc.isEmpty():
        return 0.0
    blk = doc.lastBlock()
    return doc.documentLayout().blockBoundingRect(blk).bottom()


def export_pdf(path: str, note: dict, paper: str = "A4", cue_ratio: float = 0.3) -> int:
    """Menulis PDF ke `path`. Mengembalikan jumlah halaman."""
    w = QPdfWriter(path)
    w.setResolution(DPI)
    w.setPageSize(QPageSize(PAPERS.get(paper, PAPERS["A4"])))
    w.setPageMargins(QMarginsF(0, 0, 0, 0), QPageLayout.Unit.Millimeter)
    w.setTitle(note.get("title") or "Catatan Cornell")
    w.setCreator("Catatan Cornell")

    mm = DPI / 25.4
    PW, PH = float(w.width()), float(w.height())
    M = 14 * mm                          # margin halaman
    pad = 3.2 * mm                       # ruang dalam kolom
    label_h = 6.5 * mm
    header_h = 21 * mm
    gap = 3 * mm
    left, right = M, PW - M
    content_w = right - left
    cue_w = content_w * max(0.2, min(0.45, cue_ratio))
    notes_w = content_w - cue_w
    body_top = M + header_h + gap
    body_bottom = PH - M - 5 * mm        # sisakan ruang nomor halaman
    body_h = body_bottom - body_top
    A = body_h - label_h - pad           # tinggi isi per halaman (kolom)

    cue_doc = make_doc(note.get("cue", ""), cue_w - 2 * pad, A, w)
    notes_doc = make_doc(note.get("notes", ""), notes_w - 2 * pad, A, w)
    sum_doc = make_doc(note.get("summary", ""), content_w - 2 * pad, 10 ** 7, w)

    def pages_of(doc):
        b = content_bottom(doc)
        if b <= 0:
            return 1, 0.0
        n = max(1, math.ceil(b / A - 1e-6))
        return n, b - (n - 1) * A

    pc, rc = pages_of(cue_doc)
    pn, rn = pages_of(notes_doc)
    body_pages = max(pc, pn)
    last_r = max(rc if pc == body_pages else 0.0, rn if pn == body_pages else 0.0)

    sum_text_h = content_bottom(sum_doc)
    sum_h = label_h + max(sum_text_h, 14 * mm) + pad * 1.2
    cap = body_h * 0.62
    sum_overflow = sum_h > cap
    vis_last = body_h - sum_h - gap - label_h - pad * 0.6
    summary_idx = None
    if not sum_overflow:
        fits_on_last = last_r <= vis_last
        total_pages = body_pages + (0 if fits_on_last else 1)
        summary_pages = []
        summary_idx = body_pages - 1 if fits_on_last else body_pages
    else:
        # ringkasan sangat panjang: dialirkan pada halaman tersendiri di akhir
        sum_doc.setPageSize(QSizeF(content_w - 2 * pad, A))
        n_sum = max(1, math.ceil(content_bottom(sum_doc) / A - 1e-6))
        total_pages = body_pages + n_sum
        summary_pages = list(range(n_sum))

    ink = QColor("#1F1F1F")
    muted = QColor("#7A7566")
    line = QColor("#6B6658")
    soft = QColor("#CFC9B8")

    p = QPainter(w)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.TextAntialiasing)

    def font(pt, bold=False, spacing=0.0):
        f = QFont(DEFAULT_FONT[0])
        f.setPointSizeF(pt)
        f.setBold(bold)
        if spacing:
            f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, spacing)
        return f

    title = (note.get("title") or "").strip() or "Tanpa judul"
    sub_parts = []
    if (note.get("course") or "").strip():
        sub_parts.append(f"Mata kuliah: {note['course'].strip()}")
    if note.get("date"):
        sub_parts.append(f"Tanggal: {format_date(note['date'])}")
    subtitle = "    •    ".join(sub_parts)

    def draw_header(page_no):
        p.setPen(ink)
        p.setFont(font(19, True))
        fm = QFontMetricsF(p.font())
        p.drawText(QRectF(left, M, content_w, 9 * mm), int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
                   fm.elidedText(title, Qt.TextElideMode.ElideRight, content_w))
        p.setPen(muted)
        p.setFont(font(10))
        p.drawText(QRectF(left, M + 10 * mm, content_w, 6 * mm),
                   int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
                   QFontMetricsF(p.font()).elidedText(subtitle, Qt.TextElideMode.ElideRight, content_w))
        p.setPen(QPen(line, 0.35 * mm))
        p.drawLine(int(left), int(M + header_h - 1.5 * mm), int(right), int(M + header_h - 1.5 * mm))
        p.setPen(muted)
        p.setFont(font(8))
        p.drawText(QRectF(left, PH - M - 3.5 * mm, content_w, 4 * mm),
                   int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter),
                   f"Halaman {page_no} dari {total_pages}")

    def draw_label(text, x, y, wid):
        p.setPen(muted)
        p.setFont(font(7.5, True, 1.4 * mm / 4))
        p.drawText(QRectF(x + pad, y, wid - 2 * pad, label_h), int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter), text)

    def draw_doc(doc, x, y, k, wid, hei):
        p.save()
        p.setClipRect(QRectF(x, y, wid, hei))
        p.translate(x, y - k * A)
        doc.drawContents(p, QRectF(0, k * A, wid, hei))
        p.restore()

    def draw_summary_box(sy):
        p.setPen(QPen(line, 0.3 * mm))
        p.drawRect(QRectF(left, sy, content_w, sum_h))
        draw_label("RINGKASAN", left, sy, content_w)
        p.setPen(QPen(soft, 0.2 * mm))
        p.drawLine(int(left), int(sy + label_h), int(right), int(sy + label_h))
        sum_doc.setPageSize(QSizeF(content_w - 2 * pad, 10 ** 7))
        p.save()
        p.setClipRect(QRectF(left + pad, sy + label_h + pad * 0.5, content_w - 2 * pad, sum_h - label_h - pad * 0.5))
        p.translate(left + pad, sy + label_h + pad * 0.5)
        sum_doc.drawContents(p)
        p.restore()

    for pg in range(total_pages):
        if pg > 0:
            w.newPage()
        draw_header(pg + 1)
        if pg >= body_pages:
            if summary_pages:                       # halaman lanjutan ringkasan panjang
                k = pg - body_pages
                p.setPen(QPen(line, 0.3 * mm))
                p.drawRect(QRectF(left, body_top, content_w, body_h))
                draw_label("RINGKASAN" + (" (lanjutan)" if k else ""), left, body_top, content_w)
                draw_doc(sum_doc, left + pad, body_top + label_h, k, content_w - 2 * pad, A)
            else:                                   # halaman khusus ringkasan
                draw_summary_box(body_top)
            continue

        summary_here = (pg == summary_idx)
        frame_h = body_h - sum_h - gap if summary_here else body_h
        p.setPen(QPen(line, 0.3 * mm))
        p.drawRect(QRectF(left, body_top, content_w, frame_h))
        p.drawLine(int(left + cue_w), int(body_top), int(left + cue_w), int(body_top + frame_h))
        p.setPen(QPen(soft, 0.2 * mm))
        p.drawLine(int(left), int(body_top + label_h), int(right), int(body_top + label_h))
        draw_label("PETUNJUK", left, body_top, cue_w)
        draw_label("CATATAN", left + cue_w, body_top, notes_w)
        vis_h = min(A, frame_h - label_h - pad * 0.6)
        draw_doc(cue_doc, left + pad, body_top + label_h + pad * 0.6, pg, cue_w - 2 * pad, vis_h)
        draw_doc(notes_doc, left + cue_w + pad, body_top + label_h + pad * 0.6, pg, notes_w - 2 * pad, vis_h)
        if summary_here:
            draw_summary_box(body_top + frame_h + gap)
    p.end()
    return total_pages
