"""Jendela utama Catatan Cornell (Edisi Profesional)."""
import re
from datetime import date
from pathlib import Path

from PySide6.QtCore import QDate, QEvent, QLocale, QSettings, QSize, Qt, QTimer, QUrl
from PySide6.QtGui import QAction, QActionGroup, QColor, QDesktopServices, QFont, QFontDatabase, QKeySequence, QPalette
from PySide6.QtWidgets import (QApplication, QColorDialog, QComboBox, QDateEdit, QFileDialog, QFrame, QGridLayout,
                               QHBoxLayout, QLabel, QLineEdit, QMainWindow, QMenu, QMessageBox, QSplitter,
                               QToolBar, QToolButton, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
                               QWidgetAction)

import editor as ed
from docx_export import export_docx
from editor import RichEdit
from icons import make_icon
from pdf_export import export_pdf
from store import NoteStore

PAPER_QSS = """
QFrame#sheet { background: #FFFFFF; border: 1px solid #E5E7EB; border-radius: 8px; }
QWidget#panel { background: #FFFFFF; }
QTextEdit#paper { background: #FFFFFF; color: #1F2937; border: none;
                  selection-background-color: #DBEAFE; selection-color: #111827; }
QLineEdit#topic { background: transparent; border: none; color: #111827; font-size: 21pt; font-weight: 600; padding: 2px 0; }
QLineEdit#meta, QDateEdit#meta { background: transparent; border: none; border-bottom: 1px solid #E5E7EB;
                                 color: #4B5563; padding: 2px 4px; }
QLabel#panelLabel { color: #6B7280; font-size: 7.5pt; font-weight: 700; letter-spacing: 1px; padding: 6px 10px 0 10px; }
QSplitter::handle { background: #E5E7EB; }
QSplitter::handle:horizontal { width: 1px; }
QSplitter::handle:vertical { height: 1px; }
"""

FONT_SIZES = [8, 9, 10, 11, 12, 14, 16, 18, 20, 24, 28, 32, 36]


def count_words(*texts) -> int:
    return sum(len(re.findall(r"\w+", t)) for t in texts)


