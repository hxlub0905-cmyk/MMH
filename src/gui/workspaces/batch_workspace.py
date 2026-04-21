"""Batch workspace — folder-level batch processing with progress and results."""
from __future__ import annotations

import os
from pathlib import Path

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QGroupBox, QFormLayout, QLabel, QPushButton,
    QComboBox, QSpinBox, QProgressBar, QTextEdit,
    QListWidget, QListWidgetItem, QFileDialog,
    QMessageBox, QCheckBox, QSizePolicy,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, pyqtSlot

from ...core.models import ImageRecord, BatchRunRecord
from ...core.recipe_registry import RecipeRegistry
from ...core.measurement_engine import MeasurementEngine
from ...core.calibration import CalibrationManager
from ...core.image_loader import scan_folder


class BatchWorkspace(QWidget):
    batch_completed = pyqtSignal(object)  # BatchRunRecord
    status_message  = pyqtSignal(str)

    def __init__(
        self,
        engine: MeasurementEngine,
        registry: RecipeRegistry,
        cal_manager: CalibrationManager,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self._engine      = engine
        self._registry    = registry
        self._cal_manager = cal_manager
        self._worker: _BatchWorker | None = None
        self._last_batch: BatchRunRecord | None = None
        self._build_ui()

    # ── Construction ──────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        # Settings
        settings_box = QGroupBox("Batch Settings")
        form = QFormLayout(settings_box)

        folder_row = QHBoxLayout()
        self._folder_label = QLabel("(no folder selected)")
        self._folder_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        folder_row.addWidget(self._folder_label)
        folder_btn = QPushButton("Browse…")
        folder_btn.clicked.connect(self._select_folder)
        folder_row.addWidget(folder_btn)
        form.addRow("Input folder:", folder_row)

        self._recipe_combo = QComboBox()
        self._recipe_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        form.addRow("Recipe:", self._recipe_combo)

        self._worker_spin = QSpinBox()
        self._worker_spin.setRange(1, os.cpu_count() or 4)
        self._worker_spin.setValue(max(1, (os.cpu_count() or 2) - 1))
        form.addRow("Workers:", self._worker_spin)

        root.addWidget(settings_box)

        # Run button
        run_btn = QPushButton("Run Batch")
        run_btn.clicked.connect(self._run_batch)
        root.addWidget(run_btn)

        # Progress
        prog_box = QGroupBox("Progress")
        pv = QVBoxLayout(prog_box)
        self._progress = QProgressBar()
        self._progress.setTextVisible(True)
        pv.addWidget(self._progress)
        self._log_text = QTextEdit()
        self._log_text.setReadOnly(True)
        self._log_text.setMaximumHeight(120)
        pv.addWidget(self._log_text)
        root.addWidget(prog_box)

        # Results list
        results_box = QGroupBox("Image Results")
        rv = QVBoxLayout(results_box)
        self._image_list = QListWidget()
        rv.addWidget(self._image_list)
        root.addWidget(results_box, stretch=1)

        self._refresh_recipe_combo()

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _refresh_recipe_combo(self) -> None:
        self._recipe_combo.blockSignals(True)
        self._recipe_combo.clear()
        for desc in self._registry.list_recipes():
            self._recipe_combo.addItem(f"{desc.recipe_name}  [{desc.recipe_type}]", desc.recipe_id)
        if self._recipe_combo.count() == 0:
            self._recipe_combo.addItem("(no recipes saved)", None)
        self._recipe_combo.blockSignals(False)

    def refresh_recipe_selector(self, _recipe=None) -> None:
        self._refresh_recipe_combo()

    def _select_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Select Input Folder")
        if folder:
            self._folder_label.setText(folder)

    # ── Batch execution ───────────────────────────────────────────────────────

    def _run_batch(self) -> None:
        folder = self._folder_label.text()
        if folder == "(no folder selected)" or not Path(folder).is_dir():
            QMessageBox.warning(self, "No folder", "Select a valid input folder.")
            return

        recipe_id = self._recipe_combo.currentData()
        if recipe_id is None:
            QMessageBox.warning(self, "No recipe", "Create and save a recipe first.")
            return

        paths = scan_folder(folder)
        if not paths:
            QMessageBox.information(self, "No images", "No supported images found in folder.")
            return

        cal = self._cal_manager.get_default()
        image_records = [
            ImageRecord.from_path(p, pixel_size_nm=cal.nm_per_pixel)
            for p in paths
        ]

        self._log_text.clear()
        self._image_list.clear()
        self._progress.setMaximum(len(image_records))
        self._progress.setValue(0)

        self._worker = _BatchWorker(
            engine=self._engine,
            image_records=image_records,
            recipe_ids=[recipe_id],
            max_workers=self._worker_spin.value(),
        )
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_batch_finished)
        self._worker.error.connect(self._on_batch_error)
        self._worker.start()
        self.status_message.emit(f"Batch started — {len(image_records)} images")

    @pyqtSlot(int, int, str, str)
    def _on_progress(self, done: int, total: int, name: str, status: str) -> None:
        self._progress.setValue(done)
        self._log_text.append(f"[{done}/{total}] {name}")
        item = QListWidgetItem(f"[{status}]  {name}")
        item.setForeground(Qt.GlobalColor.red if status != "OK" else Qt.GlobalColor.darkGreen)
        self._image_list.addItem(item)

    @pyqtSlot(object)
    def _on_batch_finished(self, batch_run: BatchRunRecord) -> None:
        self._last_batch = batch_run
        self._progress.setValue(batch_run.total_images)
        msg = (f"Batch complete  ·  {batch_run.success_count} OK  "
               f"·  {batch_run.fail_count} failed  —  Results sent to Review tab")
        self._log_text.append(msg)
        self.status_message.emit(msg)
        self.batch_completed.emit(batch_run)

    @pyqtSlot(str)
    def _on_batch_error(self, err: str) -> None:
        self._log_text.append(f"ERROR: {err}")
        self.status_message.emit(f"Batch error: {err}")


class _BatchWorker(QThread):
    progress = pyqtSignal(int, int, str, str)  # done, total, name, status
    finished = pyqtSignal(object)
    error    = pyqtSignal(str)

    def __init__(
        self,
        engine: MeasurementEngine,
        image_records: list[ImageRecord],
        recipe_ids: list[str],
        max_workers: int,
    ):
        super().__init__()
        self._engine        = engine
        self._image_records = image_records
        self._recipe_ids    = recipe_ids
        self._max_workers   = max_workers

    def run(self) -> None:
        try:
            batch_run = self._engine.run_batch(
                image_records=self._image_records,
                recipe_ids=self._recipe_ids,
                on_progress=lambda done, total, name, status: self.progress.emit(done, total, name, status),
                max_workers=self._max_workers,
            )
            self.finished.emit(batch_run)
        except Exception as exc:
            self.error.emit(str(exc))
