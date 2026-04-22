"""Measure workspace — single-image analysis using recipes or legacy cards."""
from __future__ import annotations

import os
from pathlib import Path

import cv2
import numpy as np
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QGroupBox, QFormLayout, QComboBox, QPushButton,
    QLabel, QCheckBox, QButtonGroup, QFrame, QMessageBox,
    QSizePolicy, QDoubleSpinBox, QSpinBox,
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, pyqtSlot

from ..control_panel import ControlPanel
from ..image_viewer import ImageViewer
from ..results_panel import ResultsPanel
from ..layer_control_panel import LayerControlPanel
from ...core.models import ImageRecord
from ...core.recipe_base import PipelineResult
from ...core.recipe_registry import RecipeRegistry
from ...core.measurement_engine import MeasurementEngine
from ...core.calibration import CalibrationManager
from ...core.annotator import OverlayOptions, draw_overlays, draw_overlays_multi
from ..._compat import records_to_legacy_cuts


class MeasureWorkspace(QWidget):
    run_completed  = pyqtSignal(object)   # PipelineResult
    recipe_saved   = pyqtSignal(object)   # MeasurementRecipe descriptor
    status_message = pyqtSignal(str)

    def __init__(
        self,
        engine: MeasurementEngine,
        registry: RecipeRegistry,
        cal_manager: CalibrationManager,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self._engine     = engine
        self._registry   = registry
        self._cal_manager = cal_manager

        self._current_ir:    ImageRecord | None = None
        self._current_raw    = None
        self._current_mask   = None
        self._current_cuts:  list = []
        self._current_records: list = []
        self._current_annotated = None
        self._profile_masks: list = []
        self._per_layer_cuts: list = []   # [(cuts, color_bgr)] per config
        self._focused_measurement: tuple[int, int] | None = None
        self._last_result: PipelineResult | None = None

        self._preview_timer = QTimer()
        self._preview_timer.setSingleShot(True)
        self._preview_timer.timeout.connect(self._run_preview)

        self._build_ui()

    # ── Construction ──────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)

        # Center: viewer header + viewer + results
        center = QWidget()
        cv = QVBoxLayout(center)
        cv.setContentsMargins(0, 0, 0, 0)
        cv.setSpacing(0)
        cv.addWidget(self._build_viewer_header())

        v_split = QSplitter(Qt.Orientation.Vertical)
        v_split.setChildrenCollapsible(False)

        self._viewer = ImageViewer()
        v_split.addWidget(self._viewer)

        self._results = ResultsPanel()
        self._results.setMinimumHeight(100)
        v_split.addWidget(self._results)
        v_split.setSizes([550, 200])
        v_split.setStretchFactor(0, 1)
        v_split.setStretchFactor(1, 0)

        cv.addWidget(v_split, stretch=1)
        splitter.addWidget(center)

        # Right: recipe selector + layer panel + legacy ControlPanel
        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(4, 4, 4, 4)
        rv.setSpacing(6)
        rv.addWidget(self._build_recipe_selector())

        rv.addWidget(self._build_edge_locator_panel())

        self._layer_panel = LayerControlPanel()
        self._layer_panel.setVisible(False)
        self._layer_panel.layers_changed.connect(self._refresh_annotated)
        rv.addWidget(self._layer_panel)

        self._ctrl = ControlPanel()
        self._ctrl.setMinimumWidth(230)
        self._ctrl.setMaximumWidth(320)
        self._ctrl.params_changed.connect(self._on_params_changed)
        self._ctrl.run_single.connect(self._run_single)
        rv.addWidget(self._ctrl, stretch=1)

        splitter.addWidget(right)
        splitter.setSizes([1000, 270])
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 0)

        root.addWidget(splitter)

        self._results.row_selected.connect(self._on_result_selected)
        self._results.state_filter_changed.connect(self._on_state_filter_changed)
        self._viewer.measure_updated.connect(lambda t: self.status_message.emit(t))

    def _build_viewer_header(self) -> QFrame:
        header = QFrame()
        header.setObjectName("viewerHeader")
        hbox = QHBoxLayout(header)
        hbox.setContentsMargins(10, 0, 12, 0)
        hbox.setSpacing(0)

        self._btn_raw  = QPushButton("Raw");       self._btn_raw.setObjectName("segLeft")
        self._btn_mask = QPushButton("Mask");      self._btn_mask.setObjectName("segMid")
        self._btn_ann  = QPushButton("Annotated"); self._btn_ann.setObjectName("segRight")
        for btn in (self._btn_raw, self._btn_mask, self._btn_ann):
            btn.setCheckable(True)
            btn.setFixedHeight(26)
        self._btn_raw.setChecked(True)

        grp = QButtonGroup(self)
        grp.setExclusive(True)
        for btn in (self._btn_raw, self._btn_mask, self._btn_ann):
            grp.addButton(btn)

        hbox.addWidget(self._btn_raw)
        hbox.addWidget(self._btn_mask)
        hbox.addWidget(self._btn_ann)

        self._btn_ruler = QPushButton("📏 Ruler")
        self._btn_ruler.setCheckable(True)
        self._btn_ruler.setFixedHeight(26)
        self._btn_ruler.setToolTip("Toggle ruler (or Shift+Click on image)")
        self._btn_ruler.toggled.connect(lambda on: self._viewer.set_ruler_mode(on))
        hbox.addWidget(self._btn_ruler)

        sep = QLabel("  |  ")
        sep.setStyleSheet("color:#d8cbb8;")
        hbox.addWidget(sep)

        self._overlay_widget = QWidget()
        self._overlay_widget.setVisible(False)
        ov = QHBoxLayout(self._overlay_widget)
        ov.setContentsMargins(0, 0, 0, 0)
        ov.setSpacing(12)

        self._chk_lines  = _ov_chk("Lines",  True)
        self._chk_labels = _ov_chk("Values", True)
        self._chk_boxes  = _ov_chk("Boxes",  False)
        self._chk_legend = _ov_chk("Legend", True)
        for chk in (self._chk_lines, self._chk_labels, self._chk_boxes, self._chk_legend):
            chk.stateChanged.connect(self._refresh_annotated)
            ov.addWidget(chk)

        sep_detail = QLabel("  |  ")
        sep_detail.setStyleSheet("color:#d8cbb8;")
        ov.addWidget(sep_detail)
        self._btn_detail_cd = QPushButton("Detail CD")
        self._btn_detail_cd.setCheckable(True)
        self._btn_detail_cd.setFixedHeight(22)
        self._btn_detail_cd.setToolTip("Show individual per-sample CD lines instead of single aggregate line")
        self._btn_detail_cd.toggled.connect(self._refresh_annotated)
        ov.addWidget(self._btn_detail_cd)

        hbox.addWidget(self._overlay_widget)
        hbox.addStretch()

        self._btn_raw.clicked.connect(self._on_mode_raw)
        self._btn_mask.clicked.connect(self._on_mode_mask)
        self._btn_ann.clicked.connect(self._on_mode_ann)

        return header

    def _build_recipe_selector(self) -> QGroupBox:
        box = QGroupBox("Recipe (optional)")
        form = QFormLayout(box)

        self._recipe_combo = QComboBox()
        self._recipe_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        form.addRow("Recipe:", self._recipe_combo)

        run_btn = QPushButton("Run Single (F5)")
        run_btn.setShortcut("F5")
        run_btn.clicked.connect(self._run_single)

        save_btn = QPushButton("Save Cards as Recipe…")
        save_btn.setToolTip("Convert current ControlPanel profiles to Recipe(s) and save")
        save_btn.clicked.connect(self._save_cards_as_recipe)

        self._btn_compare = QPushButton("Compare to Reference…")
        self._btn_compare.setToolTip("Compare each measured position against a Reference CD value")
        self._btn_compare.setEnabled(False)
        self._btn_compare.clicked.connect(self._open_compare_dialog)

        btn_row = QHBoxLayout()
        btn_row.addWidget(run_btn)
        btn_row.addWidget(save_btn)
        form.addRow(btn_row)
        form.addRow(self._btn_compare)

        self._refresh_recipe_selector_internal()
        self._recipe_combo.currentIndexChanged.connect(self._on_recipe_combo_changed)
        return box

    def _build_edge_locator_panel(self) -> QGroupBox:
        """Controls that mirror Recipe workspace's Analysis tab edge-locator section."""
        box = QGroupBox("Edge Locator")
        form = QFormLayout(box)
        form.setSpacing(6)
        form.setContentsMargins(8, 6, 8, 6)

        self._ec_method = QComboBox()
        self._ec_method.addItem("Threshold Crossing", "threshold_crossing")
        self._ec_method.addItem("Gradient",           "gradient")
        self._ec_method.addItem("BBox",               "bbox")

        self._ec_threshold_frac = QDoubleSpinBox()
        self._ec_threshold_frac.setRange(0.01, 0.99); self._ec_threshold_frac.setSingleStep(0.05)
        self._ec_threshold_frac.setValue(0.5); self._ec_threshold_frac.setDecimals(2)

        # Sampling strategy
        self._ec_sample_mode_combo = QComboBox()
        self._ec_sample_mode_combo.addItem("All columns", "all")
        self._ec_sample_mode_combo.addItem("N evenly spaced", "n")
        self._ec_sample_n = QSpinBox(); self._ec_sample_n.setRange(1, 200); self._ec_sample_n.setValue(10)
        self._ec_sample_n.setEnabled(False)
        self._ec_sample_mode_combo.currentIndexChanged.connect(
            lambda: self._ec_sample_n.setEnabled(
                self._ec_sample_mode_combo.currentData() == "n"))
        self._ec_aggregate_combo = QComboBox()
        for _lbl, _key in (("Median","median"),("Mean","mean"),("Min","min"),("Max","max")):
            self._ec_aggregate_combo.addItem(_lbl, _key)

        # Profile Gaussian LPF
        self._ec_lpf_cb = QCheckBox("Gaussian LPF")
        self._ec_lpf_sigma = QDoubleSpinBox()
        self._ec_lpf_sigma.setRange(0.1, 10.0); self._ec_lpf_sigma.setSingleStep(0.1)
        self._ec_lpf_sigma.setValue(1.0); self._ec_lpf_sigma.setDecimals(1)
        self._ec_lpf_sigma.setSuffix(" px"); self._ec_lpf_sigma.setEnabled(False)
        self._ec_lpf_cb.toggled.connect(self._ec_lpf_sigma.setEnabled)

        self._ec_overlap = QDoubleSpinBox()
        self._ec_overlap.setRange(0.0, 1.0); self._ec_overlap.setSingleStep(0.05)
        self._ec_overlap.setValue(0.5); self._ec_overlap.setDecimals(2)

        self._ec_cluster_tol = QSpinBox()
        self._ec_cluster_tol.setRange(1, 200); self._ec_cluster_tol.setValue(10)
        self._ec_cluster_tol.setSuffix(" px")

        self._ec_border = QSpinBox()
        self._ec_border.setRange(0, 200); self._ec_border.setValue(0)
        self._ec_border.setSuffix(" px"); self._ec_border.setSpecialValueText("off")

        form.addRow("Y-CD method:", self._ec_method)

        # Advanced parameters widget (hidden for BBox)
        self._ec_adv_widget = QWidget()
        adv_form = QFormLayout(self._ec_adv_widget)
        adv_form.setSpacing(5); adv_form.setContentsMargins(0, 0, 0, 0)
        # TC-specific
        self._ec_tc_widget = QWidget()
        tc_form = QFormLayout(self._ec_tc_widget)
        tc_form.setSpacing(5); tc_form.setContentsMargins(0, 0, 0, 0)
        tc_form.addRow("Threshold level:", self._ec_threshold_frac)
        adv_form.addRow(self._ec_tc_widget)
        # Sampling
        samp_row = QWidget()
        samp_hl = QHBoxLayout(samp_row); samp_hl.setContentsMargins(0,0,0,0); samp_hl.setSpacing(4)
        samp_hl.addWidget(self._ec_sample_mode_combo); samp_hl.addWidget(self._ec_sample_n)
        adv_form.addRow("Vertical lines:", samp_row)
        adv_form.addRow("Aggregation:", self._ec_aggregate_combo)
        # Profile Filter section
        ec_lpf_sep = QLabel("─── Profile Filter ───")
        ec_lpf_sep.setStyleSheet("color:#666; font-size:11px;")
        adv_form.addRow(ec_lpf_sep)
        ec_lpf_row = QWidget()
        ec_lpf_hl = QHBoxLayout(ec_lpf_row); ec_lpf_hl.setContentsMargins(0, 0, 0, 0); ec_lpf_hl.setSpacing(6)
        ec_lpf_hl.addWidget(self._ec_lpf_cb); ec_lpf_hl.addWidget(self._ec_lpf_sigma)
        adv_form.addRow("Profile LPF:", ec_lpf_row)
        form.addRow(self._ec_adv_widget)

        form.addRow("X overlap:",        self._ec_overlap)
        form.addRow("Cluster tol:",      self._ec_cluster_tol)
        form.addRow("Border exclusion:", self._ec_border)

        self._ec_method.currentIndexChanged.connect(self._on_ec_method_changed)
        self._on_ec_method_changed()  # set initial state
        return box

    def _on_ec_method_changed(self) -> None:
        method = self._ec_method.currentData()
        self._ec_adv_widget.setVisible(method != "bbox")
        self._ec_tc_widget.setVisible(method == "threshold_crossing")

    def _on_recipe_combo_changed(self) -> None:
        """When a recipe is selected, populate edge-locator panel from its saved values."""
        rid = self._selected_recipe_id()
        if rid is None:
            return
        desc = self._registry.get_descriptor(rid)
        if desc is None:
            return
        ec = desc.edge_locator_config
        _method = str(ec.get("ycd_edge_method", "threshold_crossing")).lower()
        if _method == "subpixel":
            _method = "gradient"  # backward compat for old recipes
        idx = self._ec_method.findData(_method)
        self._ec_method.setCurrentIndex(idx if idx >= 0 else 0)
        self._ec_threshold_frac.setValue(float(ec.get("threshold_frac", 0.5)))
        _slm = ec.get("sample_lines_mode", "all")
        if isinstance(_slm, int) or (isinstance(_slm, str) and _slm != "all"):
            try:
                self._ec_sample_n.setValue(int(_slm))
                self._ec_sample_mode_combo.setCurrentIndex(
                    self._ec_sample_mode_combo.findData("n"))
            except (ValueError, TypeError):
                self._ec_sample_mode_combo.setCurrentIndex(
                    self._ec_sample_mode_combo.findData("all"))
        else:
            self._ec_sample_mode_combo.setCurrentIndex(
                self._ec_sample_mode_combo.findData("all"))
        _agg = str(ec.get("aggregate_method", "median")).lower()
        _agg_idx = self._ec_aggregate_combo.findData(_agg)
        self._ec_aggregate_combo.setCurrentIndex(_agg_idx if _agg_idx >= 0 else 0)
        self._ec_lpf_cb.setChecked(bool(ec.get("profile_lpf_enabled", False)))
        self._ec_lpf_sigma.setValue(float(ec.get("profile_lpf_sigma", 1.0)))
        self._ec_overlap.setValue(float(ec.get("x_overlap_ratio", 0.5)))
        self._ec_cluster_tol.setValue(int(ec.get("y_cluster_tol", 10)))
        self._ec_border.setValue(int(ec.get("border_margin_px", 0)))

    # ── Public API ────────────────────────────────────────────────────────────

    def set_image_record(self, ir: ImageRecord) -> None:
        self._current_ir = ir
        self._current_cuts = []
        self._current_records = []
        self._current_annotated = None
        self._focused_measurement = None
        self._btn_compare.setEnabled(False)

        try:
            from ...core.image_loader import load_grayscale
            raw = load_grayscale(ir.file_path)
            self._current_raw = raw
            self._viewer.set_nm_per_pixel(ir.pixel_size_nm)
            self._viewer.set_images(raw, None, None)
            self._viewer.set_mode("raw")
            self._results.clear()
        except Exception as exc:
            self.status_message.emit(f"Load error: {exc}")
            return

        self.status_message.emit(f"Loaded: {Path(ir.file_path).name}")
        self._schedule_preview()

    def refresh_recipe_selector(self, _recipe=None) -> None:
        self._refresh_recipe_selector_internal()

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _refresh_recipe_selector_internal(self) -> None:
        self._recipe_combo.blockSignals(True)
        self._recipe_combo.clear()
        self._recipe_combo.addItem("— Use legacy cards (ControlPanel) —", None)
        for desc in self._registry.list_recipes():
            struct = desc.structure_name or "?"
            tag = f"{struct} {desc.axis_mode}-CD"
            self._recipe_combo.addItem(f"{desc.recipe_name}  [{tag}]", desc.recipe_id)
        self._recipe_combo.blockSignals(False)

    def _selected_recipe_id(self) -> str | None:
        idx = self._recipe_combo.currentIndex()
        return self._recipe_combo.itemData(idx)

    def _get_overlay_opts(self) -> OverlayOptions:
        return OverlayOptions(
            show_lines=self._chk_lines.isChecked(),
            show_labels=self._chk_labels.isChecked(),
            show_boxes=self._chk_boxes.isChecked(),
            show_legend=self._chk_legend.isChecked(),
            show_detail=self._btn_detail_cd.isChecked(),
            focus=self._focused_measurement,
        )

    def _schedule_preview(self) -> None:
        self._preview_timer.start(180)

    def _run_preview(self) -> None:
        if self._current_raw is None:
            return
        try:
            _, _, profile_masks = self._analyze_with_cards(self._current_raw, preview_only=True)
        except Exception:
            return
        self._profile_masks = profile_masks
        self._viewer.set_images(self._current_raw, self._current_mask, self._current_annotated,
                                profile_masks=profile_masks)

    # ── Save cards as recipe ──────────────────────────────────────────────────

    def _save_cards_as_recipe(self) -> None:
        cards = self._ctrl.get_measurement_cards()
        if not cards:
            QMessageBox.information(self, "No profiles", "Add at least one measurement profile first.")
            return
        saved_names = []
        saved_descs = []
        for card in cards:
            try:
                desc = self._registry.import_from_card(card)
                saved_names.append(desc.recipe_name)
                saved_descs.append(desc)
            except Exception as exc:
                QMessageBox.warning(self, "Save failed", f"Card '{card.get('name','')}': {exc}")
        if saved_names:
            self._refresh_recipe_selector_internal()
            self.status_message.emit(f"Saved recipe(s): {', '.join(saved_names)}")
            for desc in saved_descs:
                self.recipe_saved.emit(desc)

    # ── Run logic ─────────────────────────────────────────────────────────────

    @pyqtSlot()
    def _run_single(self) -> None:
        if self._current_raw is None or self._current_ir is None:
            QMessageBox.information(self, "No image", "Select an image first.")
            return

        rid = self._selected_recipe_id()
        if rid is not None:
            self._run_with_recipe(rid)
        else:
            self._run_with_cards()

    def _run_with_recipe(self, recipe_id: str) -> None:
        recipe = self._registry.get(recipe_id)
        if recipe is None:
            QMessageBox.warning(self, "Recipe error", "Could not load recipe.")
            return

        # Apply edge-locator overrides from the panel (temporary — does not save)
        import dataclasses
        from ...core.recipe_base import RecipeConfig
        from ...core.recipes.cmg_recipe import CMGRecipe as _CMGRecipe
        _existing_ec = recipe.recipe_descriptor.edge_locator_config.to_dict()
        _patched_desc = dataclasses.replace(
            recipe.recipe_descriptor,
            edge_locator_config=RecipeConfig(data={
                **_existing_ec,
                "ycd_edge_method":   self._ec_method.currentData(),
                "threshold_frac":    self._ec_threshold_frac.value(),
                "sample_lines_mode": (self._ec_sample_n.value()
                                      if self._ec_sample_mode_combo.currentData() == "n"
                                      else "all"),
                "aggregate_method":  self._ec_aggregate_combo.currentData(),
                "profile_lpf_enabled": self._ec_lpf_cb.isChecked(),
                "profile_lpf_sigma":   self._ec_lpf_sigma.value(),
                "x_overlap_ratio":   self._ec_overlap.value(),
                "y_cluster_tol":     self._ec_cluster_tol.value(),
                "border_margin_px":  self._ec_border.value(),
            }),
        )
        recipe = _CMGRecipe(descriptor=_patched_desc)

        # Sync nm/pixel from ControlPanel to ImageRecord
        self._current_ir.pixel_size_nm = self._ctrl.get_nm_per_pixel()
        result = self._engine.run_single(self._current_ir, recipe)

        if result.error:
            self.status_message.emit(f"Error: {result.error}")
            self._results.show_fail(Path(self._current_ir.file_path).name, result.error)
            return

        self._current_raw  = result.raw
        self._current_mask = result.mask
        self._current_annotated = result.annotated
        self._current_records  = result.records
        self._current_cuts = records_to_legacy_cuts(result.records)
        self._last_result  = result
        self._focused_measurement = None

        name = Path(self._current_ir.file_path).name
        desc = self._registry.get_descriptor(recipe_id)
        recipe_name = desc.recipe_name if desc else "Recipe"

        # Populate layer panel with single recipe layer
        self._per_layer_cuts = []
        self._layer_panel.set_layers([recipe_name], [self._current_cuts])
        self._layer_panel.setVisible(bool(self._current_cuts))

        self._viewer.set_images(result.raw, result.mask, result.annotated)
        if self._current_cuts:
            self._results.show_results(name, self._current_cuts)
            self._btn_ann.setChecked(True)
            self._overlay_widget.setVisible(True)
            self._viewer.set_mode("annotated")
        else:
            self._results.show_fail(name, "No cuts detected")

        n = len(result.records)
        self._btn_compare.setEnabled(bool(self._current_records))
        self.status_message.emit(f"{name}  ·  {n} measurement(s) via recipe")
        self.run_completed.emit(result)

    def _run_with_cards(self) -> None:
        if self._current_raw is None:
            return
        if not self._ctrl.get_measurement_cards():
            QMessageBox.information(self, "No measurements", "Add a measurement profile first.")
            return
        try:
            mask, cuts, profile_masks = self._analyze_with_cards(self._current_raw, preview_only=False)
        except Exception as exc:
            QMessageBox.critical(self, "Processing error", str(exc))
            return

        self._current_mask  = mask
        self._current_cuts  = cuts
        self._profile_masks = profile_masks
        self._focused_measurement = None

        # Build per-layer cuts (one per card) for layer panel
        cards = self._ctrl.get_measurement_cards()
        layer_names: list[str] = []
        layer_cuts: list[list] = []
        from ..._compat import records_to_legacy_cuts as _rtlc  # noqa: F401
        from ...core.cmg_analyzer import CMGCut as _CMGCut
        card_states = [card.get("name", f"Measure {i+1}") for i, card in enumerate(cards)]
        for sn in card_states:
            card_cuts = []
            for c in cuts:
                ms = [m for m in c.measurements if getattr(m, "state_name", "") == sn]
                if ms:
                    card_cuts.append(_CMGCut(cmg_id=c.cmg_id, measurements=ms))
            layer_names.append(sn)
            layer_cuts.append(card_cuts)
        self._layer_panel.set_layers(layer_names, layer_cuts)
        self._layer_panel.setVisible(bool(cuts))

        annotated = self._render_layered_annotated() if cuts else None
        self._current_annotated = annotated
        self._viewer.set_images(self._current_raw, mask, annotated, profile_masks=profile_masks)

        name = Path(self._current_ir.file_path).name if self._current_ir else "image"
        if cuts:
            self._results.show_results(name, cuts)
            self._btn_ann.setChecked(True)
            self._overlay_widget.setVisible(True)
            self._viewer.set_mode("annotated")
        else:
            self._results.show_fail(name, "No structures detected")

        n_meas = sum(len(c.measurements) for c in cuts)
        self.status_message.emit(f"{name}  ·  {len(cuts)} cut(s)  ·  {n_meas} measurement(s)")

    def _analyze_with_cards(self, raw: np.ndarray, preview_only: bool) -> tuple:
        from ...core.preprocessor import preprocess, PreprocessParams, apply_column_strip_mask
        from ...core.mg_detector import detect_blobs, detect_mg_column_centers_pitch_phase, regularize_blobs_to_columns
        from ...core.cmg_analyzer import analyze
        from ...core.recipes.cmg_recipe import _rot_blob_to_ori, apply_yedge_subpixel_to_cuts

        cards = self._ctrl.get_measurement_cards()
        base_params = self._ctrl.get_preprocess_params()
        min_area_default = self._ctrl.get_min_area()
        nm_px = self._ctrl.get_nm_per_pixel()

        # Edge-locator panel values (shared with recipe mode)
        _ec_method          = self._ec_method.currentData()
        _ec_threshold_frac  = self._ec_threshold_frac.value()
        _ec_overlap         = self._ec_overlap.value()
        _ec_cluster_tol     = self._ec_cluster_tol.value()

        full_mask = np.zeros_like(raw, dtype=np.uint8)
        cuts_all: list = []
        profile_masks: list = []
        cmg_offset = 0
        palette = [(255, 170, 70), (110, 180, 250), (120, 210, 160), (220, 130, 220)]

        for ci, card in enumerate(cards):
            axis = card.get("axis", "Y")
            roi = raw if axis == "Y" else cv2.rotate(raw, cv2.ROTATE_90_CLOCKWISE)

            # Strategy 2b: vertical erosion
            params = PreprocessParams(
                gl_min=card["gl_min"],
                gl_max=card["gl_max"],
                gauss_kernel=base_params.gauss_kernel,
                morph_open_k=base_params.morph_open_k,
                morph_close_k=base_params.morph_close_k,
                use_clahe=base_params.use_clahe,
                clahe_clip=base_params.clahe_clip,
                clahe_grid=base_params.clahe_grid,
                vert_erode_k=int(card.get("vert_erode_k", 0)),
                vert_erode_iter=int(card.get("vert_erode_iter", 1)),
            )
            mask_local = preprocess(roi, params)

            # Strategy 1+2a: column strip masking (severs EPI lateral bridge)
            col_centers: list[int] = []
            edge_margin = int(card.get("col_mask_edge_margin_px", 0))
            half_w = int(card.get("col_mask_width_px", 22)) // 2
            margin = int(card.get("col_mask_margin_px", 4))
            if card.get("col_mask_enabled", False):
                if card.get("col_mask_auto_centers", False):
                    col_centers = detect_mg_column_centers_pitch_phase(
                        mask_local,
                        pitch_px=int(card.get("col_mask_pitch_px", 44)),
                        smooth_k=int(card.get("xproj_smooth_k", 5)),
                        min_height_frac=float(card.get("xproj_peak_min_frac", 0.3)),
                        edge_margin_px=edge_margin,
                    )
                if not col_centers:  # fallback to manual
                    start_x = int(card.get("col_mask_start_x", 0))
                    pitch = int(card.get("col_mask_pitch_px", 44))
                    cw = mask_local.shape[1]
                    if pitch > 0 and start_x < cw:
                        col_centers = list(range(start_x, cw, pitch))
                mask_local = apply_column_strip_mask(mask_local, col_centers, half_w, margin, edge_margin)

            mask_ori = mask_local if axis == "Y" else cv2.rotate(mask_local, cv2.ROTATE_90_COUNTERCLOCKWISE)
            full_mask = np.maximum(full_mask, mask_ori)
            profile_masks.append((mask_ori, palette[ci % len(palette)], card.get("name", f"S{ci+1}")))
            if preview_only:
                continue

            blobs = detect_blobs(mask_local, min_area=card.get("min_area", min_area_default))

            # Geometric filters (0 = disabled)
            _min_ar = float(card.get("min_aspect_ratio", 0.0))
            _max_ar = float(card.get("max_aspect_ratio", 0.0))
            _min_w  = int(card.get("min_width", 0))
            _max_w  = int(card.get("max_width", 0))
            _min_h  = int(card.get("min_height", 0))
            if any([_min_ar, _max_ar, _min_w, _max_w, _min_h]):
                filtered = []
                for b in blobs:
                    ar = b.height / max(b.width, 1)
                    if _min_ar and ar < _min_ar: continue
                    if _max_ar and ar > _max_ar: continue
                    if _min_w and b.width < _min_w: continue
                    if _max_w and b.width > _max_w: continue
                    if _min_h and b.height < _min_h: continue
                    filtered.append(b)
                blobs = filtered

            # Border blob exclusion
            _border_px = int(card.get("border_margin_px", self._ec_border.value()))
            if _border_px > 0:
                _bh, _bw = mask_local.shape[:2]
                blobs = [b for b in blobs
                         if b.x0 >= _border_px and b.y0 >= _border_px
                         and b.x1 <= _bw - _border_px and b.y1 <= _bh - _border_px]

            # Pitch Grid Regularization: snap blobs onto layout grid, normalize X bounds
            if card.get("col_mask_enabled", False) and card.get("col_mask_regularize", False) and col_centers:
                half_w = int(card.get("col_mask_width_px", 22)) // 2
                tol    = int(card.get("col_mask_pitch_tol_px", 5))
                norm_x = bool(card.get("col_mask_normalize_x", True))
                blobs  = regularize_blobs_to_columns(blobs, col_centers, half_w, tol, norm_x)

            # Analyze in rotated space; back-rotate blob coords after (same fix as CMGRecipe)
            cuts = analyze(blobs, nm_px,
                           x_overlap_ratio=_ec_overlap,
                           y_cluster_tol=_ec_cluster_tol)
            if axis == "X":
                orig_h = raw.shape[0]
                for c in cuts:
                    for m in c.measurements:
                        m.upper_blob = _rot_blob_to_ori(m.upper_blob, orig_h)
                        m.lower_blob = _rot_blob_to_ori(m.lower_blob, orig_h)

            # Apply Y-edge refinement for gradient or threshold_crossing methods
            if axis == "Y" and _ec_method in ("gradient", "threshold_crossing"):
                _slm = (self._ec_sample_n.value()
                        if self._ec_sample_mode_combo.currentData() == "n"
                        else "all")
                apply_yedge_subpixel_to_cuts(
                    cuts, roi, nm_px,
                    method=_ec_method,
                    threshold_frac=_ec_threshold_frac,
                    col_centers=col_centers,
                    store_meta=False,  # legacy-cuts path doesn't use MeasurementRecord
                    sample_lines_mode=_slm,
                    aggregate_method=self._ec_aggregate_combo.currentData(),
                    profile_lpf_enabled=self._ec_lpf_cb.isChecked(),
                    profile_lpf_sigma=self._ec_lpf_sigma.value(),
                )

            # Range filter: discard measurements outside [min_line_px, max_line_px]
            if card.get("range_enabled", False):
                cuts = _filter_by_range(
                    cuts,
                    float(card.get("min_line_px", 0)),
                    float(card.get("max_line_px", 0)),
                )

            for c in cuts:
                c.cmg_id += cmg_offset
                for m in c.measurements:
                    m.cmg_id = c.cmg_id
                    m.axis = axis
                    m.state_name = card.get("name", f"Measure {ci+1}")
                    m.structure_name = card.get("structure_name", "")
            cmg_offset += len(cuts)
            cuts_all.extend(cuts)

        return full_mask, cuts_all, profile_masks

    def _render_layered_annotated(self) -> np.ndarray:
        """Render annotations with per-layer colors from the layer panel."""
        if self._current_raw is None:
            return None
        configs = self._layer_panel.get_configs()
        opts = self._get_overlay_opts()
        if not configs:
            return draw_overlays(self._current_raw, self._current_mask, self._current_cuts, opts)
        layers = [(cfg.cuts, cfg.color_bgr) for cfg in configs if cfg.show_annot]
        if not layers:
            return cv2.cvtColor(self._current_raw, cv2.COLOR_GRAY2BGR)
        return draw_overlays_multi(self._current_raw, layers, opts)

    def _refresh_annotated(self) -> None:
        if self._current_raw is None or not self._current_cuts:
            return
        annotated = self._render_layered_annotated()
        self._current_annotated = annotated
        self._viewer.set_images(self._current_raw, self._current_mask, annotated,
                                profile_masks=self._profile_masks)

    def _open_compare_dialog(self) -> None:
        from ..measure_validate_dialog import MeasureValidateDialog
        dlg = MeasureValidateDialog(records=self._current_records, parent=self)
        dlg.exec()

    # ── Mode / selection handlers ─────────────────────────────────────────────

    def _on_mode_raw(self)  -> None: self._overlay_widget.setVisible(False); self._viewer.set_mode("raw")
    def _on_mode_mask(self) -> None: self._overlay_widget.setVisible(False); self._viewer.set_mode("mask")
    def _on_mode_ann(self)  -> None: self._overlay_widget.setVisible(True);  self._viewer.set_mode("annotated")

    def _on_params_changed(self, _nm: float, _p) -> None:
        self._viewer.set_nm_per_pixel(self._ctrl.get_nm_per_pixel())
        self._schedule_preview()

    @pyqtSlot(int, int)
    def _on_result_selected(self, cmg_id: int, col_id: int) -> None:
        self._focused_measurement = (cmg_id, col_id)
        self._btn_ann.setChecked(True)
        self._overlay_widget.setVisible(True)
        self._viewer.set_mode("annotated")
        self._refresh_annotated()

    @pyqtSlot(str)
    def _on_state_filter_changed(self, state_name: str) -> None:
        self._viewer.set_mask_state_filter(state_name)
        if self._current_cuts:
            filtered = self._filtered_cuts_by_state(self._current_cuts, state_name)
            if self._current_raw is not None and self._current_mask is not None:
                annotated = draw_overlays(self._current_raw, self._current_mask,
                                          filtered, self._get_overlay_opts())
                self._current_annotated = annotated
                self._viewer.set_images(self._current_raw, self._current_mask, annotated,
                                        profile_masks=self._profile_masks)

    @staticmethod
    def _filtered_cuts_by_state(cuts: list, state_name: str) -> list:
        if not state_name:
            return cuts
        result = []
        for cut in cuts:
            keep = [m for m in cut.measurements if getattr(m, "state_name", "") == state_name]
            if keep:
                from ...core.cmg_analyzer import CMGCut
                result.append(CMGCut(cmg_id=cut.cmg_id, measurements=keep))
        return result


def _filter_by_range(cuts: list, min_px: float, max_px: float) -> list:
    """Remove measurements outside [min_px, max_px] and re-flag global MIN/MAX."""
    from ...core.cmg_analyzer import CMGCut, _flag_global_minmax
    filtered = []
    for cut in cuts:
        kept = [m for m in cut.measurements
                if (min_px <= 0 or m.cd_px >= min_px)
                and (max_px <= 0 or m.cd_px <= max_px)]
        if kept:
            filtered.append(CMGCut(cmg_id=cut.cmg_id, measurements=kept))
    _flag_global_minmax([m for cut in filtered for m in cut.measurements])
    return filtered


def _ov_chk(text: str, checked: bool = True) -> QCheckBox:
    chk = QCheckBox(text)
    chk.setChecked(checked)
    chk.setStyleSheet(
        "QCheckBox { color:#8c7a66; font-size:11px; spacing:4px; }"
        "QCheckBox::indicator { width:12px; height:12px; }"
    )
    return chk
