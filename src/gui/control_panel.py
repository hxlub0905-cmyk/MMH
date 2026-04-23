"""Right-side control panel: scale, preprocess, and dynamic measurement profiles."""

from __future__ import annotations
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QFormLayout, QDoubleSpinBox,
    QSlider, QSpinBox, QLabel, QCheckBox,
    QPushButton, QHBoxLayout, QSizePolicy, QComboBox,
    QInputDialog,
)
from PyQt6.QtCore import Qt, pyqtSignal
from ..core.preprocessor import PreprocessParams
from .collapsible import CollapsibleSection


def _set_expanding(w) -> None:
    """Make a form-field widget expand horizontally to fill available space."""
    w.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)


class ControlPanel(QWidget):
    params_changed = pyqtSignal(float, PreprocessParams)
    run_single = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(0)

        self._build_scale()
        self._build_preprocess()
        self._build_measurement_profiles()
        self._build_actions()

    def _build_scale(self) -> None:
        sec = CollapsibleSection("Scale", tier=2, collapsed=False,
                                  content_margins=(8, 4, 8, 8))
        fw = QWidget(); fw.setStyleSheet("background:transparent; border:none;")
        form = QFormLayout(fw)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        form.setContentsMargins(0, 0, 0, 0); form.setSpacing(5)

        self._nm_px = QDoubleSpinBox()
        self._nm_px.setRange(0.0001, 10000.0)
        self._nm_px.setValue(1.0)
        self._nm_px.setDecimals(4)
        self._nm_px.setSuffix(" nm/px")
        self._nm_px.valueChanged.connect(self._emit)
        _set_expanding(self._nm_px)
        form.addRow(_lbl("nm / pixel"), self._nm_px)

        sec.add_widget(fw)
        self._layout.addWidget(sec)

    def _build_preprocess(self) -> None:
        sec = CollapsibleSection("Pre-processing", tier=2, collapsed=True,
                                  content_margins=(8, 4, 8, 8))
        fw = QWidget(); fw.setStyleSheet("background:transparent; border:none;")
        form = QFormLayout(fw)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        form.setContentsMargins(0, 0, 0, 0); form.setSpacing(5)

        self._gauss_k = QSpinBox(); self._gauss_k.setRange(1, 31); self._gauss_k.setSingleStep(2); self._gauss_k.setValue(3)
        self._morph_open_k = QSpinBox(); self._morph_open_k.setRange(1, 31); self._morph_open_k.setSingleStep(2); self._morph_open_k.setValue(3)
        self._morph_close_k = QSpinBox(); self._morph_close_k.setRange(1, 31); self._morph_close_k.setSingleStep(2); self._morph_close_k.setValue(5)
        self._use_clahe = QCheckBox("CLAHE normalisation"); self._use_clahe.setChecked(True)

        self._gauss_k.valueChanged.connect(self._emit)
        self._morph_open_k.valueChanged.connect(self._emit)
        self._morph_close_k.valueChanged.connect(self._emit)
        self._use_clahe.stateChanged.connect(self._emit)

        self._gauss_k.setSuffix(" px");       _set_expanding(self._gauss_k)
        self._morph_open_k.setSuffix(" px");  _set_expanding(self._morph_open_k)
        self._morph_close_k.setSuffix(" px"); _set_expanding(self._morph_close_k)

        form.addRow(_lbl("Gaussian"), self._gauss_k)
        form.addRow(_lbl("Morph open"), self._morph_open_k)
        form.addRow(_lbl("Morph close"), self._morph_close_k)
        form.addRow(self._use_clahe)

        sec.add_widget(fw)
        self._layout.addWidget(sec)

    def _build_measurement_profiles(self) -> None:
        sec = CollapsibleSection("Measurements", tier=1, collapsed=False,
                                  content_margins=(6, 4, 6, 8))

        add_bar = QWidget(); add_bar.setStyleSheet("border:none; background:transparent;")
        add_hl = QHBoxLayout(add_bar); add_hl.setContentsMargins(2, 2, 2, 6)
        self._btn_add = QPushButton("＋  Add Measurement")
        self._btn_add.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._btn_add.setStyleSheet(
            "QPushButton { background:#f0f8f4; border:1px dashed #a8d4bc; border-radius:6px;"
            "  color:#4a8c6a; font-weight:600; padding:5px; }"
            "QPushButton:hover { background:#e0f4ec; border-color:#80c4a0; }"
        )
        self._btn_add.clicked.connect(self._on_add_profile)
        add_hl.addWidget(self._btn_add)
        sec.add_widget(add_bar)

        profiles_w = QWidget(); profiles_w.setStyleSheet("border:none; background:transparent;")
        self._profiles_layout = QVBoxLayout(profiles_w)
        self._profiles_layout.setContentsMargins(0, 0, 0, 0)
        self._profiles_layout.setSpacing(8)
        sec.add_widget(profiles_w)

        self._layout.addWidget(sec)
        self._profiles: list[dict] = []

    def _build_actions(self) -> None:
        # Run Single Image button removed — MeasureWorkspace already provides
        # "Run Single (F5)" to avoid duplicate run buttons in the UI.
        pass

    def _on_add_profile(self) -> None:
        name, ok = QInputDialog.getText(self, "Add Measurement", "Profile name:", text=f"Measure {len(self._profiles)+1}")
        if not ok:
            return
        self._add_profile(name.strip() or f"Measure {len(self._profiles)+1}")

    def _add_profile(self, name: str) -> None:
        outer = QWidget()
        # ⚠ Use bare property (no "QWidget { }" type-selector) so the rule
        #   applies ONLY to `outer` itself and does NOT cascade to child
        #   widgets (QComboBox, QSpinBox …) via Qt's stylesheet inheritance.
        outer.setStyleSheet(
            "background:#fff9f2; border:1px solid #c8b8a8; border-radius:8px;"
        )
        outer_layout = QVBoxLayout(outer)
        outer_layout.setContentsMargins(0, 0, 0, 6)
        outer_layout.setSpacing(0)

        # Card header: title + delete button (Tier 1 colour)
        header_row = QWidget()
        # Bare property — only this widget, NOT its children.
        header_row.setStyleSheet(
            "background:#fff4e8;"
            "border-top-left-radius:8px; border-top-right-radius:8px;"
            "border-bottom:1px solid #efd8b8;"
        )
        header_hl = QHBoxLayout(header_row)
        header_hl.setContentsMargins(10, 5, 6, 5)
        header_hl.setSpacing(4)
        card_title = QLabel(name)
        card_title.setStyleSheet(
            "color:#c97028; font-weight:700; font-size:11px;"
            "letter-spacing:0.5px; background:transparent; border:none;"
        )
        btn_del = QPushButton("×")
        btn_del.setFixedSize(18, 18)
        btn_del.setToolTip(f"Remove measurement '{name}'")
        btn_del.setStyleSheet(
            "QPushButton { background:#fff0eb; border:1px solid #efb6a0; border-radius:4px;"
            "  color:#b04030; font-weight:700; padding:0; font-size:13px; }"
            "QPushButton:hover { background:#f4d0c8; border-color:#d07060; }"
        )
        header_hl.addWidget(card_title)
        header_hl.addStretch()
        header_hl.addWidget(btn_del)
        outer_layout.addWidget(header_row)

        # Tier 1 params: always visible
        t1_widget = QWidget()
        # Bare property only — child QComboBox / QSpinBox keep their own styles.
        t1_widget.setStyleSheet("background:transparent;")
        t1_form = QFormLayout(t1_widget)
        t1_form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        t1_form.setContentsMargins(8, 6, 8, 4)
        t1_form.setSpacing(5)

        enabled = QCheckBox("Enabled"); enabled.setChecked(True)
        axis = QComboBox(); axis.addItems(["Y-CD", "X-CD"])
        _set_expanding(axis)

        min_val = QLabel("100"); min_val.setObjectName("thresholdValue"); min_val.setFixedWidth(34)
        max_val = QLabel("220"); max_val.setObjectName("thresholdValue"); max_val.setFixedWidth(34)
        gl_min = QSlider(Qt.Orientation.Horizontal); gl_min.setRange(0, 255); gl_min.setValue(100)
        gl_max = QSlider(Qt.Orientation.Horizontal); gl_max.setRange(0, 255); gl_max.setValue(220)

        min_row = QHBoxLayout(); min_row.setSpacing(4)
        min_row.addWidget(_lbl("Min")); min_row.addWidget(gl_min); min_row.addWidget(min_val)
        max_row = QHBoxLayout(); max_row.setSpacing(4)
        max_row.addWidget(_lbl("Max")); max_row.addWidget(gl_max); max_row.addWidget(max_val)
        min_wrap = QWidget(); min_wrap.setStyleSheet("background:transparent;"); min_wrap.setLayout(min_row)
        max_wrap = QWidget(); max_wrap.setStyleSheet("background:transparent;"); max_wrap.setLayout(max_row)

        min_area = QSpinBox(); min_area.setRange(1, 500_000); min_area.setValue(50); min_area.setSuffix(" px²"); _set_expanding(min_area)

        t1_form.addRow("Enable", enabled)
        t1_form.addRow("Axis", axis)
        t1_form.addRow("GL Min", min_wrap)
        t1_form.addRow("GL Max", max_wrap)
        t1_form.addRow("Min blob area", min_area)
        outer_layout.addWidget(t1_widget)

        # Tier 2: Filters (collapsed=False, visible but collapsible)
        sec_filters = CollapsibleSection("Filters", tier=2, collapsed=False,
                                         content_margins=(8, 4, 8, 6))
        sec_filters.setStyleSheet("background:transparent;")
        f2_form_w = QWidget(); f2_form_w.setStyleSheet("background:transparent;")
        f2_form = QFormLayout(f2_form_w)
        f2_form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        f2_form.setContentsMargins(0, 2, 0, 2)
        f2_form.setSpacing(4)

        min_ar  = QDoubleSpinBox(); min_ar.setRange(0.0, 100.0);  min_ar.setValue(0.0);  min_ar.setSingleStep(0.1);  min_ar.setSpecialValueText("off"); _set_expanding(min_ar)
        max_ar  = QDoubleSpinBox(); max_ar.setRange(0.0, 100.0);  max_ar.setValue(0.0);  max_ar.setSingleStep(0.1);  max_ar.setSpecialValueText("off"); _set_expanding(max_ar)
        min_w   = QSpinBox();        min_w.setRange(0, 9999);      min_w.setValue(0);     min_w.setSuffix(" px");     min_w.setSpecialValueText("off");  _set_expanding(min_w)
        max_w   = QSpinBox();        max_w.setRange(0, 9999);      max_w.setValue(0);     max_w.setSuffix(" px");     max_w.setSpecialValueText("off");  _set_expanding(max_w)
        min_h   = QSpinBox();        min_h.setRange(0, 9999);      min_h.setValue(0);     min_h.setSuffix(" px");     min_h.setSpecialValueText("off");  _set_expanding(min_h)

        f2_form.addRow("Min aspect (h/w)", min_ar)
        f2_form.addRow("Max aspect (h/w)", max_ar)
        f2_form.addRow("Min width", min_w)
        f2_form.addRow("Max width", max_w)
        f2_form.addRow("Min height", min_h)
        sec_filters.add_widget(f2_form_w)
        outer_layout.addWidget(sec_filters)

        # Tier 3: Advanced (collapsed by default)
        sec_adv = CollapsibleSection("Advanced", tier=3, collapsed=True,
                                      content_margins=(8, 4, 8, 6))
        sec_adv.setStyleSheet("background:transparent;")
        f3_form_w = QWidget(); f3_form_w.setStyleSheet("background:transparent;")
        f3_form = QFormLayout(f3_form_w)
        f3_form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        f3_form.setContentsMargins(0, 2, 0, 2)
        f3_form.setSpacing(4)

        vert_erode_k    = QSpinBox(); vert_erode_k.setRange(0, 99); vert_erode_k.setValue(0); vert_erode_k.setSuffix(" px"); vert_erode_k.setSpecialValueText("off")
        vert_erode_iter = QSpinBox(); vert_erode_iter.setRange(1, 10); vert_erode_iter.setValue(1)

        strip_enabled  = QCheckBox("Enable strip mask"); strip_enabled.setChecked(False)
        strip_auto     = QCheckBox("Auto-detect centers (X-proj)"); strip_auto.setChecked(False)
        xproj_smooth   = QSpinBox(); xproj_smooth.setRange(1, 51); xproj_smooth.setValue(5); xproj_smooth.setSuffix(" px")
        xproj_pitch    = QSpinBox(); xproj_pitch.setRange(1, 9999); xproj_pitch.setValue(30); xproj_pitch.setSuffix(" px")
        xproj_frac     = QDoubleSpinBox(); xproj_frac.setRange(0.01, 1.0); xproj_frac.setValue(0.3); xproj_frac.setSingleStep(0.05)
        strip_start_x  = QSpinBox(); strip_start_x.setRange(0, 9999); strip_start_x.setValue(0); strip_start_x.setSuffix(" px")
        strip_pitch    = QSpinBox(); strip_pitch.setRange(1, 9999); strip_pitch.setValue(44); strip_pitch.setSuffix(" px")
        strip_width    = QSpinBox(); strip_width.setRange(1, 9999); strip_width.setValue(22); strip_width.setSuffix(" px")
        strip_margin      = QSpinBox(); strip_margin.setRange(0, 999);  strip_margin.setValue(4);  strip_margin.setSuffix(" px")
        strip_edge_margin = QSpinBox(); strip_edge_margin.setRange(0, 999); strip_edge_margin.setValue(0); strip_edge_margin.setSuffix(" px"); strip_edge_margin.setSpecialValueText("off")
        strip_regularize  = QCheckBox("Regularize to grid"); strip_regularize.setChecked(False)
        strip_pitch_tol   = QSpinBox(); strip_pitch_tol.setRange(1, 99); strip_pitch_tol.setValue(5); strip_pitch_tol.setSuffix(" px")
        strip_normalize_x = QCheckBox("Normalize X bounds"); strip_normalize_x.setChecked(True)

        range_enabled  = QCheckBox("Enable range filter"); range_enabled.setChecked(False)
        min_line_px    = QDoubleSpinBox(); min_line_px.setRange(0, 9999); min_line_px.setValue(0); min_line_px.setSuffix(" px"); min_line_px.setSpecialValueText("off")
        max_line_px    = QDoubleSpinBox(); max_line_px.setRange(0, 9999); max_line_px.setValue(0); max_line_px.setSuffix(" px"); max_line_px.setSpecialValueText("off")

        def _on_strip_auto(checked: int) -> None:
            strip_start_x.setEnabled(not bool(checked))
            self._emit()
        strip_auto.stateChanged.connect(_on_strip_auto)

        f3_form.addRow("Vert erode", vert_erode_k)
        f3_form.addRow("Vert erode iter", vert_erode_iter)
        f3_form.addRow(strip_enabled)
        f3_form.addRow(strip_auto)
        f3_form.addRow("X-proj smooth", xproj_smooth)
        f3_form.addRow("X-proj min pitch", xproj_pitch)
        f3_form.addRow("X-proj min frac", xproj_frac)
        f3_form.addRow("Strip start X", strip_start_x)
        f3_form.addRow("Strip pitch", strip_pitch)
        f3_form.addRow("Strip width", strip_width)
        f3_form.addRow("Strip margin ±", strip_margin)
        f3_form.addRow("Edge margin", strip_edge_margin)
        f3_form.addRow(strip_regularize)
        f3_form.addRow("Pitch tolerance", strip_pitch_tol)
        f3_form.addRow(strip_normalize_x)
        f3_form.addRow(range_enabled)
        f3_form.addRow("Min line (px)", min_line_px)
        f3_form.addRow("Max line (px)", max_line_px)
        sec_adv.add_widget(f3_form_w)
        outer_layout.addWidget(sec_adv)

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
        for _w in (min_ar, max_ar, min_w, max_w, min_h, vert_erode_k, vert_erode_iter,
                   xproj_smooth, xproj_pitch, xproj_frac,
                   strip_start_x, strip_pitch, strip_width, strip_margin,
                   strip_edge_margin, strip_pitch_tol,
                   min_line_px, max_line_px):
            _w.valueChanged.connect(self._emit)
        strip_enabled.stateChanged.connect(self._emit)
        strip_regularize.stateChanged.connect(self._emit)
        strip_normalize_x.stateChanged.connect(self._emit)
        range_enabled.stateChanged.connect(self._emit)
        enabled.stateChanged.connect(self._emit)

        self._profiles_layout.addWidget(outer)
        profile_dict = {
            "name": name,
            "_widget": outer,
            "enabled": enabled,
            "axis": axis,
            "gl_min": gl_min,
            "gl_max": gl_max,
            "min_area": min_area,
            "min_aspect_ratio": min_ar,
            "max_aspect_ratio": max_ar,
            "min_width": min_w,
            "max_width": max_w,
            "min_height": min_h,
            "vert_erode_k": vert_erode_k,
            "vert_erode_iter": vert_erode_iter,
            "col_mask_enabled": strip_enabled,
            "col_mask_auto_centers": strip_auto,
            "xproj_smooth_k": xproj_smooth,
            "xproj_min_pitch_px": xproj_pitch,
            "xproj_peak_min_frac": xproj_frac,
            "col_mask_start_x": strip_start_x,
            "col_mask_pitch_px": strip_pitch,
            "col_mask_width_px": strip_width,
            "col_mask_margin_px": strip_margin,
            "col_mask_edge_margin_px": strip_edge_margin,
            "col_mask_regularize": strip_regularize,
            "col_mask_pitch_tol_px": strip_pitch_tol,
            "col_mask_normalize_x": strip_normalize_x,
            "range_enabled": range_enabled,
            "min_line_px": min_line_px,
            "max_line_px": max_line_px,
        }
        self._profiles.append(profile_dict)

        def _on_delete() -> None:
            self._profiles_layout.removeWidget(outer)
            outer.setParent(None)
            outer.deleteLater()
            if profile_dict in self._profiles:
                self._profiles.remove(profile_dict)
            self._emit()

        btn_del.clicked.connect(_on_delete)
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
                "max_width": p["max_width"].value(),
                "min_height": p["min_height"].value(),
                "vert_erode_k": p["vert_erode_k"].value(),
                "vert_erode_iter": p["vert_erode_iter"].value(),
                "col_mask_enabled": p["col_mask_enabled"].isChecked(),
                "col_mask_auto_centers": p["col_mask_auto_centers"].isChecked(),
                "xproj_smooth_k": p["xproj_smooth_k"].value(),
                "xproj_min_pitch_px": p["xproj_min_pitch_px"].value(),
                "xproj_peak_min_frac": p["xproj_peak_min_frac"].value(),
                "col_mask_start_x": p["col_mask_start_x"].value(),
                "col_mask_pitch_px": p["col_mask_pitch_px"].value(),
                "col_mask_width_px": p["col_mask_width_px"].value(),
                "col_mask_margin_px": p["col_mask_margin_px"].value(),
                "col_mask_edge_margin_px": p["col_mask_edge_margin_px"].value(),
                "col_mask_regularize": p["col_mask_regularize"].isChecked(),
                "col_mask_pitch_tol_px": p["col_mask_pitch_tol_px"].value(),
                "col_mask_normalize_x": p["col_mask_normalize_x"].isChecked(),
                "range_enabled": p["range_enabled"].isChecked(),
                "min_line_px": p["min_line_px"].value(),
                "max_line_px": p["max_line_px"].value(),
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
