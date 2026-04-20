"""Right-side control panel: scale, preprocess, and dynamic measurement profiles."""

from __future__ import annotations
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QFormLayout, QDoubleSpinBox,
    QSlider, QSpinBox, QLabel, QCheckBox, QGroupBox,
    QPushButton, QHBoxLayout, QScrollArea, QSizePolicy, QComboBox,
    QToolButton, QInputDialog, QFrame,
)
from PyQt6.QtCore import Qt, pyqtSignal
from ..core.preprocessor import PreprocessParams


class ControlPanel(QWidget):
    params_changed = pyqtSignal(float, PreprocessParams)
    run_single = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        inner = QWidget()
        self._layout = QVBoxLayout(inner)
        self._layout.setContentsMargins(10, 10, 10, 16)
        self._layout.setSpacing(10)

        self._build_scale()
        self._build_preprocess()
        self._build_measurement_profiles()
        self._build_actions()
        self._layout.addStretch()

        scroll.setWidget(inner)
        outer.addWidget(scroll)

    def _build_scale(self) -> None:
        box = QGroupBox("Scale")
        form = QFormLayout(box)

        self._nm_px = QDoubleSpinBox()
        self._nm_px.setRange(0.0001, 10000.0)
        self._nm_px.setValue(1.0)
        self._nm_px.setDecimals(4)
        self._nm_px.setSuffix(" nm/px")
        self._nm_px.valueChanged.connect(self._emit)
        form.addRow(_lbl("nm / pixel"), self._nm_px)
        self._layout.addWidget(box)

    def _build_preprocess(self) -> None:
        box = QGroupBox("Pre-processing")
        form = QFormLayout(box)

        self._gauss_k = QSpinBox(); self._gauss_k.setRange(1, 31); self._gauss_k.setSingleStep(2); self._gauss_k.setValue(3)
        self._morph_open_k = QSpinBox(); self._morph_open_k.setRange(1, 31); self._morph_open_k.setSingleStep(2); self._morph_open_k.setValue(3)
        self._morph_close_k = QSpinBox(); self._morph_close_k.setRange(1, 31); self._morph_close_k.setSingleStep(2); self._morph_close_k.setValue(5)
        self._use_clahe = QCheckBox("CLAHE normalisation"); self._use_clahe.setChecked(True)

        self._gauss_k.valueChanged.connect(self._emit)
        self._morph_open_k.valueChanged.connect(self._emit)
        self._morph_close_k.valueChanged.connect(self._emit)
        self._use_clahe.stateChanged.connect(self._emit)

        self._gauss_k.setSuffix(" px")
        self._morph_open_k.setSuffix(" px")
        self._morph_close_k.setSuffix(" px")

        form.addRow(_lbl("Gaussian"), self._gauss_k)
        form.addRow(_lbl("Morph open"), self._morph_open_k)
        form.addRow(_lbl("Morph close"), self._morph_close_k)
        form.addRow(self._use_clahe)

        self._layout.addWidget(box)

    def _build_measurement_profiles(self) -> None:
        box = QGroupBox("Measurements")
        root = QVBoxLayout(box)

        header = QHBoxLayout()
        header.addWidget(_lbl("Add reusable measurement profiles"))
        header.addStretch()
        self._btn_add = QToolButton()
        self._btn_add.setText("＋")
        self._btn_add.setToolTip("Add measurement profile")
        self._btn_add.clicked.connect(self._on_add_profile)
        header.addWidget(self._btn_add)
        root.addLayout(header)

        self._profiles_layout = QVBoxLayout()
        self._profiles_layout.setSpacing(8)
        root.addLayout(self._profiles_layout)
        self._layout.addWidget(box)

        self._profiles: list[dict] = []

    def _build_actions(self) -> None:
        btn_single = QPushButton("▶  Run Single Image")
        btn_single.setObjectName("runSingle")
        btn_single.clicked.connect(self.run_single)
        btn_single.setMinimumHeight(38)
        self._layout.addWidget(btn_single)

    def _on_add_profile(self) -> None:
        name, ok = QInputDialog.getText(self, "Add Measurement", "Profile name:", text=f"Measure {len(self._profiles)+1}")
        if not ok:
            return
        self._add_profile(name.strip() or f"Measure {len(self._profiles)+1}")

    def _add_profile(self, name: str) -> None:
        box = QGroupBox(name)
        form = QFormLayout(box)

        axis = QComboBox(); axis.addItems(["Y-CD", "X-CD"])
        min_val = QLabel("100"); min_val.setObjectName("thresholdValue"); min_val.setFixedWidth(34)
        max_val = QLabel("220"); max_val.setObjectName("thresholdValue"); max_val.setFixedWidth(34)
        gl_min = QSlider(Qt.Orientation.Horizontal); gl_min.setRange(0, 255); gl_min.setValue(100)
        gl_max = QSlider(Qt.Orientation.Horizontal); gl_max.setRange(0, 255); gl_max.setValue(220)

        min_row = QHBoxLayout(); min_row.addWidget(_lbl("Min")); min_row.addWidget(gl_min); min_row.addWidget(min_val)
        max_row = QHBoxLayout(); max_row.addWidget(_lbl("Max")); max_row.addWidget(gl_max); max_row.addWidget(max_val)
        min_wrap = QWidget(); min_wrap.setLayout(min_row)
        max_wrap = QWidget(); max_wrap.setLayout(max_row)

        min_area = QSpinBox(); min_area.setRange(1, 500_000); min_area.setValue(50); min_area.setSuffix(" px²")

        # Geometric filters (0 = disabled)
        min_ar  = QDoubleSpinBox(); min_ar.setRange(0.0, 100.0);  min_ar.setValue(0.0);  min_ar.setSingleStep(0.1);  min_ar.setSpecialValueText("off")
        max_ar  = QDoubleSpinBox(); max_ar.setRange(0.0, 100.0);  max_ar.setValue(0.0);  max_ar.setSingleStep(0.1);  max_ar.setSpecialValueText("off")
        min_w   = QSpinBox();        min_w.setRange(0, 9999);      min_w.setValue(0);     min_w.setSuffix(" px");     min_w.setSpecialValueText("off")
        min_h   = QSpinBox();        min_h.setRange(0, 9999);      min_h.setValue(0);     min_h.setSuffix(" px");     min_h.setSpecialValueText("off")

        enabled = QCheckBox("Enabled"); enabled.setChecked(True)

        def on_min(v: int) -> None:
            if v > gl_max.value():
                gl_max.setValue(v)
            min_val.setText(str(v))
            self._emit()

        def on_max(v: int) -> None:
            if v < gl_min.value():
                gl_min.setValue(v)
            max_val.setText(str(v))
            self._emit()

        gl_min.valueChanged.connect(on_min)
        gl_max.valueChanged.connect(on_max)
        axis.currentIndexChanged.connect(self._emit)
        min_area.valueChanged.connect(self._emit)
        for w in (min_ar, max_ar, min_w, min_h):
            w.valueChanged.connect(self._emit)
        enabled.stateChanged.connect(self._emit)

        form.addRow("Enable", enabled)
        form.addRow("Axis", axis)
        form.addRow("GL Min", min_wrap)
        form.addRow("GL Max", max_wrap)
        form.addRow("Min blob area", min_area)

        sep = QFrame(); sep.setFrameShape(QFrame.Shape.HLine); sep.setStyleSheet("color:#d0c8bc")
        form.addRow(sep)
        form.addRow("Min aspect (h/w)", min_ar)
        form.addRow("Max aspect (h/w)", max_ar)
        form.addRow("Min width", min_w)
        form.addRow("Min height", min_h)

        self._profiles_layout.addWidget(box)
        self._profiles.append({
            "name": name,
            "enabled": enabled,
            "axis": axis,
            "gl_min": gl_min,
            "gl_max": gl_max,
            "min_area": min_area,
            "min_aspect_ratio": min_ar,
            "max_aspect_ratio": max_ar,
            "min_width": min_w,
            "min_height": min_h,
        })
        self._emit()

    # ── public API ────────────────────────────────────────────────────────────

    def get_nm_per_pixel(self) -> float:
        return self._nm_px.value()

    def get_preprocess_params(self) -> PreprocessParams:
        # gl_min/gl_max are profile-specific now; defaults here are placeholders.
        return PreprocessParams(
            gl_min=100,
            gl_max=220,
            gauss_kernel=self._gauss_k.value(),
            morph_open_k=self._morph_open_k.value(),
            morph_close_k=self._morph_close_k.value(),
            use_clahe=self._use_clahe.isChecked(),
        )

    def get_measurement_cards(self) -> list[dict]:
        out = []
        for i, p in enumerate(self._profiles):
            if not p["enabled"].isChecked():
                continue
            out.append({
                "card_id": i,
                "name": p["name"],
                "axis": "Y" if p["axis"].currentText().startswith("Y") else "X",
                "gl_min": p["gl_min"].value(),
                "gl_max": p["gl_max"].value(),
                "min_area": p["min_area"].value(),
                "min_aspect_ratio": p["min_aspect_ratio"].value(),
                "max_aspect_ratio": p["max_aspect_ratio"].value(),
                "min_width": p["min_width"].value(),
                "min_height": p["min_height"].value(),
            })
        return out

    def get_min_area(self) -> int:
        cards = self.get_measurement_cards()
        return cards[0]["min_area"] if cards else 50

    def _emit(self) -> None:
        self.params_changed.emit(self.get_nm_per_pixel(), self.get_preprocess_params())


def _lbl(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet("color: #7c6d5b; font-size: 12px;")
    return lbl
