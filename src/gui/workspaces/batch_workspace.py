"""Batch workspace — folder-level batch processing with multi-dataset support."""
from __future__ import annotations

import os
import time
from pathlib import Path
from typing import NamedTuple

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QGroupBox, QLabel, QPushButton, QCheckBox,
    QComboBox, QSpinBox, QProgressBar, QTextEdit,
    QListWidget, QListWidgetItem, QFileDialog,
    QMessageBox, QLineEdit, QScrollArea, QSizePolicy,
    QFrame, QDialog, QTableWidget, QTableWidgetItem, QAbstractItemView,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, pyqtSlot

from ...core.models import ImageRecord, BatchRunRecord, MultiDatasetBatchRun
from ...core.recipe_registry import RecipeRegistry
from ...core.measurement_engine import MeasurementEngine
from ...core.calibration import CalibrationManager
from ...core.batch_run_store import BatchRunStore
from ...core.image_loader import scan_folder


class _DatasetRow(NamedTuple):
    label_edit:   QLineEdit
    folder_label: QLabel
    recipe_combo: QComboBox
    remove_btn:   QPushButton
    container:    QWidget
    folder_btn:   QPushButton
    folder_ref:   list  # [str] mutable slot for folder path


class BatchWorkspace(QWidget):
    batch_completed       = pyqtSignal(object)  # BatchRunRecord  (single dataset)
    multi_batch_completed = pyqtSignal(object)  # MultiDatasetBatchRun (multi)
    status_message        = pyqtSignal(str)

    def __init__(
        self,
        engine: MeasurementEngine,
        registry: RecipeRegistry,
        cal_manager: CalibrationManager,
        run_store: BatchRunStore | None = None,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self._engine        = engine
        self._registry      = registry
        self._cal_manager   = cal_manager
        self._run_store     = run_store
        self._worker        = None
        self._save_worker   = None
        self._dataset_rows: list[_DatasetRow] = []
        self._progress_count    = 0
        self._batch_start_time: float | None = None
        self._THROTTLE = 50    # update log/list every N images
        self._LIST_CAP = 500   # max QListWidget items (keeps most recent)
        self._overlay_output_dir: str = ""
        self._build_ui()
        self._add_dataset_row()   # start with one empty row

    # ── Construction ──────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        # ── Dataset table ──────────────────────────────────────────────────────
        ds_box = QGroupBox("Datasets")
        ds_vbox = QVBoxLayout(ds_box)
        ds_vbox.setContentsMargins(6, 8, 6, 6)
        ds_vbox.setSpacing(4)

        # Column headers
        hdr = QWidget()
        hdr_row = QHBoxLayout(hdr)
        hdr_row.setContentsMargins(0, 0, 0, 0)
        hdr_row.setSpacing(4)
        for text, stretch in [("Label", 2), ("Folder", 4), ("Recipe", 3), ("", 1)]:
            lbl = QLabel(text)
            lbl.setStyleSheet("color:#888; font-size:10px; font-weight:bold;")
            hdr_row.addWidget(lbl, stretch)
        ds_vbox.addWidget(hdr)

        sep = QFrame(); sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color:#3a3a3a;")
        ds_vbox.addWidget(sep)

        # Scroll area for rows
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setMinimumHeight(120)
        scroll.setMaximumHeight(340)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._rows_container = QWidget()
        self._rows_layout = QVBoxLayout(self._rows_container)
        self._rows_layout.setContentsMargins(0, 0, 0, 0)
        self._rows_layout.setSpacing(2)
        self._rows_layout.addStretch()
        scroll.setWidget(self._rows_container)
        ds_vbox.addWidget(scroll)

        add_btn = QPushButton("+ Add Dataset")
        add_btn.setFixedWidth(120)
        add_btn.clicked.connect(self._add_dataset_row)
        ds_vbox.addWidget(add_btn, alignment=Qt.AlignmentFlag.AlignLeft)

        root.addWidget(ds_box)

        # ── Workers + Run ─────────────────────────────────────────────────────
        ctrl_row = QHBoxLayout()
        self._worker_spin = QSpinBox()
        self._worker_spin.setRange(1, os.cpu_count() or 4)
        self._worker_spin.setValue(max(1, (os.cpu_count() or 2) - 1))
        ctrl_row.addWidget(QLabel("Workers:"))
        ctrl_row.addWidget(self._worker_spin)
        ctrl_row.addStretch()
        run_btn = QPushButton("Run Batch")
        run_btn.setFixedWidth(120)
        run_btn.clicked.connect(self._run_batch)
        ctrl_row.addWidget(run_btn)
        root.addLayout(ctrl_row)

        # ── Overlay 選項列 ────────────────────────────────────────────────────
        self._chk_overlay = QCheckBox("邊跑邊輸出 Overlay Image")
        self._chk_overlay.setChecked(False)
        self._chk_overlay.stateChanged.connect(self._on_overlay_toggled)

        self._overlay_folder_btn = QPushButton("選擇輸出資料夾…")
        self._overlay_folder_btn.setEnabled(False)
        self._overlay_folder_btn.clicked.connect(self._browse_overlay_folder)

        self._overlay_folder_label = QLabel("（未選擇）")
        self._overlay_folder_label.setStyleSheet("color:#9f8f7b; font-size:11px;")

        overlay_row = QHBoxLayout()
        overlay_row.addWidget(self._chk_overlay)
        overlay_row.addWidget(self._overlay_folder_btn)
        overlay_row.addWidget(self._overlay_folder_label, stretch=1)
        root.addLayout(overlay_row)

        # ── Progress ──────────────────────────────────────────────────────────
        prog_box = QGroupBox("Progress")
        pv = QVBoxLayout(prog_box)
        self._progress = QProgressBar()
        self._progress.setTextVisible(True)
        pv.addWidget(self._progress)
        self._lbl_eta = QLabel("ETA: —")
        self._lbl_eta.setStyleSheet("color:#aaa; font-size:11px;")
        pv.addWidget(self._lbl_eta)
        self._log_text = QTextEdit()
        self._log_text.setReadOnly(True)
        self._log_text.setMaximumHeight(120)
        pv.addWidget(self._log_text)
        hist_btn = QPushButton("Load History…")
        hist_btn.setFixedWidth(130)
        hist_btn.clicked.connect(self._open_history_dialog)
        pv.addWidget(hist_btn, alignment=Qt.AlignmentFlag.AlignLeft)
        root.addWidget(prog_box)

        # ── Results list ──────────────────────────────────────────────────────
        results_box = QGroupBox("Image Results")
        rv = QVBoxLayout(results_box)
        self._image_list = QListWidget()
        rv.addWidget(self._image_list)
        root.addWidget(results_box, stretch=1)

    # ── Dataset row management ────────────────────────────────────────────────

    def _add_dataset_row(self) -> None:
        idx = len(self._dataset_rows)
        folder_ref: list = [""]

        container = QWidget()
        row_layout = QHBoxLayout(container)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(4)

        label_edit = QLineEdit(f"Dataset {idx + 1}")
        label_edit.setFixedWidth(90)

        folder_label = QLabel("(no folder)")
        folder_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        folder_label.setStyleSheet("color:#aaa; font-size:11px;")

        folder_btn = QPushButton("…")
        folder_btn.setFixedWidth(28)

        recipe_combo = QComboBox()
        recipe_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._populate_recipe_combo(recipe_combo)

        remove_btn = QPushButton("✕")
        remove_btn.setFixedWidth(28)

        row_layout.addWidget(label_edit, 2)
        row_layout.addWidget(folder_label, 4)
        row_layout.addWidget(folder_btn, 0)
        row_layout.addWidget(recipe_combo, 3)
        row_layout.addWidget(remove_btn, 0)

        dr = _DatasetRow(
            label_edit=label_edit,
            folder_label=folder_label,
            recipe_combo=recipe_combo,
            remove_btn=remove_btn,
            container=container,
            folder_btn=folder_btn,
            folder_ref=folder_ref,
        )
        self._dataset_rows.append(dr)

        folder_btn.clicked.connect(lambda _, r=dr: self._browse_folder(r))
        remove_btn.clicked.connect(lambda _, r=dr: self._remove_dataset_row(r))

        # Insert before the stretch item at the end
        self._rows_layout.insertWidget(self._rows_layout.count() - 1, container)

    def _remove_dataset_row(self, row: _DatasetRow) -> None:
        if len(self._dataset_rows) <= 1:
            QMessageBox.information(self, "Cannot remove", "At least one dataset row is required.")
            return
        self._dataset_rows.remove(row)
        row.container.setParent(None)
        row.container.deleteLater()

    def _browse_folder(self, row: _DatasetRow) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Select Input Folder")
        if folder:
            row.folder_ref[0] = folder
            name = Path(folder).name
            row.folder_label.setText(name)
            row.folder_label.setToolTip(folder)
            row.folder_label.setStyleSheet("color:#ccc; font-size:11px;")

    def _populate_recipe_combo(self, combo: QComboBox) -> None:
        combo.blockSignals(True)
        combo.clear()
        for desc in self._registry.list_recipes():
            combo.addItem(f"{desc.recipe_name}  [{desc.recipe_type}]", desc.recipe_id)
        if combo.count() == 0:
            combo.addItem("(no recipes saved)", None)
        combo.blockSignals(False)

    # ── Public API ────────────────────────────────────────────────────────────

    def refresh_recipe_selector(self, _recipe=None) -> None:
        for dr in self._dataset_rows:
            cur_id = dr.recipe_combo.currentData()
            self._populate_recipe_combo(dr.recipe_combo)
            # Restore previously selected recipe if still present
            if cur_id:
                for i in range(dr.recipe_combo.count()):
                    if dr.recipe_combo.itemData(i) == cur_id:
                        dr.recipe_combo.setCurrentIndex(i)
                        break

    # ── Overlay 設定 ──────────────────────────────────────────────────────────

    def _on_overlay_toggled(self, state: int) -> None:
        self._overlay_folder_btn.setEnabled(bool(state))
        if not state:
            self._overlay_output_dir = ""
            self._overlay_folder_label.setText("（未選擇）")

    def _browse_overlay_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "選擇 Overlay 輸出資料夾")
        if folder:
            self._overlay_output_dir = folder
            self._overlay_folder_label.setText(Path(folder).name)
            self._overlay_folder_label.setToolTip(folder)

    # ── Batch execution ───────────────────────────────────────────────────────

    def _run_batch(self) -> None:
        cal = self._cal_manager.get_default()

        valid_rows = []
        for dr in self._dataset_rows:
            folder = dr.folder_ref[0]
            recipe_id = dr.recipe_combo.currentData()
            if not folder or not Path(folder).is_dir():
                continue
            if not recipe_id:
                continue
            paths = scan_folder(folder)
            if not paths:
                self._log_text.append(f"[WARN] No images in: {folder}")
                continue
            valid_rows.append({
                "label": dr.label_edit.text().strip() or f"Dataset {len(valid_rows)+1}",
                "folder": folder,
                "recipe_ids": [recipe_id],
                "image_records": [
                    ImageRecord.from_path(p, pixel_size_nm=cal.nm_per_pixel) for p in paths
                ],
            })

        if not valid_rows:
            QMessageBox.warning(self, "No data",
                                "Add at least one dataset row with a valid folder and recipe.")
            return

        self._log_text.clear()
        self._image_list.clear()
        self._progress_count = 0
        self._batch_start_time = time.monotonic()
        self._lbl_eta.setText("ETA: —")
        total_images = sum(len(r["image_records"]) for r in valid_rows)
        self._progress.setMaximum(total_images)
        self._progress.setValue(0)

        output_dir = (
            Path(self._overlay_output_dir)
            if self._chk_overlay.isChecked() and self._overlay_output_dir
            else None
        )

        if len(valid_rows) == 1:
            # Single-dataset path — backward compatible
            r = valid_rows[0]
            self._worker = _BatchWorker(
                engine=self._engine,
                image_records=r["image_records"],
                recipe_ids=r["recipe_ids"],
                max_workers=self._worker_spin.value(),
                output_dir=output_dir,
            )
            self._worker.progress.connect(self._on_progress)
            self._worker.finished.connect(self._on_single_finished)
            self._worker.error.connect(self._on_batch_error)
            self._worker.start()
            self.status_message.emit(f"Batch started — {total_images} images")
        else:
            # Multi-dataset path
            self._worker = _MultiBatchWorker(
                engine=self._engine,
                datasets=valid_rows,
                max_workers=self._worker_spin.value(),
                output_dir=output_dir,
            )
            self._worker.dataset_started.connect(self._on_dataset_started)
            self._worker.progress.connect(self._on_progress)
            self._worker.finished.connect(self._on_multi_finished)
            self._worker.error.connect(self._on_batch_error)
            self._worker.start()
            self.status_message.emit(
                f"Multi-batch started — {len(valid_rows)} datasets, {total_images} images"
            )

    @pyqtSlot(int, int, str)
    def _on_dataset_started(self, current: int, total: int, label: str) -> None:
        self._log_text.append(f"\n=== Dataset {current}/{total}: {label} ===")

    @pyqtSlot(int, int, str, str, object)
    def _on_progress(self, done: int, total: int, name: str, status: str,
                     result_dict: object = None) -> None:
        self._progress_count += 1
        self._progress.setValue(done)

        # ETA — always recalculate (cheap)
        if done > 0 and self._batch_start_time is not None:
            elapsed = time.monotonic() - self._batch_start_time
            rate = done / elapsed
            remaining = (total - done) / rate if rate > 0 else 0
            mins, secs = divmod(int(remaining), 60)
            self._lbl_eta.setText(f"ETA: {mins}m {secs:02d}s  ({rate:.1f} img/s)")

        # Throttle heavy UI updates — only on first, every THROTTLE-th, failures, or last
        if self._progress_count % self._THROTTLE == 1 or status != "OK" or done == total:
            self._log_text.append(f"[{done}/{total}] {name}  [{status}]")
            item = QListWidgetItem(f"[{status}]  {name}")
            item.setForeground(Qt.GlobalColor.red if status != "OK" else Qt.GlobalColor.darkGreen)
            if self._image_list.count() >= self._LIST_CAP:
                self._image_list.takeItem(0)
            self._image_list.addItem(item)

        if isinstance(result_dict, dict):
            if result_dict.get("overlay_path"):
                self._log_text.append(
                    f"  → overlay: {Path(result_dict['overlay_path']).name}"
                )
            if result_dict.get("overlay_error"):
                self._log_text.append(
                    f"  → overlay error: {result_dict['overlay_error']}"
                )

    @pyqtSlot(object)
    def _on_single_finished(self, batch_run: BatchRunRecord) -> None:
        self._progress.setValue(self._progress.maximum())
        self._lbl_eta.setText("ETA: done")
        msg = (f"Batch complete  ·  {batch_run.success_count} OK  "
               f"·  {batch_run.fail_count} failed  —  Results sent to Review tab")
        self._log_text.append(msg)
        self.batch_completed.emit(batch_run)   # send to Report tab immediately
        if self._run_store:
            self._log_text.append("Saving results…")
            self.status_message.emit(msg + "  (saving…)")
            self._save_worker = _SaveWorker(self._run_store, batch_run, multi=False)
            self._save_worker.save_done.connect(
                lambda p: self.status_message.emit(f"Results saved → {Path(p).name}")
            )
            self._save_worker.save_done.connect(
                lambda p: self._log_text.append(f"Saved → {Path(p).name}")
            )
            self._save_worker.save_error.connect(
                lambda e: self.status_message.emit(f"Save error: {e}")
            )
            self._save_worker.start()
        else:
            self.status_message.emit(msg)

    @pyqtSlot(object)
    def _on_multi_finished(self, mbr: MultiDatasetBatchRun) -> None:
        self._progress.setValue(self._progress.maximum())
        self._lbl_eta.setText("ETA: done")
        msg = (f"Multi-batch complete  ·  {mbr.success_count} OK  "
               f"·  {mbr.fail_count} failed across {len(mbr.datasets)} datasets"
               f"  —  Results sent to Report tab")
        self._log_text.append(msg)
        self.multi_batch_completed.emit(mbr)   # send to Report tab immediately
        if self._run_store:
            self._log_text.append("Saving results…")
            self.status_message.emit(msg + "  (saving…)")
            self._save_worker = _SaveWorker(self._run_store, mbr, multi=True)
            self._save_worker.save_done.connect(
                lambda p: self.status_message.emit(f"Results saved → {Path(p).name}")
            )
            self._save_worker.save_done.connect(
                lambda p: self._log_text.append(f"Saved → {Path(p).name}")
            )
            self._save_worker.save_error.connect(
                lambda e: self.status_message.emit(f"Save error: {e}")
            )
            self._save_worker.start()
        else:
            self.status_message.emit(msg)

    def _open_history_dialog(self) -> None:
        if not self._run_store:
            return
        dlg = _HistoryDialog(self._run_store, self)
        dlg.run_selected.connect(self._on_history_selected)
        dlg.exec()

    def _on_history_selected(self, file_path: str) -> None:
        if not self._run_store:
            return
        try:
            result = self._run_store.load(file_path)
        except Exception as exc:
            self.status_message.emit(f"Failed to load history: {exc}")
            return
        from ...core.models import MultiDatasetBatchRun
        if isinstance(result, MultiDatasetBatchRun):
            self.multi_batch_completed.emit(result)
        else:
            self.batch_completed.emit(result)

    @pyqtSlot(str)
    def _on_batch_error(self, err: str) -> None:
        self._log_text.append(f"ERROR: {err}")
        self.status_message.emit(f"Batch error: {err}")


