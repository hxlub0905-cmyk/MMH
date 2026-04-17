"""Right-side control panel: scale, detection params, pre-processing, actions."""

from __future__ import annotations
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QFormLayout, QDoubleSpinBox,
    QSlider, QSpinBox, QLabel, QCheckBox, QGroupBox,
    QPushButton, QHBoxLayout, QScrollArea, QSizePolicy,
)
from PyQt6.QtCore import Qt, pyqtSignal
from ..core.preprocessor import PreprocessParams


class ControlPanel(QWidget):
    params_changed  = pyqtSignal(float, PreprocessParams)
    run_single      = pyqtSignal()
    run_batch       = pyqtSignal()
    quick_report    = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        inner = QWidget()
        self._layout = QVBoxLayout(inner)
        self._layout.setContentsMargins(10, 10, 10, 16)
        self._layout.setSpacing(10)

        self._build_scale()
        self._build_detection()
        self._build_preprocess()
        self._build_actions()
        self._build_batch_output()
        self._layout.addStretch()

        scroll.setWidget(inner)
        outer.addWidget(scroll)

    # ── section builders ──────────────────────────────────────────────────────

    def _build_scale(self) -> None:
        box = QGroupBox("Scale")
        form = QFormLayout(box)
        form.setSpacing(8)
        form.setContentsMargins(10, 4, 10, 8)

        self._nm_px = QDoubleSpinBox()
        self._nm_px.setRange(0.0001, 10000.0)
        self._nm_px.setValue(1.0)
        self._nm_px.setDecimals(4)
        self._nm_px.setSuffix(" nm/px")
        self._nm_px.valueChanged.connect(self._emit)
        form.addRow(_lbl("nm / pixel"), self._nm_px)
        self._layout.addWidget(box)

    def _build_detection(self) -> None:
        box = QGroupBox("MG Detection")
        vbox = QVBoxLayout(box)
        vbox.setSpacing(10)
        vbox.setContentsMargins(10, 4, 10, 8)

        # ── GL range ──────────────────────────────────────────────────────────
        vbox.addWidget(_lbl("GL Range  (pixels within range = MG)"))

        # Min row
        min_row = QHBoxLayout()
        min_row.addWidget(_lbl("Min"))
        self._gl_min_val = QLabel("100")
        self._gl_min_val.setObjectName("thresholdValue")
        self._gl_min_val.setFixedWidth(30)
        self._gl_min_slider = QSlider(Qt.Orientation.Horizontal)
        self._gl_min_slider.setRange(0, 255)
        self._gl_min_slider.setValue(100)
        self._gl_min_slider.valueChanged.connect(self._on_gl_min_changed)
        min_row.addWidget(self._gl_min_slider)
        min_row.addWidget(self._gl_min_val)
        vbox.addLayout(min_row)

        # Max row
        max_row = QHBoxLayout()
        max_row.addWidget(_lbl("Max"))
        self._gl_max_val = QLabel("220")
        self._gl_max_val.setObjectName("thresholdValue")
        self._gl_max_val.setFixedWidth(30)
        self._gl_max_slider = QSlider(Qt.Orientation.Horizontal)
        self._gl_max_slider.setRange(0, 255)
        self._gl_max_slider.setValue(220)
        self._gl_max_slider.valueChanged.connect(self._on_gl_max_changed)
        max_row.addWidget(self._gl_max_slider)
        max_row.addWidget(self._gl_max_val)
        vbox.addLayout(max_row)

        # Min area
        form = QFormLayout()
        form.setSpacing(7)
        self._min_area = QSpinBox()
        self._min_area.setRange(1, 500_000)
        self._min_area.setValue(50)
        self._min_area.setSuffix(" px²")
        self._min_area.valueChanged.connect(self._emit)
        form.addRow(_lbl("Min blob area"), self._min_area)
        vbox.addLayout(form)

        self._layout.addWidget(box)

    def _on_gl_min_changed(self, v: int) -> None:
        self._gl_min_val.setText(str(v))
        # prevent min from exceeding max
        if v > self._gl_max_slider.value():
            self._gl_max_slider.setValue(v)
        self._emit()

    def _on_gl_max_changed(self, v: int) -> None:
        self._gl_max_val.setText(str(v))
        # prevent max from going below min
        if v < self._gl_min_slider.value():
            self._gl_min_slider.setValue(v)
        self._emit()

    def _build_preprocess(self) -> None:
        box = QGroupBox("Pre-processing")
        form = QFormLayout(box)
        form.setSpacing(8)
        form.setContentsMargins(10, 4, 10, 8)

        self._gauss_k = QSpinBox()
        self._gauss_k.setRange(1, 31)
        self._gauss_k.setSingleStep(2)
        self._gauss_k.setValue(3)
        self._gauss_k.setSuffix(" px")
        self._gauss_k.valueChanged.connect(self._emit)
        form.addRow(_lbl("Gaussian"), self._gauss_k)

        self._morph_open_k = QSpinBox()
        self._morph_open_k.setRange(1, 31)
        self._morph_open_k.setSingleStep(2)
        self._morph_open_k.setValue(3)
        self._morph_open_k.setSuffix(" px")
        self._morph_open_k.valueChanged.connect(self._emit)
        form.addRow(_lbl("Morph open"), self._morph_open_k)

        self._morph_close_k = QSpinBox()
        self._morph_close_k.setRange(1, 31)
        self._morph_close_k.setSingleStep(2)
        self._morph_close_k.setValue(5)
        self._morph_close_k.setSuffix(" px")
        self._morph_close_k.valueChanged.connect(self._emit)
        form.addRow(_lbl("Morph close"), self._morph_close_k)

        self._use_clahe = QCheckBox("CLAHE normalisation")
        self._use_clahe.setChecked(True)
        self._use_clahe.stateChanged.connect(self._emit)
        form.addRow(self._use_clahe)

        self._layout.addWidget(box)

    def _build_actions(self) -> None:
        btn_single = QPushButton("▶  Run Single Image")
        btn_single.setObjectName("runSingle")
        btn_single.clicked.connect(self.run_single)
        btn_single.setMinimumHeight(38)

        btn_batch = QPushButton("⚡  Run Batch…")
        btn_batch.setObjectName("runBatch")
        btn_batch.clicked.connect(self.run_batch)
        btn_batch.setMinimumHeight(38)

        self._layout.addSpacing(4)
        self._layout.addWidget(btn_single)
        self._layout.addWidget(btn_batch)

        btn_report = QPushButton("📝  One-click Report")
        btn_report.clicked.connect(self.quick_report)
        btn_report.setMinimumHeight(34)
        self._layout.addWidget(btn_report)

    def _build_batch_output(self) -> None:
        box = QGroupBox("Batch Output")
        v = QVBoxLayout(box)
        v.setSpacing(6)
        v.setContentsMargins(10, 6, 10, 8)

        self._auto_export_ann = QCheckBox("Batch後自動輸出Overlay圖")
        self._auto_export_ann.setChecked(True)
        v.addWidget(self._auto_export_ann)

        self._exp_lines = QCheckBox("含 Lines")
        self._exp_lines.setChecked(True)
        self._exp_labels = QCheckBox("含 Values")
        self._exp_labels.setChecked(True)
        self._exp_boxes = QCheckBox("含 Boxes")
        self._exp_boxes.setChecked(False)
        self._exp_legend = QCheckBox("含 Legend")
        self._exp_legend.setChecked(True)
        for chk in (self._exp_lines, self._exp_labels, self._exp_boxes, self._exp_legend):
            v.addWidget(chk)

        self._layout.addWidget(box)

    # ── public API ────────────────────────────────────────────────────────────

    def get_nm_per_pixel(self) -> float:
        return self._nm_px.value()

    def get_preprocess_params(self) -> PreprocessParams:
        return PreprocessParams(
            gl_min=self._gl_min_slider.value(),
            gl_max=self._gl_max_slider.value(),
            gauss_kernel=self._gauss_k.value(),
            morph_open_k=self._morph_open_k.value(),
            morph_close_k=self._morph_close_k.value(),
            use_clahe=self._use_clahe.isChecked(),
        )

    def get_min_area(self) -> int:
        return self._min_area.value()

    def _emit(self) -> None:
        self.params_changed.emit(self.get_nm_per_pixel(), self.get_preprocess_params())

    def should_auto_export_annotated(self) -> bool:
        return self._auto_export_ann.isChecked()

    def get_export_overlay_opts(self) -> dict[str, bool]:
        return {
            "show_lines": self._exp_lines.isChecked(),
            "show_labels": self._exp_labels.isChecked(),
            "show_boxes": self._exp_boxes.isChecked(),
            "show_legend": self._exp_legend.isChecked(),
        }


def _lbl(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet("color: #7c6d5b; font-size: 12px;")
    return lbl
