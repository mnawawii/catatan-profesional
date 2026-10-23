"""RichEdit: QTextEdit dengan operasi pemformatan lengkap untuk catatan."""
import re

from PySide6.QtCore import QRegularExpression, Qt, Signal
from PySide6.QtGui import (QBrush, QColor, QFont, QKeyEvent, QTextBlockFormat, QTextCharFormat, QTextCursor,
                           QTextFormat, QTextListFormat)
from PySide6.QtWidgets import QInputDialog, QTextEdit

DEFAULT_FAMILY = "Sans Serif"
DEFAULT_SIZE = 11.0
HEADING_SIZES = {0: DEFAULT_SIZE, 1: 20.0, 2: 16.0, 3: 13.0}
LS = QTextListFormat.Style
BULLETS = {"disc": LS.ListDisc, "circle": LS.ListCircle, "square": LS.ListSquare}
NUMBERS = {"decimal": LS.ListDecimal, "lower-alpha": LS.ListLowerAlpha, "upper-alpha": LS.ListUpperAlpha,
           "lower-roman": LS.ListLowerRoman, "upper-roman": LS.ListUpperRoman}
HIGHLIGHT_COLORS = ["#FFE066", "#B8F2C8", "#FFC2D6", "#BFE0FF", "#FFD1A3", "#E0CCFF", "#E3E3E3"]
TEXT_COLORS = ["#C0392B", "#D35400", "#B7950B", "#1E8449", "#1F618D", "#7D3C98", "#566573", "#000000"]