# ── Worker threads ─────────────────────────────────────────────────────────────

class _BatchWorker(QThread):
    progress = pyqtSignal(int, int, str, str, object)  # done, total, name, status, result_dict
    finished = pyqtSignal(object)                      # BatchRunRecord
    error    = pyqtSignal(str)

    def __init__(
        self,
        engine: MeasurementEngine,
        image_records: list[ImageRecord],
        recipe_ids: list[str],
        max_workers: int,
        output_dir: Path | None = None,
    ):
        super().__init__()
        self._engine        = engine
        self._image_records = image_records
        self._recipe_ids    = recipe_ids
        self._max_workers   = max_workers
        self._output_dir    = output_dir

    def run(self) -> None:
        try:
            batch_run = self._engine.run_batch(
                image_records=self._image_records,
                recipe_ids=self._recipe_ids,
                on_progress=lambda done, total, name, status, result_dict:
                    self.progress.emit(done, total, name, status, result_dict),
                max_workers=self._max_workers,
                output_dir=self._output_dir,
            )
            self.finished.emit(batch_run)
        except Exception as exc:
            self.error.emit(str(exc))


class _MultiBatchWorker(QThread):
    dataset_started = pyqtSignal(int, int, str)           # current_idx, total, label
    progress        = pyqtSignal(int, int, str, str, object)  # done, total, name, status, result_dict
    finished        = pyqtSignal(object)                  # MultiDatasetBatchRun
    error           = pyqtSignal(str)

    def __init__(
        self,
        engine: MeasurementEngine,
        datasets: list[dict],
        max_workers: int,
        output_dir: Path | None = None,
    ):
        super().__init__()
        self._engine      = engine
        self._datasets    = datasets
        self._max_workers = max_workers
        self._output_dir  = output_dir

    def run(self) -> None:
        try:
            mbr = self._engine.run_multi_batch(
                datasets=self._datasets,
                on_dataset_start=lambda cur, tot, lbl:
                    self.dataset_started.emit(cur, tot, lbl),
                on_progress=lambda done, total, name, status, result_dict:
                    self.progress.emit(done, total, name, status, result_dict),
                max_workers=self._max_workers,
                output_dir=self._output_dir,
            )
            self.finished.emit(mbr)
        except Exception as exc:
            self.error.emit(str(exc))


