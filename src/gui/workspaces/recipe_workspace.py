"""Recipe workspace — create, edit, and version measurement recipes."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QSplitter,
    QListWidget, QListWidgetItem, QGroupBox, QFormLayout,
    QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox,
    QCheckBox, QPushButton, QLabel, QMessageBox, QSizePolicy,
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
        dup_btn = QPushButton("Duplicate")
        del_btn = QPushButton("Delete")
        new_btn.clicked.connect(self._new_recipe)
        dup_btn.clicked.connect(self._duplicate_recipe)
        del_btn.clicked.connect(self._delete_recipe)
        btn_row.addWidget(new_btn)
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

    def _build_editor(self) -> QGroupBox:
        box = QGroupBox("Recipe Editor")
        form = QFormLayout(box)

        self._name_edit   = QLineEdit()
        self._layer_edit  = QLineEdit()
        self._type_combo  = QComboBox()
        self._type_combo.addItems(["CMG_YCD", "CMG_XCD"])
        self._axis_combo  = QComboBox()
        self._axis_combo.addItems(["Y", "X"])
        self._type_combo.currentIndexChanged.connect(self._sync_axis_from_type)

        form.addRow("Name:", self._name_edit)
        form.addRow("Target layer:", self._layer_edit)
        form.addRow("Recipe type:", self._type_combo)
        form.addRow("Axis mode:", self._axis_combo)

        # Preprocess
        pre_box = QGroupBox("Preprocessing")
        pf = QFormLayout(pre_box)
        self._gl_min = QSpinBox(); self._gl_min.setRange(0, 255); self._gl_min.setValue(100)
        self._gl_max = QSpinBox(); self._gl_max.setRange(0, 255); self._gl_max.setValue(220)
        self._gauss  = QSpinBox(); self._gauss.setRange(1, 31);   self._gauss.setSingleStep(2); self._gauss.setValue(3)
        self._open_k = QSpinBox(); self._open_k.setRange(1, 31);  self._open_k.setSingleStep(2); self._open_k.setValue(3)
        self._close_k= QSpinBox(); self._close_k.setRange(1, 31); self._close_k.setSingleStep(2); self._close_k.setValue(5)
        self._clahe  = QCheckBox("Enable CLAHE"); self._clahe.setChecked(True)
        self._clahe_clip = QDoubleSpinBox(); self._clahe_clip.setRange(0.1, 20.0); self._clahe_clip.setValue(2.0)
        self._clahe_grid = QSpinBox(); self._clahe_grid.setRange(2, 32); self._clahe_grid.setValue(8)
        pf.addRow("GL min:", self._gl_min)
        pf.addRow("GL max:", self._gl_max)
        pf.addRow("Gaussian (px):", self._gauss)
        pf.addRow("Morph open (px):", self._open_k)
        pf.addRow("Morph close (px):", self._close_k)
        pf.addRow(self._clahe)
        pf.addRow("CLAHE clip:", self._clahe_clip)
        pf.addRow("CLAHE grid:", self._clahe_grid)

        # Edge locator
        edge_box = QGroupBox("Edge Locator")
        ef = QFormLayout(edge_box)
        self._overlap = QDoubleSpinBox(); self._overlap.setRange(0.0, 1.0); self._overlap.setValue(0.5); self._overlap.setSingleStep(0.05)
        self._cluster_tol = QSpinBox(); self._cluster_tol.setRange(1, 100); self._cluster_tol.setValue(10)
        ef.addRow("X overlap ratio:", self._overlap)
        ef.addRow("Cluster tol (px):", self._cluster_tol)

        form.addRow(pre_box)
        form.addRow(edge_box)

        return box

    # ── List management ───────────────────────────────────────────────────────

    def _refresh_list(self) -> None:
        self._list.blockSignals(True)
        self._list.clear()
        for desc in self._registry.list_recipes():
            item = QListWidgetItem(f"{desc.recipe_name}  [{desc.recipe_type}]")
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
        self._name_edit.setText(desc.recipe_name)
        self._layer_edit.setText(desc.target_layer)
        idx = self._type_combo.findText(desc.recipe_type)
        self._type_combo.setCurrentIndex(max(0, idx))
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

        ec = desc.edge_locator_config
        self._overlap.setValue(float(ec.get("x_overlap_ratio", 0.5)))
        self._cluster_tol.setValue(int(ec.get("y_cluster_tol", 10)))

    def _sync_axis_from_type(self) -> None:
        rtype = self._type_combo.currentText()
        self._axis_combo.setCurrentText("X" if "XCD" in rtype else "Y")

    # ── CRUD ──────────────────────────────────────────────────────────────────

    def _new_recipe(self) -> None:
        self._current_id = None
        blank = MeasurementRecipe(
            recipe_id=str(uuid.uuid4()),
            recipe_name="New Recipe",
            recipe_type="CMG_YCD",
            axis_mode="Y",
        )
        self._load_descriptor_to_form(blank)
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
        name = self._name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "Validation", "Recipe name cannot be empty.")
            return

        rid = self._current_id or str(uuid.uuid4())
        desc = self._registry.get_descriptor(rid)
        created = desc.created_at if desc else datetime.now(timezone.utc).isoformat()

        new_desc = MeasurementRecipe(
            recipe_id=rid,
            recipe_name=name,
            recipe_type=self._type_combo.currentText(),
            target_layer=self._layer_edit.text().strip(),
            feature_family="CMG",
            axis_mode=self._axis_combo.currentText(),
            preprocess_config=RecipeConfig(data={
                "gl_min": self._gl_min.value(),
                "gl_max": self._gl_max.value(),
                "gauss_kernel": self._gauss.value(),
                "morph_open_k": self._open_k.value(),
                "morph_close_k": self._close_k.value(),
                "use_clahe": self._clahe.isChecked(),
                "clahe_clip": self._clahe_clip.value(),
                "clahe_grid": self._clahe_grid.value(),
            }),
            edge_locator_config=RecipeConfig(data={
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
