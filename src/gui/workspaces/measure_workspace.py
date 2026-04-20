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
    QSizePolicy,
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
        form.addRow(run_btn)

        self._refresh_recipe_selector_internal()
        return box

    # ── Public API ────────────────────────────────────────────────────────────

    def set_image_record(self, ir: ImageRecord) -> None:
        self._current_ir = ir
        self._current_cuts = []
        self._current_records = []
        self._current_annotated = None
        self._focused_measurement = None

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
        from ...core.mg_detector import detect_blobs, detect_mg_column_centers, regularize_blobs_to_columns
        from ...core.cmg_analyzer import analyze
        from ...core.recipes.cmg_recipe import _rot_blob_to_ori

        cards = self._ctrl.get_measurement_cards()
        base_params = self._ctrl.get_preprocess_params()
        min_area_default = self._ctrl.get_min_area()
        nm_px = self._ctrl.get_nm_per_pixel()

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
            if card.get("col_mask_enabled", False):
                if card.get("col_mask_auto_centers", False):
                    col_centers = detect_mg_column_centers(
                        mask_local,
                        smooth_k=int(card.get("xproj_smooth_k", 5)),
                        min_pitch_px=int(card.get("xproj_min_pitch_px", 30)),
                        min_height_frac=float(card.get("xproj_peak_min_frac", 0.3)),
                    )
                if not col_centers:  # fallback to manual
                    start_x = int(card.get("col_mask_start_x", 0))
                    pitch = int(card.get("col_mask_pitch_px", 44))
                    cw = mask_local.shape[1]
                    if pitch > 0 and start_x < cw:
                        col_centers = list(range(start_x, cw, pitch))
                half_w = int(card.get("col_mask_width_px", 22)) // 2
                margin = int(card.get("col_mask_margin_px", 4))
                mask_local = apply_column_strip_mask(mask_local, col_centers, half_w, margin)

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

            # Pitch Grid Regularization: snap blobs onto layout grid, normalize X bounds
            if card.get("col_mask_enabled", False) and card.get("col_mask_regularize", False) and col_centers:
                half_w = int(card.get("col_mask_width_px", 22)) // 2
                tol    = int(card.get("col_mask_pitch_tol_px", 5))
                norm_x = bool(card.get("col_mask_normalize_x", True))
                blobs  = regularize_blobs_to_columns(blobs, col_centers, half_w, tol, norm_x)

            # Analyze in rotated space; back-rotate blob coords after (same fix as CMGRecipe)
            cuts = analyze(blobs, nm_px)
            if axis == "X":
                orig_h = raw.shape[0]
                for c in cuts:
                    for m in c.measurements:
                        m.upper_blob = _rot_blob_to_ori(m.upper_blob, orig_h)
                        m.lower_blob = _rot_blob_to_ori(m.lower_blob, orig_h)

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
    """Remove measurements outside [min_px, max_px] and re-flag MIN/MAX."""
    from ...core.cmg_analyzer import CMGCut
    filtered = []
    for cut in cuts:
        kept = [m for m in cut.measurements
                if (min_px <= 0 or m.cd_px >= min_px)
                and (max_px <= 0 or m.cd_px <= max_px)]
        if kept:
            filtered.append(CMGCut(cmg_id=cut.cmg_id, measurements=kept))
    # Re-compute MIN/MAX flags on remaining measurements
    all_m = [m for c in filtered for m in c.measurements]
    if len(all_m) >= 2:
        mn = min(m.cd_px for m in all_m)
        mx = max(m.cd_px for m in all_m)
        for m in all_m:
            m.flag = "MIN" if m.cd_px == mn else ("MAX" if m.cd_px == mx else "")
    return filtered


def _ov_chk(text: str, checked: bool = True) -> QCheckBox:
    chk = QCheckBox(text)
    chk.setChecked(checked)
    chk.setStyleSheet(
        "QCheckBox { color:#8c7a66; font-size:11px; spacing:4px; }"
        "QCheckBox::indicator { width:12px; height:12px; }"
    )
    return chk