class RichEdit(QTextEdit):
    stateChanged = Signal()
    focusedIn = Signal(object)

    def __init__(self, placeholder="", parent=None):
        super().__init__(parent)
        self.setAcceptRichText(True)
        
        # Simpan teks asli ke dalam variabel
        self._placeholder_text = placeholder
        self.setPlaceholderText(placeholder)
        
        self.document().setDocumentMargin(10)
        f = QFont(DEFAULT_FAMILY)
        f.setPointSizeF(DEFAULT_SIZE)
        self.document().setDefaultFont(f)
        self.setTabStopDistance(32)
        self.cursorPositionChanged.connect(self.stateChanged)
        self.currentCharFormatChanged.connect(lambda _f: self.stateChanged.emit())
        
        # Hubungkan sinyal perubahan teks/format ke fungsi pengecek placeholder
        self.textChanged.connect(self._check_placeholder)
        self.stateChanged.connect(self._check_placeholder)

    def _check_placeholder(self):
        """Menyembunyikan placeholder jika baris pertama memiliki format list (bullet/number)."""
        has_list = self.document().firstBlock().textList() is not None
        if has_list and self.placeholderText():
            self.setPlaceholderText("")
        elif not has_list and self.placeholderText() != self._placeholder_text:
            self.setPlaceholderText(self._placeholder_text)

    def focusInEvent(self, e):
        super().focusInEvent(e)
        self.focusedIn.emit(self)

    # ------------------------------------------------------------ bantu
    def _blocks(self):
        cur = self.textCursor()
        doc = self.document()
        b = doc.findBlock(cur.selectionStart())
        end = doc.findBlock(cur.selectionEnd()).blockNumber()
        if cur.hasSelection() and cur.selectionEnd() == end_start(doc, end) and end > b.blockNumber():
            end -= 1                                  # seleksi berakhir tepat di awal blok berikutnya
        out = []
        while b.isValid() and b.blockNumber() <= end:
            out.append(b)
            b = b.next()
        return out

    def merge(self, fmt: QTextCharFormat):
        cur = self.textCursor()
        cur.mergeCharFormat(fmt)
        self.mergeCurrentCharFormat(fmt)

    # ------------------------------------------------------- karakter
    def toggle_bold(self):
        f = QTextCharFormat()
        f.setFontWeight(400 if self.fontWeight() >= 600 else 700)
        self.merge(f)

    def toggle_italic(self):
        f = QTextCharFormat()
        f.setFontItalic(not self.fontItalic())
        self.merge(f)

    def toggle_underline(self):
        f = QTextCharFormat()
        f.setFontUnderline(not self.fontUnderline())
        self.merge(f)

    def toggle_strike(self):
        f = QTextCharFormat()
        f.setFontStrikeOut(not self.currentCharFormat().fontStrikeOut())
        self.merge(f)

    def toggle_valign(self, sup: bool):
        want = QTextCharFormat.VerticalAlignment.AlignSuperScript if sup else QTextCharFormat.VerticalAlignment.AlignSubScript
        cur = self.currentCharFormat().verticalAlignment()
        f = QTextCharFormat()
        f.setVerticalAlignment(QTextCharFormat.VerticalAlignment.AlignNormal if cur == want else want)
        self.merge(f)

    def set_family(self, family: str | None):
        f = QTextCharFormat()
        f.setFontFamilies([family or DEFAULT_FAMILY])
        self.merge(f)

    def set_size(self, pt: float):
        if pt > 0:
            f = QTextCharFormat()
            f.setFontPointSize(pt)
            self.merge(f)

    def set_text_color(self, color: QColor | None):
        f = QTextCharFormat()
        f.setForeground(QBrush(color) if color else QBrush(Qt.BrushStyle.NoBrush))
        self.merge(f)

    def set_highlight(self, color: QColor | None):
        f = QTextCharFormat()
        f.setBackground(QBrush(color) if color else QBrush(Qt.BrushStyle.NoBrush))
        self.merge(f)

    def has_highlight(self) -> bool:
        return self.currentCharFormat().background().style() != Qt.BrushStyle.NoBrush

    def toggle_highlight(self, color: QColor):
        self.set_highlight(None if self.has_highlight() else color)

    def clear_formatting(self):
        cur = self.textCursor()
        if not cur.hasSelection():
            cur.select(QTextCursor.SelectionType.WordUnderCursor)
        f = QTextCharFormat()
        f.setFontPointSize(DEFAULT_SIZE)
        cur.setCharFormat(f)
        self.setCurrentCharFormat(f)

    # ---------------------------------------------------------- link
    def insert_link(self):
        cur = self.textCursor()
        sel = cur.selectedText()
        url, ok = QInputDialog.getText(self, "Sisipkan tautan", "Alamat (URL):", text="https://")
        if not ok or not url.strip() or url.strip() == "https://":
            return
        url = url.strip()
        f = QTextCharFormat()
        f.setAnchor(True)
        f.setAnchorHref(url)
        f.setForeground(QBrush(QColor("#0563C1")))
        f.setFontUnderline(True)
        if sel:
            cur.mergeCharFormat(f)
        else:
            cur.insertText(url, f)
        n = QTextCharFormat()
        n.setAnchor(False)
        n.setFontUnderline(False)
        n.setForeground(QBrush(Qt.BrushStyle.NoBrush))
        self.setCurrentCharFormat(n) if not sel else None

    def remove_link(self):
        cur = self.textCursor()
        if not cur.hasSelection():
            cur.select(QTextCursor.SelectionType.WordUnderCursor)
        f = QTextCharFormat()
        f.setAnchor(False)
        f.setAnchorHref("")
        f.setFontUnderline(False)
        f.setForeground(QBrush(Qt.BrushStyle.NoBrush))
        cur.mergeCharFormat(f)

    # ---------------------------------------------------------- blok
    def set_heading(self, level: int):
        cur = self.textCursor()
        cur.beginEditBlock()
        for b in self._blocks():
            bc = QTextCursor(b)
            bf = b.blockFormat()
            bf.setHeadingLevel(level)
            bc.setBlockFormat(bf)
            bc.movePosition(QTextCursor.MoveOperation.StartOfBlock)
            bc.movePosition(QTextCursor.MoveOperation.EndOfBlock, QTextCursor.MoveMode.KeepAnchor)
            f = QTextCharFormat()
            f.setFontPointSize(HEADING_SIZES.get(level, DEFAULT_SIZE))
            f.setFontWeight(700 if level else 400)
            bc.mergeCharFormat(f)
        cur.endEditBlock()
        f = QTextCharFormat()
        f.setFontPointSize(HEADING_SIZES.get(level, DEFAULT_SIZE))
        f.setFontWeight(700 if level else 400)
        self.mergeCurrentCharFormat(f)
        self.stateChanged.emit()

    def heading_level(self) -> int:
        return self.textCursor().blockFormat().headingLevel()

    def set_align(self, flag):
        self.setAlignment(flag)
        self.stateChanged.emit()

    def toggle_list(self, style):
        cur = self.textCursor()
        cur.beginEditBlock()
        blocks = self._blocks()
        tl = cur.currentList()
        if tl and tl.format().style() == style:
            for b in blocks:
                lst = b.textList()
                if lst:
                    lst.remove(b)
                    bc = QTextCursor(b)
                    bf = b.blockFormat()
                    bf.setIndent(0)
                    bc.setBlockFormat(bf)
        else:
            lf = QTextListFormat()
            lf.setStyle(style)
            lf.setIndent(tl.format().indent() if tl else 1)
            first = QTextCursor(blocks[0])
            lst = first.createList(lf)
            for b in blocks[1:]:
                lst.add(b)
        cur.endEditBlock()
        self.stateChanged.emit()

    def list_style(self):
        tl = self.textCursor().currentList()
        return tl.format().style() if tl else None

    def shift_indent(self, delta: int):
        cur = self.textCursor()
        cur.beginEditBlock()
        for b in self._blocks():
            tl = b.textList()
            if not tl:
                bf = b.blockFormat()
                bf.setIndent(max(0, min(8, bf.indent() + delta)))
                QTextCursor(b).setBlockFormat(bf)
                continue
            lf = tl.format()
            new = lf.indent() + delta
            if new < 1:
                tl.remove(b)
                bf = b.blockFormat()
                bf.setIndent(0)
                QTextCursor(b).setBlockFormat(bf)
                continue
            if new > 8:
                continue
            target = None
            p = b.previous()
            while p.isValid():
                ptl = p.textList()
                if not ptl:
                    break
                ind = ptl.format().indent()
                if ind == new and ptl.format().style() == lf.style():
                    target = ptl
                    break
                if ind < new:
                    break
                p = p.previous()
            if target is not None:
                target.add(b)
            else:
                nf = QTextListFormat(lf)
                nf.setIndent(new)
                QTextCursor(b).createList(nf)
        cur.endEditBlock()
        self.stateChanged.emit()

    # ------------------------------------------------------- keyboard
    def keyPressEvent(self, e: QKeyEvent):
        key = e.key()
        mods = e.modifiers()
        cur = self.textCursor()
        in_list = cur.currentList() is not None
        if key == Qt.Key.Key_Tab and in_list and not (mods & Qt.KeyboardModifier.ControlModifier):
            self.shift_indent(+1)
            return
        if key == Qt.Key.Key_Backtab:
            if in_list or cur.blockFormat().indent() > 0:
                self.shift_indent(-1)
            return
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and in_list and not cur.hasSelection() \
                and cur.block().text() == "" and not (mods & Qt.KeyboardModifier.ShiftModifier):
            self.shift_indent(-1)                      # item kosong + Enter: naik satu tingkat / keluar daftar
            return
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and not (mods & Qt.KeyboardModifier.ShiftModifier) \
                and not cur.hasSelection() and cur.blockFormat().headingLevel() > 0 and cur.atBlockEnd():
            super().keyPressEvent(e)                   # baris baru setelah judul kembali menjadi paragraf biasa
            self.set_heading(0)
            return
        if key == Qt.Key.Key_Space and not in_list and not cur.hasSelection():
            text = cur.block().text()[:cur.positionInBlock()]
            if text == cur.block().text()[:cur.positionInBlock()] and cur.positionInBlock() == len(cur.block().text()):
                style = None
                if text in ("-", "*", "•"):
                    style = LS.ListDisc
                elif re.fullmatch(r"\d{1,2}[.)]", text):
                    style = LS.ListDecimal
                elif re.fullmatch(r"[a-z][.)]", text):
                    style = LS.ListLowerAlpha
                if style is not None:
                    cur.beginEditBlock()
                    cur.movePosition(QTextCursor.MoveOperation.StartOfBlock)
                    cur.movePosition(QTextCursor.MoveOperation.EndOfBlock, QTextCursor.MoveMode.KeepAnchor)
                    cur.removeSelectedText()
                    cur.endEditBlock()
                    self.setTextCursor(cur)
                    self.toggle_list(style)
                    return
        super().keyPressEvent(e)

    def paste_plain(self):
        self.insertPlainText(self.clipboard_text())

    def clipboard_text(self):
        from PySide6.QtGui import QGuiApplication
        return QGuiApplication.clipboard().text()


def end_start(doc, block_number):
    return doc.findBlockByNumber(block_number).position()