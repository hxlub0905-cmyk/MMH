"""Browse workspace — file tree, image preview, calibration selection."""
from __future__ import annotations

from pathlib import Path

from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QSplitter,
    QGroupBox, QFormLayout, QDoubleSpinBox,
    QLabel, QPushButton, QComboBox, QSizePolicy,
)
from PyQt6.QtCore import Qt, pyqtSignal

from ..file_tree_panel import FileTreePanel
from ..image_viewer import ImageViewer
from ...core.models import ImageRecord
from ...core.calibration import CalibrationManager, CalibrationProfile
from ...core.image_loader import load_grayscale


class BrowseWorkspace(QWidget):
    image_selected = pyqtSignal(object)   # emits ImageRecord
    status_message = pyqtSignal(str)

    def __init__(
        self,
        cal_manager: CalibrationManager,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self._cal_manager = cal_manager
        self._current_ir: ImageRecord | None = None
        self._build_ui()

    # ── Construction ──────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)

        # Left: file tree
        left = QWidget()
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 0, 0)

        open_btn = QPushButton("Open Folder…")
        open_btn.clicked.connect(self._open_folder)
        lv.addWidget(open_btn)

        self._tree = FileTreePanel()
        self._tree.file_selected.connect(self._on_file_selected)
        lv.addWidget(self._tree)

        splitter.addWidget(left)

        # Right: preview + calibration selector
        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(4, 4, 4, 4)

        self._viewer = ImageViewer()
        rv.addWidget(self._viewer, stretch=1)

        rv.addWidget(self._build_calibration_bar())

        measure_btn = QPushButton("Send to Measure →")
        measure_btn.clicked.connect(self._send_to_measure)
        rv.addWidget(measure_btn)

        splitter.addWidget(right)
        splitter.setSizes([220, 800])
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)

        root.addWidget(splitter)

    def _build_calibration_bar(self) -> QWidget:
        box = QGroupBox("Calibration")
        form = QFormLayout(box)

        self._cal_combo = QComboBox()
        self._cal_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._cal_combo.currentIndexChanged.connect(self._on_cal_changed)
        form.addRow(QLabel("Profile:"), self._cal_combo)

        self._nm_px_spin = QDoubleSpinBox()
        self._nm_px_spin.setRange(0.0001, 10000.0)
        self._nm_px_spin.setValue(1.0)
        self._nm_px_spin.setDecimals(4)
        self._nm_px_spin.setSuffix(" nm/px")
        self._nm_px_spin.valueChanged.connect(self._on_nm_px_changed)
        form.addRow(QLabel("nm / pixel:"), self._nm_px_spin)

        save_btn = QPushButton("Save as new profile…")
        save_btn.clicked.connect(self._save_new_profile)
        form.addRow(save_btn)

        self._refresh_cal_combo()
        return box

    # ── Calibration helpers ───────────────────────────────────────────────────

    def _refresh_cal_combo(self) -> None:
        self._cal_combo.blockSignals(True)
        self._cal_combo.clear()
        profiles = self._cal_manager.list_profiles()
        for p in profiles:
            self._cal_combo.addItem(f"{p.profile_name}  ({p.nm_per_pixel:.4f} nm/px)", p.profile_id)
        if not profiles:
            self._cal_combo.addItem("Default (1.0 nm/px)", "__fallback__")
        self._cal_combo.blockSignals(False)

    def _current_profile(self) -> CalibrationProfile:
        idx = self._cal_combo.currentIndex()
        if idx < 0:
            return self._cal_manager.get_default()
        pid = self._cal_combo.itemData(idx)
        if pid == "__fallback__":
            return self._cal_manager.get_default()
        return self._cal_manager.get(pid) or self._cal_manager.get_default()

    def _on_cal_changed(self, _idx: int) -> None:
        prof = self._current_profile()
        self._nm_px_spin.blockSignals(True)
        self._nm_px_spin.setValue(prof.nm_per_pixel)
        self._nm_px_spin.blockSignals(False)

    def _on_nm_px_changed(self, _value: float) -> None:
        pass  # value read on demand; no auto-save

    def _save_new_profile(self) -> None:
        from PyQt6.QtWidgets import QInputDialog
        name, ok = QInputDialog.getText(self, "New Profile", "Profile name:")
        if not ok or not name.strip():
            return
        p = self._cal_manager.create_new(
            name=name.strip(),
            nm_per_pixel=self._nm_px_spin.value(),
        )
        self._refresh_cal_combo()
        self.status_message.emit(f"Saved calibration profile '{p.profile_name}'")

    # ── File selection ────────────────────────────────────────────────────────

    def _open_folder(self) -> None:
        from PyQt6.QtWidgets import QFileDialog
        folder = QFileDialog.getExistingDirectory(self, "Open Folder")
        if folder:
            self._tree.set_root(Path(folder))
            self.status_message.emit(f"Opened folder: {folder}")

    def _on_file_selected(self, path: Path) -> None:
        nm_per_px = self._nm_px_spin.value()
        self._current_ir = ImageRecord.from_path(path, pixel_size_nm=nm_per_px)

        try:
            raw = load_grayscale(str(path))
            self._viewer.set_images(raw, None, None)
            self._viewer.set_mode("raw")
        except Exception as exc:
            self.status_message.emit(f"Preview failed: {exc}")

        self.status_message.emit(f"Selected: {path.name}  ({nm_per_px:.4f} nm/px)")

    def _send_to_measure(self) -> None:
        if self._current_ir is None:
            self.status_message.emit("Select an image first.")
            return
        self._current_ir.pixel_size_nm = self._nm_px_spin.value()
        self.image_selected.emit(self._current_ir)

    # ── Public API ────────────────────────────────────────────────────────────

    def set_root(self, path: Path) -> None:
        self._tree.set_root(path)
