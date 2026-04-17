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
    font-family: 'Segoe UI', Arial, sans-serif;
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
    border-radius: 7px;
    margin-top: 16px;
    padding: 10px 8px 8px 8px;
    background: #fff9f2;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 6px;
    color: #f29f4b;
    font-weight: 600;
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
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
    border: 1px solid #e6dccf;
    border-radius: 6px;
    padding: 6px 14px;
    font-weight: 500;
}
QPushButton:hover {
    background: #fff4e8;
    border-color: #d8cbb8;
    color: #3f3428;
}
QPushButton:pressed { background: #f4e8da; }
QPushButton:disabled { color: #d8cbb8; border-color: #d3c4ae; }

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
    border: 1px solid #e6dccf;
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
    border: 1px solid #d8cbb8;
    border-radius: 3px;
    background: #fffdf9;
}
QCheckBox::indicator:checked {
    background: #e6953d;
    border-color: #f29f4b;
    image: none;
}
QCheckBox::indicator:checked::after {
    content: "✓";
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
    background: #f2ece4;
    color: #9f8f7b;
    border-top: 1px solid #e6dccf;
    font-size: 11px;
    padding: 2px 8px;
}

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
"""
