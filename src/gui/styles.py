"""Application-wide soft light theme QSS stylesheet and colour constants."""

# ── Colour tokens ──────────────────────────────────────────────────────────────
BG_BASE       = "#f7f4ef"
BG_PANEL      = "#fff9f2"
BG_SURFACE    = "#fffdf9"
BG_ELEVATED   = "#fff4e8"
BORDER        = "#e6dccf"
BORDER_LIGHT  = "#d8cbb8"
ACCENT        = "#f29f4b"
ACCENT_HOVER  = "#f6b56b"
ACCENT_ACTIVE = "#d97d1e"
TEXT_PRIMARY  = "#3f3428"
TEXT_SECONDARY= "#7c6d5b"
TEXT_MUTED    = "#9f8f7b"
SUCCESS       = "#7abf9a"
WARNING       = "#d9a24f"
DANGER        = "#cc7b6c"
MIN_COLOUR    = "#d8894f"   # used in annotator
MAX_COLOUR    = "#6ea8cf"   # used in annotator
NORM_COLOUR   = "#8ccaa6"   # used in annotator

STYLE = """
/* ════════════════════════ Base ══════════════════════════════════════════ */
* {
    outline: 0;
}
QWidget {
    background-color: #f7f4ef;
    color: #3f3428;
    font-family: 'Segoe UI', 'Helvetica Neue', Arial, sans-serif;
    font-size: 13px;
    border: none;
}
QMainWindow::separator { background: #e6dccf; width: 1px; height: 1px; }

/* ════════════════════════ Panels / Frames ════════════════════════════════ */
QFrame#leftPanel {
    background: #fff7ee;
    border-right: 1px solid #e6dccf;
}
QFrame#rightPanel {
    background: #fff7ee;
    border-left: 1px solid #e6dccf;
}
QFrame#viewerHeader {
    background: #fff9f2;
    border-bottom: 1px solid #e6dccf;
    min-height: 38px;
    max-height: 38px;
}
QFrame#resultsHeader {
    background: #fff9f2;
    border-top: 1px solid #e6dccf;
    border-bottom: 1px solid #e6dccf;
    min-height: 30px;
    max-height: 30px;
}
QGroupBox {
    border: 1px solid #e6dccf;
    border-radius: 8px;
    margin-top: 18px;
    padding: 12px 10px 10px 10px;
    background: #fff9f2;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 6px;
    color: #e8963a;
    font-weight: 700;
    font-size: 10px;
    text-transform: uppercase;
    letter-spacing: 0.8px;
}

/* ════════════════════════ Splitter ══════════════════════════════════════ */
QSplitter::handle {
    background: #e6dccf;
}
QSplitter::handle:horizontal { width: 1px; }
QSplitter::handle:vertical   { height: 1px; }

/* ════════════════════════ Labels ════════════════════════════════════════ */
QLabel { color: #7c6d5b; background: transparent; }
QLabel#panelTitle {
    color: #f29f4b;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 1.5px;
    text-transform: uppercase;
    padding: 8px 12px 4px 12px;
}
QLabel#statusChip {
    color: #7eb8d8;
    background: #fff0df;
    border: 1px solid #f0cfaa;
    border-radius: 10px;
    padding: 2px 10px;
    font-size: 11px;
}
QLabel#thresholdValue {
    color: #f29f4b;
    font-size: 14px;
    font-weight: 700;
    min-width: 30px;
}

/* ════════════════════════ Buttons — default ══════════════════════════════ */
QPushButton {
    background: #fffdf9;
    color: #6f6254;
    border: 1px solid #c8b49e;
    border-radius: 6px;
    padding: 6px 16px;
    font-weight: 500;
    min-height: 24px;
}
QPushButton:hover {
    background: #fff4e8;
    border-color: #b09e86;
    color: #3f3428;
}
QPushButton:pressed { background: #f0e0cb; border-color: #9e8a72; }
QPushButton:disabled { color: #c8b89e; border-color: #dfd0be; background: #faf6f0; }

/* Segmented view-mode buttons */
QPushButton#segLeft {
    border-top-left-radius: 12px;
    border-bottom-left-radius: 12px;
    border-top-right-radius: 0;
    border-bottom-right-radius: 0;
    border-right: none;
    padding: 4px 14px;
    font-size: 12px;
}
QPushButton#segMid {
    border-radius: 0;
    border-right: none;
    padding: 4px 14px;
    font-size: 12px;
}
QPushButton#segRight {
    border-top-right-radius: 12px;
    border-bottom-right-radius: 12px;
    border-top-left-radius: 0;
    border-bottom-left-radius: 0;
    padding: 4px 14px;
    font-size: 12px;
}
QPushButton#segLeft:checked,
QPushButton#segMid:checked,
QPushButton#segRight:checked {
    background: #f6b56b;
    border-color: #f29f4b;
    color: #ffffff;
}

/* ════════════════════════ CollapsibleSection headers ═══════════════════ */
/* Tier 1 — accent/orange, top-level section header */
QPushButton#sectionHeader1 {
    background: #fff4e8;
    color: #c97028;
    border: none;
    border-top: 1px solid #efd8b8;
    border-bottom: 1px solid #efd8b8;
    border-radius: 0;
    padding: 0 10px;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.8px;
    text-transform: uppercase;
    text-align: left;
}
QPushButton#sectionHeader1:hover { background: #ffede0; color: #b05c20; }
QPushButton#sectionHeader1:pressed { background: #ffe4cc; }

/* Tier 2 — muted orange, parameter group header */
QPushButton#sectionHeader2 {
    background: #f9f4ee;
    color: #9a7050;
    border: none;
    border-top: 1px solid #ede4d8;
    border-bottom: 1px solid #ede4d8;
    border-radius: 0;
    padding: 0 10px;
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 0.5px;
    text-align: left;
}
QPushButton#sectionHeader2:hover { background: #f5ede4; color: #7a5030; }
QPushButton#sectionHeader2:pressed { background: #f0e4d8; }

/* Tier 3 — muted grey, advanced/rarely-changed section header */
QPushButton#sectionHeader3 {
    background: #f4f0ec;
    color: #9f8f7b;
    border: none;
    border-top: 1px solid #e8e0d8;
    border-bottom: 1px solid #e8e0d8;
    border-radius: 0;
    padding: 0 10px;
    font-size: 10px;
    font-weight: 500;
    letter-spacing: 0.3px;
    text-align: left;
}
QPushButton#sectionHeader3:hover { background: #eee8e0; color: #7a6858; }
QPushButton#sectionHeader3:pressed { background: #e8e0d8; }

/* ════════════════════════ Summary stats chips ══════════════════════════ */
QLabel#statChip {
    background: #fff4e6;
    border: 1px solid #efd8b8;
    border-radius: 8px;
    padding: 3px 10px;
    color: #8a6830;
    font-size: 11px;
    font-weight: 600;
}
QLabel#statChipAlert {
    background: #ffeee8;
    border: 1px solid #f0c0a8;
    border-radius: 8px;
    padding: 3px 10px;
    color: #a04030;
    font-size: 11px;
    font-weight: 600;
}

/* Detail CD toggle — teal accent, same height as Ruler/segmented buttons */
QPushButton#detailCD {
    background: #fffdf9;
    color: #6f6254;
    border: 1px solid #dfd0be;
    border-radius: 6px;
    padding: 4px 12px;
    font-size: 12px;
    font-weight: 500;
}
QPushButton#detailCD:hover {
    background: #f0faf5;
    border-color: #88c4a8;
    color: #3a6650;
}
QPushButton#detailCD:checked {
    background: #d0f0e0;
    border-color: #5ab080;
    color: #2a5540;
    font-weight: 700;
}
QPushButton#detailCD:pressed { background: #c0e8d0; }

/* Run Single — green accent */
QPushButton#runSingle {
    background: #ebf7f0;
    border: 1px solid #9ec9ad;
    color: #3e7f5d;
    border-radius: 7px;
    padding: 8px 0;
    font-weight: 600;
}
QPushButton#runSingle:hover {
    background: #ddf1e5;
    border-color: #88b898;
    color: #376f54;
}
QPushButton#runSingle:pressed { background: #d2eadc; }

/* Run Batch — purple accent */
QPushButton#runBatch {
    background: #fff1e4;
    border: 1px solid #efb67f;
    color: #9a5a22;
    border-radius: 7px;
    padding: 8px 0;
    font-weight: 600;
}
QPushButton#runBatch:hover {
    background: #ffe8d3;
    border-color: #eea55b;
    color: #8f4f1f;
}
QPushButton#runBatch:pressed { background: #ffe0c0; }

/* ════════════════════════ Toolbar ══════════════════════════════════════ */
QToolBar {
    background: #f2ece4;
    border-bottom: 1px solid #e6dccf;
    spacing: 2px;
    padding: 3px 6px;
}
QToolButton {
    background: transparent;
    border: 1px solid transparent;
    border-radius: 5px;
    padding: 5px 12px;
    color: #7c6d5b;
    font-size: 12px;
}
QToolButton:hover {
    background: #fffdf9;
    border-color: #e6dccf;
    color: #3f3428;
}
QToolButton:pressed  { background: #f4e8da; }

/* ════════════════════════ Slider ════════════════════════════════════════ */
QSlider::groove:horizontal {
    height: 3px;
    background: #e6dccf;
    border-radius: 2px;
}
QSlider::handle:horizontal {
    background: #f29f4b;
    border: 2px solid #e6953d;
    width: 14px; height: 14px;
    border-radius: 7px;
    margin: -6px 0;
}
QSlider::handle:horizontal:hover { background: #f6b56b; }
QSlider::sub-page:horizontal {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                stop:0 #e6953d, stop:1 #f29f4b);
    border-radius: 2px;
}

/* ════════════════════════ SpinBox ══════════════════════════════════════ */
QSpinBox, QDoubleSpinBox {
    background: #fffdf9;
    border: 1px solid #c8b49e;
    border-radius: 5px;
    padding: 4px 6px;
    color: #3f3428;
    selection-background-color: #f6b56b;
}
QSpinBox:focus, QDoubleSpinBox:focus { border-color: #f29f4b; }
QSpinBox::up-button, QSpinBox::down-button,
QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {
    background: #fff4e8;
    border: none;
    width: 18px;
}
QSpinBox::up-button:hover, QSpinBox::down-button:hover,
QDoubleSpinBox::up-button:hover, QDoubleSpinBox::down-button:hover {
    background: #efddc8;
}

/* ════════════════════════ CheckBox ══════════════════════════════════════ */
QCheckBox { spacing: 7px; color: #7c6d5b; }
QCheckBox::indicator {
    width: 14px; height: 14px;
    border: 1px solid #c0ad96;
    border-radius: 3px;
    background: #fffdf9;
}
QCheckBox::indicator:checked {
    background: #e6953d;
    border-color: #f29f4b;
    image: none;
}

/* ════════════════════════ Tree ══════════════════════════════════════════ */
QTreeWidget {
    background: #f2ece4;
    alternate-background-color: #faf5ee;
    border: none;
    show-decoration-selected: 1;
}
QTreeWidget::item {
    padding: 3px 2px;
    border-radius: 3px;
}
QTreeWidget::item:selected {
    background: #f6c38c;
    color: #3f3428;
}
QTreeWidget::item:hover:!selected { background: #f6efe6; }
QTreeWidget QHeaderView::section {
    background: #fff7ee;
    border: none;
    border-bottom: 1px solid #e6dccf;
    padding: 5px 8px;
    color: #9f8f7b;
    font-size: 11px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}

/* ════════════════════════ Table ════════════════════════════════════════ */
QTableWidget {
    background: #f2ece4;
    gridline-color: #eee4d8;
    alternate-background-color: #faf4ec;
    border: none;
    selection-background-color: #f6c38c;
}
QTableWidget::item { padding: 4px 8px; }
QTableWidget::item:selected { color: #3f3428; }
QTableWidget QHeaderView::section {
    background: #fff9f2;
    border: none;
    border-bottom: 1px solid #e6dccf;
    border-right: 1px solid #eadfce;
    padding: 6px 8px;
    color: #f29f4b;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.3px;
}
QTableCornerButton::section { background: #fff9f2; }

/* ════════════════════════ ScrollBar ════════════════════════════════════ */
QScrollBar:vertical {
    background: transparent;
    width: 6px; border-radius: 3px;
}
QScrollBar::handle:vertical {
    background: #e6dccf;
    border-radius: 3px;
    min-height: 24px;
}
QScrollBar::handle:vertical:hover { background: #d8cbb8; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar:horizontal {
    background: transparent;
    height: 6px; border-radius: 3px;
}
QScrollBar::handle:horizontal {
    background: #e6dccf;
    border-radius: 3px;
    min-width: 24px;
}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }

/* ════════════════════════ TabWidget / TabBar ════════════════════════════ */
QTabWidget::pane {
    border: 1px solid #e6dccf;
    border-top: none;
    background: #f7f4ef;
}
QTabWidget::tab-bar { alignment: left; }
QTabBar {
    background: transparent;
}
QTabBar::tab {
    background: #efe8de;
    border: 1px solid #e6dccf;
    border-bottom: none;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    padding: 6px 18px 5px 18px;
    color: #9f8f7b;
    font-size: 12px;
    font-weight: 500;
    margin-right: 2px;
    min-width: 80px;
}
QTabBar::tab:selected {
    background: #f7f4ef;
    color: #e8963a;
    font-weight: 700;
    border-top: 2px solid #f29f4b;
}
QTabBar::tab:hover:!selected {
    background: #f6efe6;
    color: #5a4d3e;
}

/* ════════════════════════ LineEdit ══════════════════════════════════════ */
QLineEdit {
    background: #fffdf9;
    border: 1px solid #c8b49e;
    border-radius: 5px;
    padding: 4px 8px;
    color: #3f3428;
    selection-background-color: #f6b56b;
    min-height: 22px;
}
QLineEdit:focus { border-color: #f29f4b; background: #fffef9; }
QLineEdit:disabled { background: #f5f0ea; color: #b0a090; }
QLineEdit:read-only { background: #f5f0ea; color: #8a7a6a; }

/* ════════════════════════ ComboBox ══════════════════════════════════════ */
QComboBox {
    background: #fffdf9;
    border: 1px solid #c8b49e;
    border-radius: 5px;
    padding: 4px 28px 4px 8px;
    color: #3f3428;
    min-height: 22px;
}
QComboBox:focus { border-color: #f29f4b; }
QComboBox:disabled { background: #f5f0ea; color: #b0a090; }
QComboBox::drop-down {
    subcontrol-origin: padding;
    subcontrol-position: right center;
    border: none;
    width: 22px;
    border-top-right-radius: 5px;
    border-bottom-right-radius: 5px;
    background: transparent;
}
QComboBox::down-arrow {
    width: 0; height: 0;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid #9f8f7b;
}
QComboBox QAbstractItemView {
    background: #fffdf9;
    border: 1px solid #e6dccf;
    border-radius: 4px;
    selection-background-color: #f6c38c;
    selection-color: #3f3428;
    color: #3f3428;
    padding: 2px;
}

/* ════════════════════════ Dialog ════════════════════════════════════════ */
QDialog {
    background: #f7f4ef;
}
QDialogButtonBox QPushButton {
    min-width: 80px;
}

/* ════════════════════════ MenuBar / Menu ════════════════════════════════ */
QMenuBar {
    background: #f2ece4;
    border-bottom: 1px solid #e6dccf;
}
QMenuBar::item { padding: 5px 12px; color: #7c6d5b; }
QMenuBar::item:selected { background: #fffdf9; color: #3f3428; }
QMenu {
    background: #fffdf9;
    border: 1px solid #e6dccf;
    border-radius: 5px;
    padding: 4px 0;
}
QMenu::item { padding: 6px 22px 6px 16px; color: #6f6254; }
QMenu::item:selected { background: #f6c38c; color: #3f3428; }
QMenu::separator { height: 1px; background: #e6dccf; margin: 3px 8px; }

/* ════════════════════════ StatusBar ═════════════════════════════════════ */
QStatusBar {
    background: #f0e9e0;
    color: #8a7a6a;
    border-top: 1px solid #e6dccf;
    font-size: 11px;
    padding: 2px 10px;
}
QStatusBar::item { border: none; }

/* ════════════════════════ ProgressBar ══════════════════════════════════ */
QProgressBar {
    background: #fffdf9;
    border: 1px solid #e6dccf;
    border-radius: 4px;
    text-align: center;
    font-size: 11px;
    color: #7c6d5b;
    max-height: 14px;
}
QProgressBar::chunk {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                                stop:0 #e6953d, stop:1 #f29f4b);
    border-radius: 3px;
}

/* ════════════════════════ TextEdit ══════════════════════════════════════ */
QTextEdit {
    background: #f2ece4;
    border: 1px solid #e6dccf;
    border-radius: 4px;
    color: #9f8f7b;
    font-family: 'Consolas', 'Courier New', monospace;
    font-size: 11px;
}

/* ════════════════════════ GraphicsView ══════════════════════════════════ */
QGraphicsView {
    background: #fbf8f3;
    border: none;
}

/* ════════════════════════ ScrollArea ════════════════════════════════════ */
QScrollArea { border: none; background: transparent; }
QScrollArea > QWidget > QWidget { background: transparent; }

/* ════════════════════════ Right panel — stronger input borders ══════════ */
/* The right panel (#fff7ee bg) is close in tone to the default widget      */
/* backgrounds, making 1px light borders nearly invisible. Darken them.     */
QFrame#rightPanel QSpinBox,
QFrame#rightPanel QDoubleSpinBox {
    border: 1.5px solid #8a7060;
    background: #ffffff;
    border-radius: 5px;
    color: #3f3428;
}
QFrame#rightPanel QSpinBox:hover,
QFrame#rightPanel QDoubleSpinBox:hover {
    border-color: #6a5040;
}
QFrame#rightPanel QSpinBox:focus,
QFrame#rightPanel QDoubleSpinBox:focus {
    border-color: #f29f4b;
}
QFrame#rightPanel QComboBox {
    border: 1.5px solid #8a7060;
    background: #ffffff;
    color: #3f3428;
}
QFrame#rightPanel QComboBox:hover {
    border-color: #6a5040;
}
QFrame#rightPanel QComboBox:focus {
    border-color: #f29f4b;
}
QFrame#rightPanel QComboBox::down-arrow {
    border-top-color: #6b5a4a;
}
QFrame#rightPanel QLineEdit {
    border: 1.5px solid #8a7060;
    background: #ffffff;
    color: #3f3428;
}
QFrame#rightPanel QLineEdit:hover {
    border-color: #6a5040;
}
QFrame#rightPanel QLineEdit:focus {
    border-color: #f29f4b;
}
QFrame#rightPanel QCheckBox::indicator {
    border: 1.5px solid #8a7060;
    border-radius: 3px;
    background: #ffffff;
}
QFrame#rightPanel QCheckBox::indicator:checked {
    background: #e6953d;
    border-color: #f29f4b;
}
QFrame#rightPanel QPushButton {
    background: #f0e8e0;
    border: 1.5px solid #8a7060;
    color: #4a3828;
}
QFrame#rightPanel QPushButton:hover {
    border-color: #6a5040;
}
QFrame#rightPanel QPushButton:focus {
    border-color: #f29f4b;
}

/* ════════════════════════ Profile delete button ═════════════════════════ */
/* Quiet by default; danger colour only on hover — avoids visual clutter   */
/* in the section header while remaining immediately recognisable.          */
QPushButton#profileDeleteBtn {
    background: transparent;
    border: none;
    color: #c8b8a8;
    font-size: 14px;
    font-weight: 700;
    padding: 0;
    border-radius: 3px;
    min-height: 0;
}
QPushButton#profileDeleteBtn:hover {
    background: #f4d0c8;
    color: #b04030;
    border: 1px solid #efb6a0;
}
QPushButton#profileDeleteBtn:pressed {
    background: #ead0c8;
    color: #902820;
}
"""