# ── History dialog ─────────────────────────────────────────────────────────────

class _HistoryDialog(QDialog):
    """歷史批次結果選擇器。"""
    run_selected = pyqtSignal(str)   # file_path

    def __init__(self, run_store: BatchRunStore, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Batch Run History")
        self.setMinimumSize(680, 400)
        layout = QVBoxLayout(self)

        self._table = QTableWidget(0, 6)
        self._table.setHorizontalHeaderLabels(
            ["Type", "Start Time", "Total", "OK", "Failed", "Folder / Label"]
        )
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        layout.addWidget(self._table)

        btn_row = QHBoxLayout()
        load_btn  = QPushButton("Load Selected")
        del_btn   = QPushButton("Delete")
        close_btn = QPushButton("Close")
        load_btn.clicked.connect(self._load)
        del_btn.clicked.connect(self._delete)
        close_btn.clicked.connect(self.reject)
        btn_row.addStretch()
        btn_row.addWidget(load_btn)
        btn_row.addWidget(del_btn)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

        self._run_store = run_store
        self._summaries: list[dict] = []
        self._refresh()

    def _refresh(self) -> None:
        self._summaries = self._run_store.list_runs()
        self._table.setRowCount(0)
        for s in self._summaries:
            row = self._table.rowCount()
            self._table.insertRow(row)
            vals = [
                s.get("type", "single"),
                s.get("start_time", "")[:19].replace("T", " "),
                str(s.get("total_images", 0)),
                str(s.get("success_count", 0)),
                str(s.get("fail_count", 0)),
                s.get("input_folder") or s.get("dataset_label", ""),
            ]
            for col, v in enumerate(vals):
                item = QTableWidgetItem(v)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self._table.setItem(row, col, item)

    def _load(self) -> None:
        row = self._table.currentRow()
        if row < 0:
            return
        self.run_selected.emit(self._summaries[row]["file_path"])
        self.accept()

    def _delete(self) -> None:
        row = self._table.currentRow()
        if row < 0:
            return
        self._run_store.delete(self._summaries[row]["file_path"])
        self._refresh()


# ── Background save worker ─────────────────────────────────────────────────────

class _SaveWorker(QThread):
    """Serialize and persist a BatchRunRecord / MultiDatasetBatchRun off the main thread."""
    save_done  = pyqtSignal(str)   # file path
    save_error = pyqtSignal(str)

    def __init__(self, run_store, batch_run, *, multi: bool = False):
        super().__init__()
        self._store     = run_store
        self._batch_run = batch_run
        self._multi     = multi

    def run(self) -> None:
        try:
            if self._multi:
                path = self._store.save_multi(self._batch_run)
            else:
                path = self._store.save(self._batch_run)
            self.save_done.emit(str(path))
        except Exception as exc:
            self.save_error.emit(str(exc))
