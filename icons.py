"""Ikon toolbar yang digambar dengan QPainter (tanpa berkas SVG/PNG, mengikuti warna tema)."""
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPainterPath, QPen, QPixmap, QPolygonF

S = 20  # kotak gambar logis


def _lines(p, ys, xs):
    for y, (x1, x2) in zip(ys, xs):
        p.drawLine(QPointF(x1, y), QPointF(x2, y))


def _text(p, ch, size=15, bold=False, italic=False, family="Sans Serif", rect=None):
    f = QFont(family)
    f.setPixelSize(size)
    f.setBold(bold)
    f.setItalic(italic)
    p.setFont(f)
    p.drawText(rect or QRectF(0, 0, S, S), int(Qt.AlignmentFlag.AlignCenter), ch)


def _arrow_curve(p, flip):
    path = QPainterPath()
    path.moveTo(5, 8)
    path.cubicTo(8, 3.5, 15, 4.5, 15.5, 11)
    path.cubicTo(15.8, 14.5, 13, 16, 10, 16)
    p.drawPath(path)
    tri = QPolygonF([QPointF(2.5, 9.5), QPointF(7.5, 11), QPointF(6, 5.5)])
    p.setBrush(p.pen().color())
    p.drawPolygon(tri)


def draw(name, p: QPainter, color: QColor, accent: QColor):
    pen = QPen(color, 1.6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    if name == "bold":
        _text(p, "B", 16, bold=True)
    elif name == "italic":
        _text(p, "I", 16, italic=True, family="Serif")
    elif name == "underline":
        _text(p, "U", 14, rect=QRectF(0, -1, S, S))
        p.drawLine(QPointF(4.5, 17), QPointF(15.5, 17))
    elif name == "strike":
        _text(p, "S", 14)
        p.drawLine(QPointF(3.5, 10.5), QPointF(16.5, 10.5))
    elif name == "sup":
        _text(p, "x", 13, rect=QRectF(-1, 3, S, S))
        _text(p, "2", 9, bold=True, rect=QRectF(8, -3, S, S))
    elif name == "sub":
        _text(p, "x", 13, rect=QRectF(-1, 0, S, S))
        _text(p, "2", 9, bold=True, rect=QRectF(8, 6, S, S))
    elif name in ("textcolor", "highlight"):
        if name == "highlight":
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(accent)
            p.drawRoundedRect(QRectF(2.5, 3, 15, 11), 2, 2)
            p.setPen(pen)
        _text(p, "A", 14, bold=True, rect=QRectF(0, 0.5 if name == "textcolor" else 1, S, 14))
        if name == "textcolor":
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(accent)
            p.drawRoundedRect(QRectF(3, 15.5, 14, 3), 1.2, 1.2)
    elif name == "bullet":
        p.setBrush(color)
        for y in (5, 10, 15):
            p.drawEllipse(QPointF(4, y), 1.4, 1.4)
        p.setBrush(Qt.BrushStyle.NoBrush)
        _lines(p, (5, 10, 15), ((8, 17),) * 3)
    elif name == "number":
        for i, y in enumerate((5.5, 10.5, 15.5)):
            _text(p, str(i + 1), 7, bold=True, rect=QRectF(1, y - 4, 6, 8))
        _lines(p, (5.5, 10.5, 15.5), ((8.5, 17),) * 3)
    elif name in ("indent", "outdent"):
        _lines(p, (4.5, 15.5), ((3, 17),) * 2)
        _lines(p, (8.5, 11.5), ((9, 17),) * 2)
        tri = QPolygonF([QPointF(3, 7.5), QPointF(3, 12.5), QPointF(6.5, 10)]) if name == "indent" else \
            QPolygonF([QPointF(6.5, 7.5), QPointF(6.5, 12.5), QPointF(3, 10)])
        p.setBrush(color)
        p.drawPolygon(tri)
    elif name in ("left", "center", "right", "justify"):
        ys = (4.5, 8.5, 12.5, 16.5)
        widths = {"left": ((3, 17), (3, 12), (3, 17), (3, 10)), "center": ((3, 17), (5, 15), (3, 17), (6, 14)),
                  "right": ((3, 17), (8, 17), (3, 17), (10, 17)), "justify": ((3, 17),) * 4}[name]
        _lines(p, ys, widths)
    elif name == "link":
        p.save()
        p.translate(10, 10)
        p.rotate(-45)
        p.drawRoundedRect(QRectF(-8, -3, 9, 6), 3, 3)
        p.drawRoundedRect(QRectF(-1, -3, 9, 6), 3, 3)
        p.restore()
    elif name == "clear":
        _text(p, "T", 14, rect=QRectF(-1, 0, S, S))
        p.drawLine(QPointF(11, 11), QPointF(17, 17))
        p.drawLine(QPointF(17, 11), QPointF(11, 17))
    elif name == "undo":
        _arrow_curve(p, False)
    elif name == "redo":
        p.save()
        p.translate(S, 0)
        p.scale(-1, 1)
        _arrow_curve(p, True)
        p.restore()
    elif name == "plus":
        p.drawLine(QPointF(10, 4), QPointF(10, 16))
        p.drawLine(QPointF(4, 10), QPointF(16, 10))
    elif name == "trash":
        p.drawLine(QPointF(4, 5.5), QPointF(16, 5.5))
        p.drawRect(QRectF(5.5, 7, 9, 10))
        p.drawLine(QPointF(8, 4), QPointF(12, 4))
        p.drawLine(QPointF(8.5, 9.5), QPointF(8.5, 14.5))
        p.drawLine(QPointF(11.5, 9.5), QPointF(11.5, 14.5))
    elif name == "copy":
        p.drawRoundedRect(QRectF(7, 7, 9, 10), 1.5, 1.5)
        p.drawPolyline(QPolygonF([QPointF(5, 13), QPointF(4, 13), QPointF(4, 4), QPointF(12, 4), QPointF(12, 5)]))
    elif name in ("pdf", "word"):
        p.drawRoundedRect(QRectF(3, 2.5, 14, 15), 2, 2)
        _text(p, "PDF" if name == "pdf" else "W", 6 if name == "pdf" else 9, bold=True, rect=QRectF(3, 2.5, 14, 15))
    elif name == "eye":
        path = QPainterPath()
        path.moveTo(2, 10)
        path.quadTo(10, 1.5, 18, 10)
        path.quadTo(10, 18.5, 2, 10)
        p.drawPath(path)
        p.drawEllipse(QPointF(10, 10), 2.6, 2.6)
    elif name == "sidebar":
        p.drawRoundedRect(QRectF(3, 4, 14, 12), 2, 2)
        p.drawLine(QPointF(8, 4), QPointF(8, 16))
    elif name == "search":
        p.drawEllipse(QPointF(8.5, 8.5), 4.5, 4.5)
        p.drawLine(QPointF(12, 12), QPointF(16.5, 16.5))
    elif name == "cornell":
        p.drawRoundedRect(QRectF(3, 3, 14, 14), 2, 2)
        p.drawLine(QPointF(8, 3), QPointF(8, 13))
        p.drawLine(QPointF(3, 13), QPointF(17, 13))


def make_icon(name: str, color: QColor, accent: QColor | None = None, px: int = S) -> QIcon:
    scale = 2.0
    pm = QPixmap(int(px * scale), int(px * scale))
    pm.setDevicePixelRatio(scale)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    p.scale(px / S, px / S)
    draw(name, p, color, accent or color)
    p.end()
    icon = QIcon(pm)
    dis = QPixmap(pm)
    dp = QPainter(dis)
    dp.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationIn)
    dp.fillRect(dis.rect(), QColor(0, 0, 0, 90))
    dp.end()
    icon.addPixmap(dis, QIcon.Mode.Disabled)
    return icon
