"""Control panel: nm/pixel input, GL threshold slider, morphological params."""

from __future__ import annotations
from PyQt6.QtWidgets import (
    QWidget, QFormLayout, QDoubleSpinBox, QSlider, QSpinBox,
    QLabel, QCheckBox, QGroupBox, QVBoxLayout, QHBoxLayout, QPushButton,
)
from PyQt6.QtCore import Qt, pyqtSignal
from ..core.preprocessor import PreprocessParams


class ControlPanel(QWidget):
    params_changed = pyqtSignal(float, PreprocessParams)   # nm_per_pixel, params
    run_single = pyqtSignal()
    run_batch = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(6)

        # ── Scale ─────────────────────────────────────────────────────────────
        scale_box = QGroupBox("Scale")
        scale_form = QFormLayout(scale_box)
        self._nm_px = QDoubleSpinBox()
        self._nm_px.setRange(0.01, 10000.0)
        self._nm_px.setValue(1.0)
        self._nm_px.setSuffix("  nm/pixel")
        self._nm_px.setDecimals(4)
        self._nm_px.valueChanged.connect(self._emit)
        scale_form.addRow("nm / pixel:", self._nm_px)
        root.addWidget(scale_box)

        # ── Detection ─────────────────────────────────────────────────────────
        det_box = QGroupBox("MG Detection")
        det_form = QFormLayout(det_box)

        self._thr_label = QLabel("128")
        self._thr_slider = QSlider(Qt.Orientation.Horizontal)
        self._thr_slider.setRange(0, 255)
        self._thr_slider.setValue(128)
        self._thr_slider.setTickInterval(16)
        self._thr_slider.valueChanged.connect(
            lambda v: (self._thr_label.setText(str(v)), self._emit())
        )
        thr_row = QHBoxLayout()
        thr_row.addWidget(self._thr_slider)
        thr_row.addWidget(self._thr_label)
        det_form.addRow("GL Threshold:", thr_row)

        self._min_area = QSpinBox()
        self._min_area.setRange(1, 100_000)
        self._min_area.setValue(50)
        self._min_area.setSuffix("  px²")
        self._min_area.valueChanged.connect(self._emit)
        det_form.addRow("Min blob area:", self._min_area)

        root.addWidget(det_box)

        # ── Pre-processing ────────────────────────────────────────────────────
        pre_box = QGroupBox("Pre-processing")
        pre_form = QFormLayout(pre_box)

        self._gauss_k = QSpinBox()
        self._gauss_k.setRange(1, 31)
        self._gauss_k.setSingleStep(2)
        self._gauss_k.setValue(3)
        self._gauss_k.valueChanged.connect(self._emit)
        pre_form.addRow("Gaussian kernel:", self._gauss_k)

        self._morph_open_k = QSpinBox()
        self._morph_open_k.setRange(1, 31)
        self._morph_open_k.setSingleStep(2)
        self._morph_open_k.setValue(3)
        self._morph_open_k.valueChanged.connect(self._emit)
        pre_form.addRow("Morph open kernel:", self._morph_open_k)

        self._morph_close_k = QSpinBox()
        self._morph_close_k.setRange(1, 31)
        self._morph_close_k.setSingleStep(2)
        self._morph_close_k.setValue(5)
        self._morph_close_k.valueChanged.connect(self._emit)
        pre_form.addRow("Morph close kernel:", self._morph_close_k)

        self._use_clahe = QCheckBox("CLAHE contrast normalisation")
        self._use_clahe.setChecked(True)
        self._use_clahe.stateChanged.connect(self._emit)
        pre_form.addRow(self._use_clahe)

        root.addWidget(pre_box)

        # ── Actions ───────────────────────────────────────────────────────────
        btn_single = QPushButton("Run Single Image")
        btn_single.clicked.connect(self.run_single)
        btn_batch = QPushButton("Run Batch…")
        btn_batch.clicked.connect(self.run_batch)
        root.addWidget(btn_single)
        root.addWidget(btn_batch)
        root.addStretch()

    # ── public API ────────────────────────────────────────────────────────────

    def get_nm_per_pixel(self) -> float:
        return self._nm_px.value()

    def get_preprocess_params(self) -> PreprocessParams:
        return PreprocessParams(
            threshold=self._thr_slider.value(),
            gauss_kernel=self._gauss_k.value(),
            morph_open_k=self._morph_open_k.value(),
            morph_close_k=self._morph_close_k.value(),
            use_clahe=self._use_clahe.isChecked(),
        )

    def get_min_area(self) -> int:
        return self._min_area.value()

    def _emit(self) -> None:
        self.params_changed.emit(self.get_nm_per_pixel(), self.get_preprocess_params())
