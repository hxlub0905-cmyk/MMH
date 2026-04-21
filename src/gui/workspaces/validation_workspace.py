"""ValidationWorkspace — Recipe golden-sample validation UI."""
from __future__ import annotations

import csv
from pathlib import Path

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox,
    QLabel, QPushButton, QComboBox, QTableWidget, QTableWidgetItem,
    QProgressBar, QFileDialog, QHeaderView, QAbstractItemView, QFormLayout,
    QApplication,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QColor

from ...core.measurement_engine import MeasurementEngine
from ...core.recipe_registry import RecipeRegistry
from ...core.models import GoldenSampleEntry, ValidationResult
from ..styles import STYLE


class ValidationWorkspace(QWidget):
    status_message = pyqtSignal(str)

    def __init__(
        self,
        engine: MeasurementEngine,
        registry: RecipeRegistry,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self._engine   = engine
        self._registry = registry
        self._worker: _ValidationWorker | None = None
        self._results: list[ValidationResult] = []
        self._build_ui()

    # ── Construction ──────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        # ── Recipe selector ────────────────────────────────────────────────────
        recipe_box = QGroupBox("Recipe")
        rh = QHBoxLayout(recipe_box)
        rh.addWidget(QLabel("Recipe:"))
        self._recipe_combo = QComboBox()
        self._recipe_combo.setSizePolicy(
            self._recipe_combo.sizePolicy().horizontalPolicy(),
            self._recipe_combo.sizePolicy().verticalPolicy(),
        )
        rh.addWidget(self._recipe_combo, 1)
        root.addWidget(recipe_box)
        self._populate_recipe_combo()

        # ── Golden sample table ────────────────────────────────────────────────
        sample_box = QGroupBox("Golden Samples")
        sv = QVBoxLayout(sample_box)
        self._sample_table = QTableWidget(0, 5)
        self._sample_table.setHorizontalHeaderLabels(
            ["File", "Reference nm", "CMG ID", "Col ID", "Notes"]
        )
        self._sample_table.horizontalHeader().setStretchLastSection(True)
        self._sample_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        sv.addWidget(self._sample_table)

        btns = QHBoxLayout()
        add_btn = QPushButton("Add Files…")
        rm_btn  = QPushButton("Remove Selected")
        csv_btn = QPushButton("Load CSV…")
        add_btn.clicked.connect(self._add_files)
        rm_btn.clicked.connect(self._remove_selected)
        csv_btn.clicked.connect(self._load_csv)
        btns.addWidget(add_btn)
        btns.addWidget(rm_btn)
        btns.addWidget(csv_btn)
        btns.addStretch()
        sv.addLayout(btns)
        root.addWidget(sample_box)

        # ── Run controls ───────────────────────────────────────────────────────
        run_row = QHBoxLayout()
        self._run_btn = QPushButton("Run Validation")
        self._run_btn.clicked.connect(self._run_validation)
        self._progress = QProgressBar()
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        run_row.addWidget(self._run_btn)
        run_row.addWidget(self._progress, 1)
        root.addLayout(run_row)

        # ── Results ────────────────────────────────────────────────────────────
        results_box = QGroupBox("Validation Results")
        rv = QVBoxLayout(results_box)

        # Stats summary
        self._stats_form = QFormLayout()
        stats_widget = QWidget()
        stats_widget.setLayout(self._stats_form)
        rv.addWidget(stats_widget)

        # Results table
        self._result_table = QTableWidget(0, 5)
        self._result_table.setHorizontalHeaderLabels(
            ["File", "Reference (nm)", "Measured (nm)", "Bias (nm)", "Status"]
        )
        self._result_table.horizontalHeader().setStretchLastSection(True)
        self._result_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        rv.addWidget(self._result_table)

        export_btn = QPushButton("Export Report CSV…")
        export_btn.clicked.connect(self._export_csv)
        rv.addWidget(export_btn, alignment=Qt.AlignmentFlag.AlignLeft)

        root.addWidget(results_box, stretch=1)

    # ── Public API ────────────────────────────────────────────────────────────

    def refresh_recipe_selector(self, _recipe=None) -> None:
        cur_id = self._recipe_combo.currentData()
        self._populate_recipe_combo()
        if cur_id:
            for i in range(self._recipe_combo.count()):
                if self._recipe_combo.itemData(i) == cur_id:
                    self._recipe_combo.setCurrentIndex(i)
                    break

    # ── Internal ──────────────────────────────────────────────────────────────

    def _populate_recipe_combo(self) -> None:
        self._recipe_combo.blockSignals(True)
        self._recipe_combo.clear()
        for desc in self._registry.list_recipes():
            self._recipe_combo.addItem(
                f"{desc.recipe_name}  [{desc.recipe_type}]", desc.recipe_id
            )
        if self._recipe_combo.count() == 0:
            self._recipe_combo.addItem("(no recipes)", None)
        self._recipe_combo.blockSignals(False)

    def _add_files(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Select golden sample images",
            filter="Images (*.tif *.tiff *.png *.bmp *.jpg)"
        )
        for p in paths:
            row = self._sample_table.rowCount()
            self._sample_table.insertRow(row)
            self._sample_table.setItem(row, 0, QTableWidgetItem(p))
            self._sample_table.setItem(row, 1, QTableWidgetItem("0.0"))
            self._sample_table.setItem(row, 2, QTableWidgetItem("0"))
            self._sample_table.setItem(row, 3, QTableWidgetItem("0"))
            self._sample_table.setItem(row, 4, QTableWidgetItem(""))

    def _remove_selected(self) -> None:
        rows = sorted(
            {idx.row() for idx in self._sample_table.selectedIndexes()},
            reverse=True,
        )
        for row in rows:
            self._sample_table.removeRow(row)

    def _load_csv(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Load golden sample CSV", filter="CSV (*.csv)"
        )
        if not path:
            return
        try:
            with open(path, newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for entry in reader:
                    row = self._sample_table.rowCount()
                    self._sample_table.insertRow(row)
                    self._sample_table.setItem(row, 0, QTableWidgetItem(entry.get("file_path", "")))
                    self._sample_table.setItem(row, 1, QTableWidgetItem(entry.get("reference_nm", "0")))
                    self._sample_table.setItem(row, 2, QTableWidgetItem(entry.get("cmg_id", "0")))
                    self._sample_table.setItem(row, 3, QTableWidgetItem(entry.get("col_id", "0")))
                    self._sample_table.setItem(row, 4, QTableWidgetItem(entry.get("notes", "")))
        except Exception as exc:
            self.status_message.emit(f"CSV load error: {exc}")

    def _collect_entries(self) -> list[GoldenSampleEntry]:
        entries = []
        for row in range(self._sample_table.rowCount()):
            def cell(c: int) -> str:
                item = self._sample_table.item(row, c)
                return item.text().strip() if item else ""
            try:
                entries.append(GoldenSampleEntry(
                    file_path=cell(0),
                    reference_nm=float(cell(1) or "0"),
                    cmg_id=int(cell(2) or "0"),
                    col_id=int(cell(3) or "0"),
                    notes=cell(4),
                ))
            except (ValueError, TypeError):
                pass
        return entries

    def _run_validation(self) -> None:
        recipe_id = self._recipe_combo.currentData()
        if not recipe_id:
            self.status_message.emit("Select a recipe first.")
            return
        recipe = self._registry.get(recipe_id)
        if recipe is None:
            self.status_message.emit("Recipe not found.")
            return
        entries = self._collect_entries()
        if not entries:
            self.status_message.emit("Add at least one golden sample.")
            return

        self._run_btn.setEnabled(False)
        self._progress.setValue(0)
        self._progress.setMaximum(len(entries))

        from ...core.recipe_validator import RecipeValidator
        self._worker = _ValidationWorker(RecipeValidator(recipe), entries)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_finished)
        self._worker.start()

    @pyqtSlot(int, int, str)
    def _on_progress(self, done: int, total: int, name: str) -> None:
        self._progress.setValue(done)
        self.status_message.emit(f"Validating [{done}/{total}]: {name}")
        QApplication.processEvents()

    @pyqtSlot(object)
    def _on_finished(self, results: list) -> None:
        self._results = results
        self._run_btn.setEnabled(True)
        self._progress.setValue(self._progress.maximum())
        self._render_results(results)
        from ...core.recipe_validator import RecipeValidator
        stats = RecipeValidator.compute_stats(results)
        self._render_stats(stats)
        self.status_message.emit(
            f"Validation done: {stats.get('n', 0)} OK, {stats.get('n_fail', 0)} failed"
        )

    def _render_stats(self, stats: dict) -> None:
        while self._stats_form.count():
            item = self._stats_form.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()
        if stats.get("n", 0) == 0:
            self._stats_form.addRow(QLabel("No successful results"), QLabel("—"))
            return
        rows = [
            ("N:", str(stats["n"])),
            ("Mean Bias (nm):", f"{stats.get('mean_bias_nm', 0):.4f}"),
            ("Precision (nm):", f"{stats.get('precision_nm', 0):.4f}"),
            ("3-Sigma (nm):", f"{stats.get('3sigma_nm', 0):.4f}"),
            ("Max |Bias| (nm):", f"{stats.get('max_abs_bias_nm', 0):.4f}"),
        ]
        for lbl, val in rows:
            self._stats_form.addRow(QLabel(lbl), QLabel(val))

    def _render_results(self, results: list[ValidationResult]) -> None:
        self._result_table.setRowCount(0)
        for r in results:
            row = self._result_table.rowCount()
            self._result_table.insertRow(row)
            name = Path(r.file_path).name
            meas = f"{r.measured_nm:.3f}" if r.measured_nm is not None else "—"
            bias = f"{r.bias_nm:.3f}" if r.bias_nm is not None else "—"
            status = "OK" if r.success else f"FAIL: {r.error}"
            vals = [name, f"{r.reference_nm:.3f}", meas, bias, status]
            for col, v in enumerate(vals):
                item = QTableWidgetItem(v)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if col == 3 and r.bias_nm is not None:
                    ab = abs(r.bias_nm)
                    if ab < 1.0:
                        item.setBackground(QColor(200, 240, 200))
                    elif ab < 2.0:
                        item.setBackground(QColor(255, 255, 200))
                    else:
                        item.setBackground(QColor(255, 200, 200))
                self._result_table.setItem(row, col, item)

    def _export_csv(self) -> None:
        if not self._results:
            self.status_message.emit("No results to export.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Validation Report", filter="CSV (*.csv)"
        )
        if not path:
            return
        try:
            with open(path, "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(["file_path", "reference_nm", "measured_nm", "bias_nm", "status"])
                for r in self._results:
                    w.writerow([
                        r.file_path,
                        r.reference_nm,
                        r.measured_nm if r.measured_nm is not None else "",
                        r.bias_nm if r.bias_nm is not None else "",
                        "OK" if r.success else r.error,
                    ])
            self.status_message.emit(f"Exported: {Path(path).name}")
        except Exception as exc:
            self.status_message.emit(f"Export error: {exc}")


# ── Worker thread ─────────────────────────────────────────────────────────────

class _ValidationWorker(QThread):
    progress = pyqtSignal(int, int, str)
    finished = pyqtSignal(object)

    def __init__(self, validator, entries: list[GoldenSampleEntry]):
        super().__init__()
        self._validator = validator
        self._entries = entries

    def run(self) -> None:
        results = self._validator.run(
            self._entries,
            on_progress=lambda done, total, name: self.progress.emit(done, total, name),
        )
        self.finished.emit(results)
