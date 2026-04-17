"""Application-wide dark theme QSS stylesheet and colour constants."""

# ── Colour tokens ──────────────────────────────────────────────────────────────
BG_BASE       = "#0d0e1a"
BG_PANEL      = "#13142a"
BG_SURFACE    = "#1c1d35"
BG_ELEVATED   = "#23253f"
BORDER        = "#2a2d50"
BORDER_LIGHT  = "#3a3e68"
ACCENT        = "#4f7fc2"
ACCENT_HOVER  = "#6a9ad8"
ACCENT_ACTIVE = "#3a6ab4"
TEXT_PRIMARY  = "#dde3f5"
TEXT_SECONDARY= "#8892b0"
TEXT_MUTED    = "#505878"
SUCCESS       = "#3fb97a"
WARNING       = "#d4a03a"
DANGER        = "#d45a5a"
MIN_COLOUR    = "#e05555"   # used in annotator
MAX_COLOUR    = "#5588ee"   # used in annotator
NORM_COLOUR   = "#44aadd"   # used in annotator

STYLE = """
/* ════════════════════════ Base ══════════════════════════════════════════ */
* {
    outline: 0;
}
QWidget {
    background-color: #0d0e1a;
    color: #dde3f5;
    font-family: 'Segoe UI', Arial, sans-serif;
    font-size: 13px;
    border: none;
}
QMainWindow::separator { background: #2a2d50; width: 1px; height: 1px; }

/* ════════════════════════ Panels / Frames ════════════════════════════════ */
QFrame#leftPanel {
    background: #10112a;
    border-right: 1px solid #2a2d50;
}
QFrame#rightPanel {
    background: #10112a;
    border-left: 1px solid #2a2d50;
}
QFrame#viewerHeader {
    background: #13142a;
    border-bottom: 1px solid #2a2d50;
    min-height: 38px;
    max-height: 38px;
}
QFrame#resultsHeader {
    background: #13142a;
    border-top: 1px solid #2a2d50;
    border-bottom: 1px solid #2a2d50;
    min-height: 30px;
    max-height: 30px;
}
QGroupBox {
    border: 1px solid #2a2d50;
    border-radius: 7px;
    margin-top: 16px;
    padding: 10px 8px 8px 8px;
    background: #13142a;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 6px;
    color: #4f7fc2;
    font-weight: 600;
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}

/* ════════════════════════ Splitter ══════════════════════════════════════ */
QSplitter::handle {
    background: #2a2d50;
}
QSplitter::handle:horizontal { width: 1px; }
QSplitter::handle:vertical   { height: 1px; }

/* ════════════════════════ Labels ════════════════════════════════════════ */
QLabel { color: #8892b0; background: transparent; }
QLabel#panelTitle {
    color: #4f7fc2;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 1.5px;
    text-transform: uppercase;
    padding: 8px 12px 4px 12px;
}
QLabel#statusChip {
    color: #44aadd;
    background: #1a2a40;
    border: 1px solid #2a4060;
    border-radius: 10px;
    padding: 2px 10px;
    font-size: 11px;
}
QLabel#thresholdValue {
    color: #4f7fc2;
    font-size: 14px;
    font-weight: 700;
    min-width: 30px;
}

/* ════════════════════════ Buttons — default ══════════════════════════════ */
QPushButton {
    background: #1c1d35;
    color: #b0bcd8;
    border: 1px solid #2a2d50;
    border-radius: 6px;
    padding: 6px 14px;
    font-weight: 500;
}
QPushButton:hover {
    background: #23253f;
    border-color: #3a3e68;
    color: #dde3f5;
}
QPushButton:pressed { background: #141528; }
QPushButton:disabled { color: #3a3e68; border-color: #1e2038; }

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
    background: #2d4a80;
    border-color: #4f7fc2;
    color: #ffffff;
}

/* Run Single — green accent */
QPushButton#runSingle {
    background: #1a3a28;
    border: 1px solid #2a6040;
    color: #6de8a0;
    border-radius: 7px;
    padding: 8px 0;
    font-weight: 600;
}
QPushButton#runSingle:hover {
    background: #204a32;
    border-color: #3a8050;
    color: #90ffbb;
}
QPushButton#runSingle:pressed { background: #152e20; }

/* Run Batch — purple accent */
QPushButton#runBatch {
    background: #2a1a40;
    border: 1px solid #5040a0;
    color: #c090ff;
    border-radius: 7px;
    padding: 8px 0;
    font-weight: 600;
}
QPushButton#runBatch:hover {
    background: #382050;
    border-color: #7060c0;
    color: #d8b0ff;
}
QPushButton#runBatch:pressed { background: #1e1230; }

/* ════════════════════════ Toolbar ══════════════════════════════════════ */
QToolBar {
    background: #0a0b18;
    border-bottom: 1px solid #2a2d50;
    spacing: 2px;
    padding: 3px 6px;
}
QToolButton {
    background: transparent;
    border: 1px solid transparent;
    border-radius: 5px;
    padding: 5px 12px;
    color: #8892b0;
    font-size: 12px;
}
QToolButton:hover {
    background: #1c1d35;
    border-color: #2a2d50;
    color: #dde3f5;
}
QToolButton:pressed  { background: #141528; }

/* ════════════════════════ Slider ════════════════════════════════════════ */
QSlider::groove:horizontal {
    height: 3px;
    background: #2a2d50;
    border-radius: 2px;
}
QSlider::handle:horizontal {
    background: #4f7fc2;
    border: 2px solid #2d5598;
    width: 14px; height: 14px;
    border-radius: 7px;
    margin: -6px 0;
}
QSlider::handle:horizontal:hover { background: #6a9ad8; }
QSlider::sub-page:horizontal {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                stop:0 #2d5598, stop:1 #4f7fc2);
    border-radius: 2px;
}

/* ════════════════════════ SpinBox ══════════════════════════════════════ */
QSpinBox, QDoubleSpinBox {
    background: #1c1d35;
    border: 1px solid #2a2d50;
    border-radius: 5px;
    padding: 4px 6px;
    color: #dde3f5;
    selection-background-color: #2d4a80;
}
QSpinBox:focus, QDoubleSpinBox:focus { border-color: #4f7fc2; }
QSpinBox::up-button, QSpinBox::down-button,
QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {
    background: #23253f;
    border: none;
    width: 18px;
}
QSpinBox::up-button:hover, QSpinBox::down-button:hover,
QDoubleSpinBox::up-button:hover, QDoubleSpinBox::down-button:hover {
    background: #2d3060;
}

/* ════════════════════════ CheckBox ══════════════════════════════════════ */
QCheckBox { spacing: 7px; color: #8892b0; }
QCheckBox::indicator {
    width: 14px; height: 14px;
    border: 1px solid #3a3e68;
    border-radius: 3px;
    background: #1c1d35;
}
QCheckBox::indicator:checked {
    background: #2d5598;
    border-color: #4f7fc2;
    image: none;
}
QCheckBox::indicator:checked::after {
    content: "✓";
}

/* ════════════════════════ Tree ══════════════════════════════════════════ */
QTreeWidget {
    background: #0a0b18;
    alternate-background-color: #0f1020;
    border: none;
    show-decoration-selected: 1;
}
QTreeWidget::item {
    padding: 3px 2px;
    border-radius: 3px;
}
QTreeWidget::item:selected {
    background: #1e3360;
    color: #dde3f5;
}
QTreeWidget::item:hover:!selected { background: #161830; }
QTreeWidget QHeaderView::section {
    background: #10112a;
    border: none;
    border-bottom: 1px solid #2a2d50;
    padding: 5px 8px;
    color: #505878;
    font-size: 11px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}

/* ════════════════════════ Table ════════════════════════════════════════ */
QTableWidget {
    background: #0a0b18;
    gridline-color: #191a30;
    alternate-background-color: #0e0f22;
    border: none;
    selection-background-color: #1e3360;
}
QTableWidget::item { padding: 4px 8px; }
QTableWidget::item:selected { color: #dde3f5; }
QTableWidget QHeaderView::section {
    background: #13142a;
    border: none;
    border-bottom: 1px solid #2a2d50;
    border-right: 1px solid #1e2040;
    padding: 6px 8px;
    color: #4f7fc2;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.3px;
}
QTableCornerButton::section { background: #13142a; }

/* ════════════════════════ ScrollBar ════════════════════════════════════ */
QScrollBar:vertical {
    background: transparent;
    width: 6px; border-radius: 3px;
}
QScrollBar::handle:vertical {
    background: #2a2d50;
    border-radius: 3px;
    min-height: 24px;
}
QScrollBar::handle:vertical:hover { background: #3a3e68; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar:horizontal {
    background: transparent;
    height: 6px; border-radius: 3px;
}
QScrollBar::handle:horizontal {
    background: #2a2d50;
    border-radius: 3px;
    min-width: 24px;
}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }

/* ════════════════════════ MenuBar / Menu ════════════════════════════════ */
QMenuBar {
    background: #0a0b18;
    border-bottom: 1px solid #2a2d50;
}
QMenuBar::item { padding: 5px 12px; color: #8892b0; }
QMenuBar::item:selected { background: #1c1d35; color: #dde3f5; }
QMenu {
    background: #1c1d35;
    border: 1px solid #2a2d50;
    border-radius: 5px;
    padding: 4px 0;
}
QMenu::item { padding: 6px 22px 6px 16px; color: #b0bcd8; }
QMenu::item:selected { background: #1e3360; color: #dde3f5; }
QMenu::separator { height: 1px; background: #2a2d50; margin: 3px 8px; }

/* ════════════════════════ StatusBar ═════════════════════════════════════ */
QStatusBar {
    background: #0a0b18;
    color: #505878;
    border-top: 1px solid #2a2d50;
    font-size: 11px;
    padding: 2px 8px;
}

/* ════════════════════════ ProgressBar ══════════════════════════════════ */
QProgressBar {
    background: #1c1d35;
    border: 1px solid #2a2d50;
    border-radius: 4px;
    text-align: center;
    font-size: 11px;
    color: #8892b0;
    max-height: 14px;
}
QProgressBar::chunk {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                                stop:0 #2d5598, stop:1 #4f7fc2);
    border-radius: 3px;
}

/* ════════════════════════ TextEdit ══════════════════════════════════════ */
QTextEdit {
    background: #0a0b18;
    border: 1px solid #2a2d50;
    border-radius: 4px;
    color: #505878;
    font-family: 'Consolas', 'Courier New', monospace;
    font-size: 11px;
}

/* ════════════════════════ GraphicsView ══════════════════════════════════ */
QGraphicsView {
    background: #050610;
    border: none;
}

/* ════════════════════════ ScrollArea ════════════════════════════════════ */
QScrollArea { border: none; background: transparent; }
QScrollArea > QWidget > QWidget { background: transparent; }
"""