class MainWindow(QMainWindow):
    def __init__(self, store: NoteStore):
        super().__init__()
        self.store = store
        self.settings = QSettings("mnawawii", "cornell")
        self.current: dict | None = None
        self.dirty = False
        self.loading = False
        self.icon_targets: list[tuple[object, str, str | None]] = []
        self.highlight_color = QColor(ed.HIGHLIGHT_COLORS[0])
        self.text_color = QColor(ed.TEXT_COLORS[0])
        self.paper = self.settings.value("paper", "A4")

        self.setWindowTitle("Catatan Profesional")
        self.resize(1180, 760)
        self.setMinimumSize(760, 520)

        self.save_timer = QTimer(self, singleShot=True, interval=1200)
        self.save_timer.timeout.connect(self.save_now)

        self._build_central()
        self._build_actions()
        self._build_menus()
        self._build_toolbars()
        self._build_statusbar()
        self.sheet.setStyleSheet(PAPER_QSS)
        self.refresh_icons()

        QApplication.instance().focusChanged.connect(self._on_focus_changed)
        self.active = self.notes_edit
        self.refresh_tree()
        first = self.first_note_id()
        if first:
            self.select_note(first)
        else:
            self.new_note()
        geo = self.settings.value("geometry")
        if geo:
            self.restoreGeometry(geo)

    # ---------------------------------------------------------------- tata letak
    def _build_central(self):
        root = QWidget()
        h = QHBoxLayout(root)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)
        self.setCentralWidget(root)

        # ---- sidebar
        self.sidebar = QWidget()
        self.sidebar.setMinimumWidth(190)
        self.sidebar.setMaximumWidth(340)
        sv = QVBoxLayout(self.sidebar)
        sv.setContentsMargins(10, 10, 6, 10)
        top = QHBoxLayout()
        title = QLabel("Catatan")
        f = title.font()
        f.setPointSizeF(f.pointSizeF() + 4)
        f.setBold(True)
        title.setFont(f)
        top.addWidget(title)
        top.addStretch(1)
        self.btn_new = QToolButton()
        self.btn_new.setToolTip("Catatan baru (Ctrl+N)")
        self.btn_new.setAutoRaise(True)
        top.addWidget(self.btn_new)
        sv.addLayout(top)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Cari catatan…  (Ctrl+F)")
        self.search.setClearButtonEnabled(True)
        self.search_timer = QTimer(self, singleShot=True, interval=250)
        self.search_timer.timeout.connect(self.refresh_tree)
        self.search.textChanged.connect(lambda _t: self.search_timer.start())
        sv.addWidget(self.search)
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setIndentation(14)
        self.tree.setUniformRowHeights(True)
        self.tree.currentItemChanged.connect(self._on_tree_select)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._tree_menu)
        sv.addWidget(self.tree, 1)
        h.addWidget(self.sidebar)

        # ---- lembar Kerja
        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(10, 10, 14, 10)
        self.sheet = QFrame()
        self.sheet.setObjectName("sheet")
        sh = QVBoxLayout(self.sheet)
        sh.setContentsMargins(22, 14, 22, 14)
        sh.setSpacing(6)

        self.topic = QLineEdit()
        self.topic.setObjectName("topic")
        self.topic.setPlaceholderText("Topik / judul materi")
        sh.addWidget(self.topic)
        meta = QHBoxLayout()
        meta.setSpacing(14)
        self.course = QLineEdit()
        self.course.setObjectName("meta")
        self.course.setPlaceholderText("Kategori / Proyek")
        self.course.setMaximumWidth(280)
        self.date = QDateEdit(QDate.currentDate())
        self.date.setObjectName("meta")
        self.date.setCalendarPopup(True)
        self.date.setLocale(QLocale(QLocale.Language.Indonesian))
        self.date.setDisplayFormat("dd MMM yyyy")
        self.date.setMaximumWidth(140)
        meta.addWidget(QLabel("Proyek:"))
        meta.addWidget(self.course)
        meta.addWidget(QLabel("Tanggal:"))
        meta.addWidget(self.date)
        meta.addStretch(1)
        self.words_label = QLabel("")
        self.words_label.setStyleSheet("color:#6B7280;")
        meta.addWidget(self.words_label)
        sh.addLayout(meta)
        for lab in self.sheet.findChildren(QLabel):
            lab.setStyleSheet("color:#6B7280;")

        line = QFrame()
        line.setFixedHeight(1)
        line.setStyleSheet("background:#E5E7EB;")
        sh.addWidget(line)

        def panel(text, placeholder):
            w = QWidget()
            w.setObjectName("panel")
            lay = QVBoxLayout(w)
            lay.setContentsMargins(0, 0, 0, 0)
            lay.setSpacing(0)
            lab = QLabel(text)
            lab.setObjectName("panelLabel")
            ed_ = RichEdit(placeholder)
            ed_.setObjectName("paper")
            pal = ed_.palette()
            pal.setColor(QPalette.ColorRole.Base, QColor("#FFFFFF"))
            pal.setColor(QPalette.ColorRole.Text, QColor("#1F2937"))
            pal.setColor(QPalette.ColorRole.PlaceholderText, QColor("#9CA3AF"))
            ed_.setPalette(pal)
            lay.addWidget(lab)
            lay.addWidget(ed_, 1)
            return w, ed_, lab

        self.cue_panel, self.cue_edit, _ = panel("AGENDA / KATA KUNCI", "Topik rapat, agenda, atau poin penting…")
        self.notes_panel, self.notes_edit, self.notes_label = panel("CATATAN", "Catat hasil rapat, ide, atau draf pekerjaan di sini…")
        self.sum_panel, self.sum_edit, _ = panel("TINDAK LANJUT", "Ringkasan eksekutif atau daftar tindak lanjut (action items)…")
        self.editors = [self.cue_edit, self.notes_edit, self.sum_edit]

        self.split_h = QSplitter(Qt.Orientation.Horizontal)
        self.split_h.addWidget(self.cue_panel)
        self.split_h.addWidget(self.notes_panel)
        self.split_h.setChildrenCollapsible(False)
        self.split_h.setHandleWidth(1)
        self.split_v = QSplitter(Qt.Orientation.Vertical)
        self.split_v.addWidget(self.split_h)
        self.split_v.addWidget(self.sum_panel)
        self.split_v.setChildrenCollapsible(False)
        self.split_v.setHandleWidth(1)
        self.split_h.setSizes([300, 700])
        self.split_v.setSizes([640, 150])
        sh.addWidget(self.split_v, 1)
        rv.addWidget(self.sheet, 1)
        h.addWidget(right, 1)

        for w in (self.topic, self.course):
            w.textChanged.connect(self.mark_dirty)
        self.date.dateChanged.connect(self.mark_dirty)
        for e in self.editors:
            e.textChanged.connect(self.mark_dirty)
            e.stateChanged.connect(self.update_format_state)
            e.focusedIn.connect(self._set_active)
        self.split_h.splitterMoved.connect(lambda *_: self.mark_dirty())
        self.split_v.splitterMoved.connect(lambda *_: self.mark_dirty())

    # ---------------------------------------------------------------- aksi
    def act(self, text, slot=None, shortcut=None, icon=None, checkable=False, tip=None):
        a = QAction(text, self)
        if shortcut:
            a.setShortcut(QKeySequence(shortcut))
        if slot:
            a.triggered.connect(slot)
        a.setCheckable(checkable)
        a.setToolTip(tip or (f"{text} ({shortcut})" if shortcut else text))
        if icon:
            self.icon_targets.append((a, icon, None))
        return a

    def on_active(self, fn):
        def run(*_a):
            e = self.active
            fn(e)
            e.setFocus()
        return run

    def _build_actions(self):
        A = self.act
        o = self.on_active
        self.a_new = A("Catatan baru", self.new_note, "Ctrl+N", "plus")
        self.a_pdf = A("Ekspor PDF…", lambda: self.export("pdf"), "Ctrl+E", "pdf")
        self.a_word = A("Ekspor Word…", lambda: self.export("docx"), "Ctrl+Shift+E", "word")
        self.a_dup = A("Duplikat catatan", self.duplicate_current, None, "copy")
        self.a_del = A("Hapus catatan…", self.delete_current, None, "trash")
        self.a_backup = A("Cadangkan sekarang", self.backup_now)
        self.a_open_dir = A("Buka folder data", lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.store.root))))
        self.a_quit = A("Keluar", self.close, "Ctrl+Q")
        self.a_undo = A("Urungkan", o(lambda e: e.undo()), "Ctrl+Z", "undo")
        self.a_redo = A("Ulangi", o(lambda e: e.redo()), "Ctrl+Shift+Z", "redo")
        self.a_find = A("Cari catatan", lambda: (self.search.setFocus(), self.search.selectAll()), "Ctrl+F")
        self.a_paste_plain = A("Tempel sebagai teks biasa", o(lambda e: e.paste_plain()), "Ctrl+Shift+V")
        self.a_bold = A("Tebal", o(lambda e: e.toggle_bold()), "Ctrl+B", "bold", True)
        self.a_italic = A("Miring", o(lambda e: e.toggle_italic()), "Ctrl+I", "italic", True)
        self.a_underline = A("Garis bawah", o(lambda e: e.toggle_underline()), "Ctrl+U", "underline", True)
        self.a_strike = A("Coret", o(lambda e: e.toggle_strike()), "Ctrl+Shift+X", "strike", True)
        self.a_sup = A("Superskrip", o(lambda e: e.toggle_valign(True)), "Ctrl+.", "sup", True)
        self.a_sub = A("Subskrip", o(lambda e: e.toggle_valign(False)), "Ctrl+,", "sub", True)
        self.a_hl = A("Sorot teks (kuning)", o(lambda e: e.toggle_highlight(self.highlight_color)), "Ctrl+H", "highlight")
        self.a_color = A("Warna teks", o(lambda e: e.set_text_color(self.text_color)), None, "textcolor")
        self.a_bullet = A("Daftar bullet", o(lambda e: e.toggle_list(ed.LS.ListDisc)), "Ctrl+Shift+8", "bullet", True)
        self.a_number = A("Daftar bernomor", o(lambda e: e.toggle_list(ed.LS.ListDecimal)), "Ctrl+Shift+7", "number", True)
        self.a_indent = A("Geser ke dalam", o(lambda e: e.shift_indent(+1)), "Ctrl+]", "indent")
        self.a_outdent = A("Geser ke luar", o(lambda e: e.shift_indent(-1)), "Ctrl+[", "outdent")
        self.aligns = {}
        for key, txt, sc, flag in (("left", "Rata kiri", "Ctrl+L", Qt.AlignmentFlag.AlignLeft),
                                   ("center", "Rata tengah", "Ctrl+E", Qt.AlignmentFlag.AlignHCenter),
                                   ("right", "Rata kanan", "Ctrl+R", Qt.AlignmentFlag.AlignRight),
                                   ("justify", "Rata kiri-kanan", "Ctrl+J", Qt.AlignmentFlag.AlignJustify)):
            a = A(txt, o(lambda e, f=flag: e.set_align(f)), sc if key != "center" else "Ctrl+Shift+C", key, True)
            self.aligns[key] = a
        ag = QActionGroup(self)
        for a in self.aligns.values():
            ag.addAction(a)
        self.a_link = A("Sisipkan tautan…", o(lambda e: e.insert_link()), "Ctrl+K", "link")
        self.a_unlink = A("Hapus tautan", o(lambda e: e.remove_link()))
        self.a_clear = A("Hapus format", o(lambda e: e.clear_formatting()), "Ctrl+\\", "clear")
        self.a_study = A("Mode baca (tutup catatan)", self.toggle_study, "F8", "eye", True,
                         tip="Mode baca (F8): sembunyikan detail Catatan untuk fokus pada Tindak Lanjut")
        self.a_sidebar = A("Tampilkan daftar catatan", self.toggle_sidebar, "F9", "sidebar", True)
        self.a_sidebar.setChecked(True)
        self.a_study.setIconText("Mode baca")
        self.a_sidebar.setIconText("Daftar")
        self.a_redo.setShortcuts([QKeySequence("Ctrl+Shift+Z"), QKeySequence("Ctrl+Y")])
        self.btn_new.setDefaultAction(self.a_new)
        self.btn_new.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.paper_actions = {}
        pg = QActionGroup(self)
        for name in ("A4", "Letter", "Legal"):
            a = QAction(name, self, checkable=True)
            a.setChecked(name == self.paper)
            a.triggered.connect(lambda _c, n=name: self.set_paper(n))
            pg.addAction(a)
            self.paper_actions[name] = a

    def _build_menus(self):
        mb = self.menuBar()
        m = mb.addMenu("&Berkas")
        for a in (self.a_new, self.a_dup, self.a_del):
            m.addAction(a)
        m.addSeparator()
        m.addAction(self.a_pdf)
        m.addAction(self.a_word)
        paper = m.addMenu("Ukuran kertas ekspor")
        for a in self.paper_actions.values():
            paper.addAction(a)
        m.addSeparator()
        m.addAction(self.a_backup)
        m.addAction(self.a_open_dir)
        m.addSeparator()
        m.addAction(self.a_quit)
        m = mb.addMenu("&Edit")
        for a in (self.a_undo, self.a_redo):
            m.addAction(a)
        m.addSeparator()
        m.addAction(self.a_paste_plain)
        m.addAction(self.a_find)
        m = mb.addMenu("&Format")
        for a in (self.a_bold, self.a_italic, self.a_underline, self.a_strike, self.a_sup, self.a_sub):
            m.addAction(a)
        m.addSeparator()
        for a in (self.a_hl, self.a_color):
            m.addAction(a)
        m.addSeparator()
        for a in (self.a_bullet, self.a_number, self.a_indent, self.a_outdent):
            m.addAction(a)
        m.addSeparator()
        for a in self.aligns.values():
            m.addAction(a)
        m.addSeparator()
        for a in (self.a_link, self.a_unlink, self.a_clear):
            m.addAction(a)
        m = mb.addMenu("&Tampilan")
        m.addAction(self.a_study)
        m.addAction(self.a_sidebar)
        m = mb.addMenu("&Bantuan")
        m.addAction(self.act("Tentang Aplikasi", self.about))
        m.addAction(self.act("Tips pintasan", self.tips))

    def _swatch_menu(self, colors, on_pick, clear_text, custom=True):
        menu = QMenu(self)
        w = QWidget()
        g = QGridLayout(w)
        g.setContentsMargins(8, 8, 8, 4)
        g.setSpacing(5)
        for i, c in enumerate(colors):
            b = QToolButton()
            b.setFixedSize(24, 24)
            b.setStyleSheet(f"QToolButton {{ background:{c}; border:1px solid #888; border-radius:12px; }}"
                            f"QToolButton:hover {{ border:2px solid #444; }}")
            b.clicked.connect(lambda _c=False, col=c: (menu.close(), on_pick(QColor(col))))
            g.addWidget(b, i // 4, i % 4)
        wa = QWidgetAction(menu)
        wa.setDefaultWidget(w)
        menu.addAction(wa)
        menu.addAction(clear_text, lambda: on_pick(None))
        if custom:
            menu.addAction("Warna lain…", lambda: self._custom_color(on_pick))
        return menu

    def _custom_color(self, on_pick):
        c = QColorDialog.getColor(QColor("#FFE066"), self, "Pilih warna")
        if c.isValid():
            on_pick(c)

    def _build_toolbars(self):
        tb1 = QToolBar("Berkas")
        tb1.setMovable(False)
        tb1.setIconSize(QSize(20, 20))
        tb1.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        for a in (self.a_new, self.a_pdf, self.a_word):
            tb1.addAction(a)
        tb1.addSeparator()
        tb1.addAction(self.a_undo)
        tb1.addAction(self.a_redo)
        tb1.addSeparator()
        tb1.addAction(self.a_study)
        tb1.addAction(self.a_sidebar)
        self.addToolBar(tb1)
        self.addToolBarBreak()

        tb = QToolBar("Format")
        tb.setMovable(False)
        tb.setIconSize(QSize(20, 20))
        self.addToolBar(tb)
        self.font_combo = QComboBox()
        self.font_combo.setMinimumWidth(150)
        self.font_combo.setMaximumWidth(190)
        self.font_combo.addItem("Bawaan")
        self.font_combo.addItems(sorted(set(QFontDatabase.families()), key=str.casefold))
        self.font_combo.activated.connect(lambda i: self.on_active(lambda e: e.set_family(None if i == 0 else self.font_combo.itemText(i)))())
        tb.addWidget(self.font_combo)
        self.size_combo = QComboBox()
        self.size_combo.setEditable(True)
        self.size_combo.setMaximumWidth(70)
        self.size_combo.addItems([str(s) for s in FONT_SIZES])
        self.size_combo.setCurrentText("11")
        self.size_combo.activated.connect(lambda _i: self._apply_size())
        self.size_combo.lineEdit().returnPressed.connect(self._apply_size)
        tb.addWidget(self.size_combo)
        self.heading_combo = QComboBox()
        self.heading_combo.addItems(["Normal", "Judul 1", "Judul 2", "Judul 3"])
        self.heading_combo.activated.connect(lambda i: self.on_active(lambda e: e.set_heading(i))())
        tb.addWidget(self.heading_combo)
        tb.addSeparator()
        for a in (self.a_bold, self.a_italic, self.a_underline, self.a_strike, self.a_sup, self.a_sub):
            tb.addAction(a)
        tb.addSeparator()
        self.btn_hl = self._color_button(self.a_hl, "highlight", ed.HIGHLIGHT_COLORS, self._pick_highlight, "Tanpa sorotan")
        self.btn_tc = self._color_button(self.a_color, "textcolor", ed.TEXT_COLORS, self._pick_text_color, "Warna teks bawaan")
        tb.addWidget(self.btn_hl)
        tb.addWidget(self.btn_tc)
        tb.addSeparator()
        self.btn_bul = self._list_button(self.a_bullet, [("● Bulat", "disc"), ("○ Lingkaran", "circle"), ("■ Kotak", "square")], ed.BULLETS)
        self.btn_num = self._list_button(self.a_number, [("1. 2. 3.", "decimal"), ("a. b. c.", "lower-alpha"), ("A. B. C.", "upper-alpha"),
                                                         ("i. ii. iii.", "lower-roman"), ("I. II. III.", "upper-roman")], ed.NUMBERS)
        tb.addWidget(self.btn_bul)
        tb.addWidget(self.btn_num)
        tb.addAction(self.a_outdent)
        tb.addAction(self.a_indent)
        tb.addSeparator()
        for a in self.aligns.values():
            tb.addAction(a)
        tb.addSeparator()
        tb.addAction(self.a_link)
        tb.addAction(self.a_clear)

    def _color_button(self, action, icon, colors, on_pick, clear_text):
        b = QToolButton()
        b.setDefaultAction(action)
        b.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup)
        b.setMenu(self._swatch_menu(colors, on_pick, clear_text))
        b.setIconSize(QSize(20, 20))
        self.icon_targets.append((action, icon, "accent"))
        return b

    def _list_button(self, action, entries, mapping):
        b = QToolButton()
        b.setDefaultAction(action)
        b.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup)
        menu = QMenu(self)
        for label, key in entries:
            menu.addAction(label, self.on_active(lambda e, k=key: e.toggle_list(mapping[k])))
        b.setMenu(menu)
        return b

    def _build_statusbar(self):
        sb = self.statusBar()
        self.state_label = QLabel("Tersimpan")
        self.backup_label = QLabel("")
        sb.addWidget(self.state_label)
        sb.addPermanentWidget(self.backup_label)
        self.update_backup_label()

    # ------------------------------------------------------------ ikon & tema
    def refresh_icons(self):
        col = self.palette().color(QPalette.ColorRole.ButtonText)
        for target, name, accent_kind in self.icon_targets:
            accent = None
            if accent_kind == "accent":
                accent = self.highlight_color if name == "highlight" else self.text_color
            icon = make_icon(name, col, accent)
            (target.setIcon if hasattr(target, "setIcon") else None) and target.setIcon(icon)
        # tombol bertindak default memakai ikon dari action-nya
        self.btn_new.setIcon(make_icon("plus", col))
        for b in (self.btn_hl, self.btn_tc):
            b.setIcon(b.defaultAction().icon())

    def changeEvent(self, e):
        if e.type() == QEvent.Type.PaletteChange and hasattr(self, "btn_new"):
            QTimer.singleShot(0, self.refresh_icons)
        super().changeEvent(e)

    # ------------------------------------------------------------ fokus & status
    def _set_active(self, e):
        self.active = e
        self.update_format_state()

    def _on_focus_changed(self, _old, new):
        if new in self.editors:
            self.active = new

    def update_format_state(self):
        e = self.active
        if e is None:
            return
        cf = e.currentCharFormat()
        self.a_bold.setChecked(e.fontWeight() >= 600)
        self.a_italic.setChecked(e.fontItalic())
        self.a_underline.setChecked(e.fontUnderline())
        self.a_strike.setChecked(cf.fontStrikeOut())
        va = cf.verticalAlignment()
        self.a_sup.setChecked(va == type(va).AlignSuperScript)
        self.a_sub.setChecked(va == type(va).AlignSubScript)
        ls = e.list_style()
        self.a_bullet.setChecked(ls in ed.BULLETS.values())
        self.a_number.setChecked(ls in ed.NUMBERS.values())
        al = e.alignment()
        key = "center" if al & Qt.AlignmentFlag.AlignHCenter else "right" if al & Qt.AlignmentFlag.AlignRight else \
              "justify" if al & Qt.AlignmentFlag.AlignJustify else "left"
        self.aligns[key].setChecked(True)
        for w, fn in ((self.heading_combo, lambda: e.heading_level()),
                      (self.font_combo, None), (self.size_combo, None)):
            w.blockSignals(True)
        self.heading_combo.setCurrentIndex(max(0, min(3, e.heading_level())))
        fam = cf.fontFamilies()[0] if cf.hasProperty(cf.Property.FontFamilies) and cf.fontFamilies() else ""
        idx = self.font_combo.findText(fam) if fam and fam != ed.DEFAULT_FAMILY else 0
        self.font_combo.setCurrentIndex(max(0, idx))
        pt = cf.fontPointSize() or ed.DEFAULT_SIZE
        self.size_combo.setCurrentText(str(int(pt)) if abs(pt - int(pt)) < 0.01 else f"{pt:.1f}")
        for w in (self.heading_combo, self.font_combo, self.size_combo):
            w.blockSignals(False)

    def _apply_size(self):
        try:
            pt = float(self.size_combo.currentText().replace(",", "."))
        except ValueError:
            return
        self.on_active(lambda e: e.set_size(pt))()

    def _pick_highlight(self, color):
        if color is not None:
            self.highlight_color = color
            self.refresh_icons()
        self.on_active(lambda e: e.set_highlight(color))()

    def _pick_text_color(self, color):
        if color is not None:
            self.text_color = color
            self.refresh_icons()
        self.on_active(lambda e: e.set_text_color(color))()

    # ------------------------------------------------------------------ daftar
    def first_note_id(self):
        if not self.store.index:
            return None
        return sorted(self.store.index, key=lambda i: self.store.index[i].get("updated", ""), reverse=True)[0]

    def refresh_tree(self, keep: str | None = None):
        keep = keep or (self.current["id"] if self.current else None)
        ids = self.store.search(self.search.text()) if self.search.text().strip() else set(self.store.index)
        groups: dict[str, list[str]] = {}
        for nid in ids:
            c = (self.store.index[nid].get("course") or "").strip() or "Tanpa proyek"
            groups.setdefault(c, []).append(nid)
        self.tree.blockSignals(True)
        self.tree.clear()
        target = None
        for course in sorted(groups, key=lambda c: (c == "Tanpa proyek", c.casefold())):
            g = QTreeWidgetItem([f"{course}  ({len(groups[course])})"])
            f = g.font(0)
            f.setBold(True)
            g.setFont(0, f)
            g.setFlags(Qt.ItemFlag.ItemIsEnabled)
            self.tree.addTopLevelItem(g)
            for nid in sorted(groups[course], key=lambda i: (self.store.index[i].get("date", ""), self.store.index[i].get("updated", "")), reverse=True):
                m = self.store.index[nid]
                it = QTreeWidgetItem([(m.get("title") or "Tanpa judul")])
                it.setData(0, Qt.ItemDataRole.UserRole, nid)
                it.setToolTip(0, f"{m.get('title') or 'Tanpa judul'}\n{m.get('date', '')}")
                g.addChild(it)
                if nid == keep:
                    target = it
            g.setExpanded(True)
        if target is not None:
            self.tree.setCurrentItem(target)
        self.tree.blockSignals(False)

    def _on_tree_select(self, item, _prev):
        if item is None:
            return
        nid = item.data(0, Qt.ItemDataRole.UserRole)
        if nid and (not self.current or nid != self.current["id"]):
            self.load_note(nid)

    def select_note(self, nid):
        self.load_note(nid)
        self.refresh_tree(keep=nid)

    def _tree_menu(self, pos):
        it = self.tree.itemAt(pos)
        if not it or not it.data(0, Qt.ItemDataRole.UserRole):
            return
        self.tree.setCurrentItem(it)
        m = QMenu(self)
        m.addAction(self.a_pdf)
        m.addAction(self.a_word)
        m.addSeparator()
        m.addAction(self.a_dup)
        m.addAction(self.a_del)
        m.exec(self.tree.viewport().mapToGlobal(pos))

    # ------------------------------------------------------------ muat & simpan
    def load_note(self, nid: str):
        self.save_now()
        try:
            note = self.store.get(nid)
        except (OSError, ValueError):
            QMessageBox.warning(self, "Galat", "Berkas catatan tidak dapat dibaca.")
            return
        self.loading = True
        self.current = note
        self.topic.setText(note.get("title", ""))
        self.course.setText(note.get("course", ""))
        try:
            self.date.setDate(QDate.fromString(note.get("date", ""), Qt.DateFormat.ISODate) if note.get("date") else QDate.currentDate())
        except Exception:
            self.date.setDate(QDate.currentDate())
        for e, key in ((self.cue_edit, "cue"), (self.notes_edit, "notes"), (self.sum_edit, "summary")):
            e.setHtml(note.get(key, ""))
            e.document().clearUndoRedoStacks()
            e.moveCursor(e.textCursor().MoveOperation.Start)
        r = float(note.get("cue_ratio", 0.3))
        self.split_h.setSizes([int(r * 1000), int((1 - r) * 1000)])
        s = float(note.get("summary_ratio", 0.19))
        self.split_v.setSizes([int((1 - s) * 1000), int(s * 1000)])
        self.loading = False
        self.dirty = False
        self.update_words()
        self.state_label.setText("Tersimpan")
        self.notes_edit.setFocus()

    def mark_dirty(self, *_a):
        if self.loading or self.current is None:
            return
        self.dirty = True
        self.state_label.setText("Menyimpan…")
        self.save_timer.start()

    def update_words(self):
        n = count_words(self.cue_edit.toPlainText(), self.notes_edit.toPlainText(), self.sum_edit.toPlainText())
        self.words_label.setText(f"{n} kata")

    def collect(self) -> dict:
        n = self.current
        n["title"] = self.topic.text().strip()
        n["course"] = self.course.text().strip()
        n["date"] = self.date.date().toString(Qt.DateFormat.ISODate)
        n["cue"] = self.cue_edit.toHtml() if not self.cue_edit.document().isEmpty() else ""
        n["notes"] = self.notes_edit.toHtml() if not self.notes_edit.document().isEmpty() else ""
        n["summary"] = self.sum_edit.toHtml() if not self.sum_edit.document().isEmpty() else ""
        sz = self.split_h.sizes()
        if sum(sz) > 0:
            n["cue_ratio"] = round(sz[0] / sum(sz), 3)
        sv = self.split_v.sizes()
        if sum(sv) > 0:
            n["summary_ratio"] = round(sv[1] / sum(sv), 3)
        return n

    def save_now(self):
        if not self.dirty or self.current is None:
            return
        self.save_timer.stop()
        course_before = self.store.index.get(self.current["id"], {}).get("course", "")
        note = self.collect()
        try:
            self.store.save(note)
        except OSError as e:
            self.state_label.setText(f"Gagal menyimpan: {e}")
            return
        self.dirty = False
        self.state_label.setText("Tersimpan")
        self.update_words()
        self.refresh_tree()

    # ------------------------------------------------------------- operasi catatan
    def new_note(self):
        self.save_now()
        course = self.current.get("course", "") if self.current else ""
        n = self.store.new(course=course)
        self.refresh_tree(keep=n["id"])
        self.load_note(n["id"])
        self.refresh_tree(keep=n["id"])
        self.topic.setFocus()

    def duplicate_current(self):
        if not self.current:
            return
        self.save_now()
        n = self.store.duplicate(self.current["id"])
        self.select_note(n["id"])

    def delete_current(self):
        if not self.current:
            return
        title = self.current.get("title") or "Tanpa judul"
        if QMessageBox.question(self, "Hapus catatan", f"Hapus “{title}”?\n\nCatatan dipindahkan ke folder sampah dan "
                                "dihapus permanen setelah 30 hari.") != QMessageBox.StandardButton.Yes:
            return
        nid = self.current["id"]
        self.dirty = False
        self.current = None
        self.store.delete(nid)
        nxt = self.first_note_id()
        if nxt:
            self.select_note(nxt)
        else:
            self.refresh_tree()
            self.new_note()

    # --------------------------------------------------------------------- ekspor
    def set_paper(self, name):
        self.paper = name
        self.settings.setValue("paper", name)

    def export(self, kind: str):
        if not self.current:
            return
        self.dirty = True
        self.save_now()
        note = self.current
        ext = "pdf" if kind == "pdf" else "docx"
        safe = re.sub(r"[^\w\- ]+", "", (note.get("title") or "catatan")).strip().replace(" ", "_") or "catatan"
        start = Path(self.settings.value("export_dir", str(Path.home()))) / f"{safe}.{ext}"
        filt = "PDF (*.pdf)" if kind == "pdf" else "Dokumen Word (*.docx)"
        path, _ = QFileDialog.getSaveFileName(self, "Ekspor catatan", str(start), filt)
        if not path:
            return
        if not path.lower().endswith("." + ext):
            path += "." + ext
        self.settings.setValue("export_dir", str(Path(path).parent))
        try:
            ratio = float(note.get("cue_ratio", 0.3))
            if kind == "pdf":
                pages = export_pdf(path, note, self.paper, ratio)
                msg = f"PDF dibuat ({pages} halaman)."
            else:
                export_docx(path, note, self.paper, ratio)
                msg = "Dokumen Word dibuat."
        except Exception as e:  # tampilkan galat, jangan menutup aplikasi
            QMessageBox.critical(self, "Ekspor gagal", f"{type(e).__name__}: {e}")
            return
        box = QMessageBox(QMessageBox.Icon.Information, "Ekspor selesai", f"{msg}\n{path}", parent=self)
        open_btn = box.addButton("Buka berkas", QMessageBox.ButtonRole.AcceptRole)
        box.addButton("Tutup", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        if box.clickedButton() is open_btn:
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    # -------------------------------------------------------------------- tampilan
    def toggle_study(self):
        on = self.a_study.isChecked()
        self.notes_panel.setVisible(not on)
        self.state_label.setText("Mode baca: kolom Catatan disembunyikan" if on else "Tersimpan")

    def toggle_sidebar(self):
        self.sidebar.setVisible(self.a_sidebar.isChecked())

    # ----------------------------------------------------------------------- lain-lain
    def update_backup_label(self):
        self.backup_label.setText(f"Cadangan terakhir: {self.store.last_backup_label()}")

    def backup_now(self):
        self.save_now()
        ok = self.store.backup(force=True)
        self.update_backup_label()
        self.state_label.setText("Cadangan dibuat" if ok else "Tidak ada yang dicadangkan")

    def about(self):
        QMessageBox.about(self, "Catatan Profesional",
                          "<b>Catatan Profesional</b><br>Pencatat ringkas untuk alur kerja profesional (Agenda, Catatan, Tindak Lanjut). "
                          "Ekspor ke PDF dan Word.<br><br>Data: " + str(self.store.root))

    def tips(self):
        QMessageBox.information(self, "Tips pintasan",
                                "Ctrl+B / I / U : tebal, miring, garis bawah\nCtrl+H : sorot kuning (ulangi untuk menghapus)\n"
                                "Ctrl+Shift+8 / 7 : daftar bullet / bernomor\nTab / Shift+Tab : geser tingkat daftar\n"
                                "Ketik “- ” atau “1. ” di awal baris : otomatis menjadi daftar\n"
                                "Ctrl+K : tautan    Ctrl+\\ : hapus format\n"
                                "F8 : mode baca (sembunyikan detail catatan)\nF9 : tampil/sembunyi daftar catatan\n"
                                "Ctrl+E : ekspor PDF    Ctrl+Shift+E : ekspor Word")

    def closeEvent(self, ev):
        self.save_now()
        self.settings.setValue("geometry", self.saveGeometry())
        super().closeEvent(ev)