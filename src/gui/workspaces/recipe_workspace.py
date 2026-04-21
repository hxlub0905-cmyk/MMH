"""Recipe workspace — create, edit, and version measurement recipes."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QSplitter,
    QListWidget, QListWidgetItem, QGroupBox, QFormLayout,
    QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox,
    QCheckBox, QPushButton, QLabel, QMessageBox, QSizePolicy,
    QTabWidget, QScrollArea,
)
from PyQt6.QtCore import Qt, pyqtSignal

from ...core.recipe_base import MeasurementRecipe, RecipeConfig
from ...core.recipe_registry import RecipeRegistry


class RecipeWorkspace(QWidget):
    recipe_saved   = pyqtSignal(object)   # MeasurementRecipe
    recipe_deleted = pyqtSignal(str)       # recipe_id
    status_message = pyqtSignal(str)

    def __init__(self, registry: RecipeRegistry, parent: QWidget | None = None):
        super().__init__(parent)
        self._registry = registry
        self._current_id: str | None = None
        self._name_auto: bool = False  # True while name should follow struct+axis
        self._build_ui()
        self._refresh_list()

    # ── Construction ──────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)

        # Left: recipe list + buttons
        left = QWidget()
        lv = QVBoxLayout(left)
        lv.setContentsMargins(4, 4, 4, 4)
        lv.addWidget(QLabel("Saved Recipes"))

        self._list = QListWidget()
        self._list.currentItemChanged.connect(self._on_recipe_selected)
        lv.addWidget(self._list, stretch=1)

        btn_row = QHBoxLayout()
        new_btn = QPushButton("New")
        tmpl_btn = QPushButton("CMG Template")
        dup_btn = QPushButton("Duplicate")
        del_btn = QPushButton("Delete")
        new_btn.clicked.connect(self._new_recipe)
        tmpl_btn.clicked.connect(self._new_from_cmg_template)
        dup_btn.clicked.connect(self._duplicate_recipe)
        del_btn.clicked.connect(self._delete_recipe)
        btn_row.addWidget(new_btn)
        btn_row.addWidget(tmpl_btn)
        btn_row.addWidget(dup_btn)
        btn_row.addWidget(del_btn)
        lv.addLayout(btn_row)

        splitter.addWidget(left)

        # Right: editor
        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(8, 8, 8, 8)
        rv.addWidget(self._build_editor())

        save_btn = QPushButton("Save Recipe")
        save_btn.clicked.connect(self._save_recipe)
        rv.addWidget(save_btn)

        splitter.addWidget(right)
        splitter.setSizes([240, 700])

        root.addWidget(splitter)

    def _build_editor(self) -> QWidget:
        outer = QWidget()
        ov = QVBoxLayout(outer)
        ov.setContentsMargins(0, 0, 0, 0)
        ov.setSpacing(6)

        # ── Identity (always visible) ─────────────────────────────────────────
        id_box = QGroupBox("Recipe Identity")
        id_form = QFormLayout(id_box)
        id_form.setSpacing(8)
        id_form.setContentsMargins(10, 14, 10, 10)

        self._name_edit   = QLineEdit()
        self._layer_edit  = QLineEdit()
        self._struct_edit = QLineEdit()
        self._struct_edit.setPlaceholderText("e.g. CMG, PEPI, MG")
        self._axis_combo  = QComboBox()
        self._axis_combo.addItems(["Y", "X"])
        self._axis_combo.setFixedWidth(60)

        # Auto-update name when struct/axis changes (until user edits it manually)
        self._struct_edit.textChanged.connect(self._on_struct_axis_changed)
        self._axis_combo.currentIndexChanged.connect(self._on_struct_axis_changed)
        self._name_edit.textEdited.connect(self._on_name_manually_edited)

        struct_row = QHBoxLayout()
        struct_row.addWidget(self._struct_edit)
        struct_row.addWidget(QLabel("Axis:"))
        struct_row.addWidget(self._axis_combo)

        id_form.addRow("Name:", self._name_edit)
        id_form.addRow("Target layer:", self._layer_edit)
        id_form.addRow("Structure:", struct_row)
        ov.addWidget(id_box)

        # ── Tabbed parameter sections ─────────────────────────────────────────
        tabs = QTabWidget()
        tabs.setDocumentMode(True)

        # ── Tab 1: Preprocessing ──────────────────────────────────────────────
        self._gl_min = QSpinBox(); self._gl_min.setRange(0, 255); self._gl_min.setValue(100)
        self._gl_max = QSpinBox(); self._gl_max.setRange(0, 255); self._gl_max.setValue(220)
        self._gauss  = QSpinBox(); self._gauss.setRange(1, 31);   self._gauss.setSingleStep(2); self._gauss.setValue(3)
        self._open_k = QSpinBox(); self._open_k.setRange(1, 31);  self._open_k.setSingleStep(2); self._open_k.setValue(3)
        self._close_k= QSpinBox(); self._close_k.setRange(1, 31); self._close_k.setSingleStep(2); self._close_k.setValue(5)
        self._clahe  = QCheckBox("Enable CLAHE"); self._clahe.setChecked(True)
        self._clahe_clip = QDoubleSpinBox(); self._clahe_clip.setRange(0.1, 20.0); self._clahe_clip.setValue(2.0)
        self._clahe_grid = QSpinBox(); self._clahe_grid.setRange(2, 32); self._clahe_grid.setValue(8)
        self._vert_erode_k    = QSpinBox(); self._vert_erode_k.setRange(0, 99); self._vert_erode_k.setValue(0); self._vert_erode_k.setSuffix(" px"); self._vert_erode_k.setSpecialValueText("off")
        self._vert_erode_iter = QSpinBox(); self._vert_erode_iter.setRange(1, 10); self._vert_erode_iter.setValue(1)

        pre_tab = QWidget()
        pf = QFormLayout(pre_tab)
        pf.setSpacing(8); pf.setContentsMargins(12, 10, 12, 10)
        pf.addRow("GL min:", self._gl_min)
        pf.addRow("GL max:", self._gl_max)
        pf.addRow("Gaussian (px):", self._gauss)
        pf.addRow("Morph open (px):", self._open_k)
        pf.addRow("Morph close (px):", self._close_k)
        pf.addRow(self._clahe)
        pf.addRow("CLAHE clip:", self._clahe_clip)
        pf.addRow("CLAHE grid:", self._clahe_grid)
        pf.addRow("Vert erode (px):", self._vert_erode_k)
        pf.addRow("Vert erode iter:", self._vert_erode_iter)
        tabs.addTab(pre_tab, "Preprocessing")

        # ── Tab 2: Detection ──────────────────────────────────────────────────
        self._min_area   = QSpinBox();        self._min_area.setRange(0, 500_000);  self._min_area.setValue(0);    self._min_area.setSuffix(" px²");   self._min_area.setSpecialValueText("auto")
        self._min_ar     = QDoubleSpinBox();  self._min_ar.setRange(0.0, 100.0);   self._min_ar.setValue(0.0);    self._min_ar.setSingleStep(0.1);    self._min_ar.setSpecialValueText("off")
        self._max_ar     = QDoubleSpinBox();  self._max_ar.setRange(0.0, 100.0);   self._max_ar.setValue(0.0);    self._max_ar.setSingleStep(0.1);    self._max_ar.setSpecialValueText("off")
        self._min_width  = QSpinBox();        self._min_width.setRange(0, 9999);    self._min_width.setValue(0);   self._min_width.setSuffix(" px");    self._min_width.setSpecialValueText("off")
        self._max_width  = QSpinBox();        self._max_width.setRange(0, 9999);    self._max_width.setValue(0);   self._max_width.setSuffix(" px");    self._max_width.setSpecialValueText("off")
        self._min_height = QSpinBox();        self._min_height.setRange(0, 9999);   self._min_height.setValue(0);  self._min_height.setSuffix(" px");   self._min_height.setSpecialValueText("off")

        det_tab = QWidget()
        df = QFormLayout(det_tab)
        df.setSpacing(8); df.setContentsMargins(12, 10, 12, 10)
        df.addRow("Min area:", self._min_area)
        df.addRow("Min aspect (h/w):", self._min_ar)
        df.addRow("Max aspect (h/w):", self._max_ar)
        df.addRow("Min width:", self._min_width)
        df.addRow("Max width:", self._max_width)
        df.addRow("Min height:", self._min_height)
        tabs.addTab(det_tab, "Detection")

        # ── Tab 3: Strip Mask ─────────────────────────────────────────────────
        self._strip_enabled     = QCheckBox("Enable strip mask");             self._strip_enabled.setChecked(False)
        self._strip_auto        = QCheckBox("Auto-detect centers (X-proj)");  self._strip_auto.setChecked(False)
        self._xproj_smooth      = QSpinBox();       self._xproj_smooth.setRange(1, 51);    self._xproj_smooth.setValue(5);   self._xproj_smooth.setSuffix(" px")
        self._xproj_pitch       = QSpinBox();       self._xproj_pitch.setRange(1, 9999);   self._xproj_pitch.setValue(30);   self._xproj_pitch.setSuffix(" px")
        self._xproj_min_frac    = QDoubleSpinBox(); self._xproj_min_frac.setRange(0.01, 1.0); self._xproj_min_frac.setValue(0.3); self._xproj_min_frac.setSingleStep(0.05)
        self._strip_start_x     = QSpinBox();       self._strip_start_x.setRange(0, 9999);  self._strip_start_x.setValue(0);  self._strip_start_x.setSuffix(" px")
        self._strip_pitch       = QSpinBox();       self._strip_pitch.setRange(1, 9999);    self._strip_pitch.setValue(44);   self._strip_pitch.setSuffix(" px")
        self._strip_width       = QSpinBox();       self._strip_width.setRange(1, 9999);    self._strip_width.setValue(22);   self._strip_width.setSuffix(" px")
        self._strip_margin      = QSpinBox();       self._strip_margin.setRange(0, 9999);   self._strip_margin.setValue(4);   self._strip_margin.setSuffix(" px")
        self._strip_edge_margin = QSpinBox();       self._strip_edge_margin.setRange(0, 999); self._strip_edge_margin.setValue(0); self._strip_edge_margin.setSuffix(" px"); self._strip_edge_margin.setSpecialValueText("off")
        self._strip_regularize  = QCheckBox("Regularize to grid");            self._strip_regularize.setChecked(False)
        self._strip_pitch_tol   = QSpinBox();       self._strip_pitch_tol.setRange(1, 99);  self._strip_pitch_tol.setValue(5); self._strip_pitch_tol.setSuffix(" px")
        self._strip_normalize_x = QCheckBox("Normalize X bounds");            self._strip_normalize_x.setChecked(True)
        self._strip_auto.toggled.connect(lambda on: self._strip_start_x.setEnabled(not on))

        strip_tab = QWidget()
        sf = QFormLayout(strip_tab)
        sf.setSpacing(8); sf.setContentsMargins(12, 10, 12, 10)
        sf.addRow(self._strip_enabled)
        sf.addRow(self._strip_auto)
        sf.addRow("  X-proj smooth:", self._xproj_smooth)
        sf.addRow("  X-proj min pitch:", self._xproj_pitch)
        sf.addRow("  X-proj min frac:", self._xproj_min_frac)
        sf.addRow("Start X (manual):", self._strip_start_x)
        sf.addRow("Pitch:", self._strip_pitch)
        sf.addRow("Strip width:", self._strip_width)
        sf.addRow("Margin ±:", self._strip_margin)
        sf.addRow("Edge margin:", self._strip_edge_margin)
        sf.addRow(self._strip_regularize)
        sf.addRow("  Pitch tolerance:", self._strip_pitch_tol)
        sf.addRow(self._strip_normalize_x)
        tabs.addTab(strip_tab, "Strip Mask")

        # ── Tab 4: Analysis ───────────────────────────────────────────────────
        self._overlap     = QDoubleSpinBox(); self._overlap.setRange(0.0, 1.0);    self._overlap.setValue(0.5);   self._overlap.setSingleStep(0.05)
        self._cluster_tol = QSpinBox();       self._cluster_tol.setRange(1, 100);  self._cluster_tol.setValue(10)
        self._edge_method = QComboBox()
        self._edge_method.addItem("Subpixel (gradient refined)", "subpixel")
        self._edge_method.addItem("BBox (original integer edge)", "bbox")
        self._range_enabled = QCheckBox("Enable range filter"); self._range_enabled.setChecked(False)
        self._min_line_px = QDoubleSpinBox(); self._min_line_px.setRange(0, 9999); self._min_line_px.setValue(0); self._min_line_px.setSuffix(" px"); self._min_line_px.setSpecialValueText("off")
        self._max_line_px = QDoubleSpinBox(); self._max_line_px.setRange(0, 9999); self._max_line_px.setValue(0); self._max_line_px.setSuffix(" px"); self._max_line_px.setSpecialValueText("off")

        ana_tab = QWidget()
        af = QFormLayout(ana_tab)
        af.setSpacing(8); af.setContentsMargins(12, 10, 12, 10)
        edge_lbl = QLabel("─── Edge Locator ───")
        edge_lbl.setStyleSheet("color:#666; font-size:11px;")
        af.addRow(edge_lbl)
        af.addRow("Y-CD edge method:", self._edge_method)
        af.addRow("X overlap ratio:", self._overlap)
        af.addRow("Cluster tol (px):", self._cluster_tol)
        range_lbl = QLabel("─── Range Filter ───")
        range_lbl.setStyleSheet("color:#666; font-size:11px;")
        af.addRow(range_lbl)
        af.addRow(self._range_enabled)
        af.addRow("Min CD (px):", self._min_line_px)
        af.addRow("Max CD (px):", self._max_line_px)
        tabs.addTab(ana_tab, "Analysis")

        ov.addWidget(tabs, stretch=1)
        return outer

    # ── List management ───────────────────────────────────────────────────────

    def _refresh_list(self) -> None:
        self._list.blockSignals(True)
        self._list.clear()
        for desc in self._registry.list_recipes():
            struct = desc.structure_name or "?"
            tag = f"{struct} {desc.axis_mode}-CD"
            item = QListWidgetItem(f"{desc.recipe_name}  [{tag}]")
            item.setData(Qt.ItemDataRole.UserRole, desc.recipe_id)
            self._list.addItem(item)
        self._list.blockSignals(False)

    def _on_recipe_selected(self, item: QListWidgetItem | None, _prev=None) -> None:
        if item is None:
            return
        rid = item.data(Qt.ItemDataRole.UserRole)
        desc = self._registry.get_descriptor(rid)
        if desc:
            self._current_id = rid
            self._load_descriptor_to_form(desc)

    def _load_descriptor_to_form(self, desc: MeasurementRecipe) -> None:
        self._name_auto = False  # loaded recipes keep their explicit name
        self._name_edit.setText(desc.recipe_name)
        self._layer_edit.setText(desc.target_layer)
        self._struct_edit.setText(desc.structure_name)
        self._axis_combo.setCurrentText(desc.axis_mode)

        pc = desc.preprocess_config
        self._gl_min.setValue(int(pc.get("gl_min", 100)))
        self._gl_max.setValue(int(pc.get("gl_max", 220)))
        self._gauss.setValue(int(pc.get("gauss_kernel", 3)))
        self._open_k.setValue(int(pc.get("morph_open_k", 3)))
        self._close_k.setValue(int(pc.get("morph_close_k", 5)))
        self._clahe.setChecked(bool(pc.get("use_clahe", True)))
        self._clahe_clip.setValue(float(pc.get("clahe_clip", 2.0)))
        self._clahe_grid.setValue(int(pc.get("clahe_grid", 8)))
        self._vert_erode_k.setValue(int(pc.get("vert_erode_k", 0)))
        self._vert_erode_iter.setValue(int(pc.get("vert_erode_iter", 1)))

        dc = desc.detector_config
        self._min_area.setValue(int(dc.get("min_area", 0) or 0))
        self._min_ar.setValue(float(dc.get("min_aspect_ratio", 0.0)))
        self._max_ar.setValue(float(dc.get("max_aspect_ratio", 0.0)))
        self._min_width.setValue(int(dc.get("min_width", 0)))
        self._max_width.setValue(int(dc.get("max_width", 0)))
        self._min_height.setValue(int(dc.get("min_height", 0)))
        self._xproj_smooth.setValue(int(dc.get("xproj_smooth_k", 5)))
        self._xproj_pitch.setValue(int(dc.get("xproj_min_pitch_px", 30)))
        self._xproj_min_frac.setValue(float(dc.get("xproj_peak_min_frac", 0.3)))
        self._strip_enabled.setChecked(bool(dc.get("col_mask_enabled", False)))
        auto_on = bool(dc.get("col_mask_auto_centers", False)) or bool(dc.get("xproj_enabled", False))
        self._strip_auto.setChecked(auto_on)
        self._strip_start_x.setEnabled(not auto_on)
        self._strip_start_x.setValue(int(dc.get("col_mask_start_x", 0)))
        self._strip_pitch.setValue(int(dc.get("col_mask_pitch_px", 44)))
        self._strip_width.setValue(int(dc.get("col_mask_width_px", 22)))
        self._strip_margin.setValue(int(dc.get("col_mask_margin_px", 4)))
        self._strip_edge_margin.setValue(int(dc.get("col_mask_edge_margin_px", 0)))
        self._strip_regularize.setChecked(bool(dc.get("col_mask_regularize", False)))
        self._strip_pitch_tol.setValue(int(dc.get("col_mask_pitch_tol_px", 5)))
        self._strip_normalize_x.setChecked(bool(dc.get("col_mask_normalize_x", True)))

        ec = desc.edge_locator_config
        _method = str(ec.get("ycd_edge_method", "subpixel")).lower()
        _method_idx = self._edge_method.findData(_method)
        self._edge_method.setCurrentIndex(_method_idx if _method_idx >= 0 else 0)
        self._overlap.setValue(float(ec.get("x_overlap_ratio", 0.5)))
        self._cluster_tol.setValue(int(ec.get("y_cluster_tol", 10)))

        self._range_enabled.setChecked(bool(dc.get("range_enabled", False)))
        self._min_line_px.setValue(float(dc.get("min_line_px", 0)))
        self._max_line_px.setValue(float(dc.get("max_line_px", 0)))

    # ── CRUD ──────────────────────────────────────────────────────────────────

    def _new_recipe(self) -> None:
        self._current_id = None
        self._name_auto = True  # enable auto-name until user edits manually
        blank = MeasurementRecipe(
            recipe_id=str(uuid.uuid4()),
            recipe_name="",
            recipe_type="STRUCT_YCD",
            structure_name="",
            axis_mode="Y",
        )
        self._load_descriptor_to_form(blank)
        self._name_auto = True  # restore after load (load sets it False)
        self._name_edit.setPlaceholderText("auto-generated from structure + axis")
        self._struct_edit.setFocus()

    def _new_from_cmg_template(self) -> None:
        """Pre-fill editor with built-in CMG Y-CD defaults (does not save yet)."""
        self._current_id = None
        from ...core.recipe_base import RecipeConfig
        tmpl = MeasurementRecipe(
            recipe_id=str(uuid.uuid4()),
            recipe_name="CMG Y-CD",
            recipe_type="CMG_YCD",
            structure_name="CMG",
            axis_mode="Y",
            preprocess_config=RecipeConfig(data={
                "gl_min": 100, "gl_max": 220,
                "gauss_kernel": 3, "morph_open_k": 3, "morph_close_k": 5,
                "use_clahe": True, "clahe_clip": 2.0, "clahe_grid": 8,
            }),
            edge_locator_config=RecipeConfig(data={
                "x_overlap_ratio": 0.5, "y_cluster_tol": 10,
            }),
        )
        self._load_descriptor_to_form(tmpl)
        self._name_edit.setFocus()
        self._name_edit.selectAll()

    def _duplicate_recipe(self) -> None:
        if self._current_id is None:
            return
        orig = self._registry.get_descriptor(self._current_id)
        if orig is None:
            return
        dup = MeasurementRecipe.from_dict(orig.to_dict())
        dup.recipe_id = str(uuid.uuid4())
        dup.recipe_name = f"{orig.recipe_name} (copy)"
        dup.created_at = datetime.now(timezone.utc).isoformat()
        self._registry.save(dup)
        self._refresh_list()
        self.recipe_saved.emit(dup)
        self.status_message.emit(f"Duplicated → '{dup.recipe_name}'")

    def _delete_recipe(self) -> None:
        if self._current_id is None:
            return
        desc = self._registry.get_descriptor(self._current_id)
        name = desc.recipe_name if desc else self._current_id
        ans = QMessageBox.question(
            self, "Delete Recipe",
            f"Delete '{name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if ans != QMessageBox.StandardButton.Yes:
            return
        self._registry.delete(self._current_id)
        self._current_id = None
        self._refresh_list()
        self.recipe_deleted.emit(self._current_id or "")
        self.status_message.emit(f"Deleted recipe '{name}'")

    def _save_recipe(self) -> None:
        struct = self._struct_edit.text().strip()
        axis = self._axis_combo.currentText()
        name = self._name_edit.text().strip() or f"{struct or 'STRUCT'} {axis}-CD"
        if not name:
            QMessageBox.warning(self, "Validation", "Recipe name cannot be empty.")
            return

        rid = self._current_id or str(uuid.uuid4())
        desc = self._registry.get_descriptor(rid)
        created = desc.created_at if desc else datetime.now(timezone.utc).isoformat()

        recipe_type = f"{struct or 'STRUCT'}_{axis}CD"
        min_area_val = self._min_area.value() or None  # 0 → None (auto)
        new_desc = MeasurementRecipe(
            recipe_id=rid,
            recipe_name=name,
            recipe_type=recipe_type,
            target_layer=self._layer_edit.text().strip(),
            structure_name=struct,
            axis_mode=axis,
            preprocess_config=RecipeConfig(data={
                "gl_min": self._gl_min.value(),
                "gl_max": self._gl_max.value(),
                "gauss_kernel": self._gauss.value(),
                "morph_open_k": self._open_k.value(),
                "morph_close_k": self._close_k.value(),
                "use_clahe": self._clahe.isChecked(),
                "clahe_clip": self._clahe_clip.value(),
                "clahe_grid": self._clahe_grid.value(),
                "vert_erode_k": self._vert_erode_k.value(),
                "vert_erode_iter": self._vert_erode_iter.value(),
            }),
            detector_config=RecipeConfig(data={
                "min_area": min_area_val,
                "min_aspect_ratio": self._min_ar.value(),
                "max_aspect_ratio": self._max_ar.value(),
                "min_width": self._min_width.value(),
                "max_width": self._max_width.value(),
                "min_height": self._min_height.value(),
                "xproj_enabled": self._strip_auto.isChecked(),  # backward compat
                "xproj_smooth_k": self._xproj_smooth.value(),
                "xproj_min_pitch_px": self._xproj_pitch.value(),
                "xproj_peak_min_frac": self._xproj_min_frac.value(),
                "col_mask_enabled": self._strip_enabled.isChecked(),
                "col_mask_auto_centers": self._strip_auto.isChecked(),
                "col_mask_start_x": self._strip_start_x.value(),
                "col_mask_pitch_px": self._strip_pitch.value(),
                "col_mask_width_px": self._strip_width.value(),
                "col_mask_margin_px": self._strip_margin.value(),
                "col_mask_edge_margin_px": self._strip_edge_margin.value(),
                "col_mask_regularize": self._strip_regularize.isChecked(),
                "col_mask_pitch_tol_px": self._strip_pitch_tol.value(),
                "col_mask_normalize_x": self._strip_normalize_x.isChecked(),
                "range_enabled": self._range_enabled.isChecked(),
                "min_line_px": self._min_line_px.value(),
                "max_line_px": self._max_line_px.value(),
            }),
            edge_locator_config=RecipeConfig(data={
                # Carry forward all existing keys (e.g. subpixel_* set via JSON),
                # then override the ones the UI explicitly controls.
                **(desc.edge_locator_config.to_dict() if desc else {}),
                "ycd_edge_method": self._edge_method.currentData(),
                "x_overlap_ratio": self._overlap.value(),
                "y_cluster_tol": self._cluster_tol.value(),
            }),
            version=((desc.version + 1) if desc else 1),
            created_at=created,
        )
        self._registry.save(new_desc)
        self._current_id = rid
        self._refresh_list()
        self.recipe_saved.emit(new_desc)
        self.status_message.emit(f"Saved recipe '{name}'")

    def refresh_from_registry(self) -> None:
        self._refresh_list()

    # ── Auto-name helpers ─────────────────────────────────────────────────────

    def _on_struct_axis_changed(self) -> None:
        if not self._name_auto:
            return
        struct = self._struct_edit.text().strip()
        axis = self._axis_combo.currentText()
        if struct:
            self._name_edit.setText(f"{struct} {axis}-CD")

    def _on_name_manually_edited(self) -> None:
        self._name_auto = False
        self._name_edit.setPlaceholderText("")
