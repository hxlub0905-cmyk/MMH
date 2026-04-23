"""Compare-to-Reference dialog for Measure workspace."""
from __future__ import annotations

import csv
import math
import statistics
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..core.models import MeasurementRecord
from ..core.batch_run_store import BatchRunStore


# ── Colour helpers ─────────────────────────────────────────────────────────────

_RED  = QColor(200, 60, 60)
_BLUE = QColor(50, 100, 200)
_GRAY = QColor(140, 130, 120)


def _bias_color(bias: float) -> QColor:
    if bias > 0:
        return _RED
    if bias < 0:
        return _BLUE
    return _GRAY


# ── History picker sub-dialog ──────────────────────────────────────────────────

class _RefHistoryPickerDialog(QDialog):
    """Pick a historical batch run; returns its measurement records as reference."""

    def __init__(self, run_store: BatchRunStore, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Select Reference Run")
        self.setMinimumSize(680, 360)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Select the batch run whose measurements will be used as Reference CD values:"))

        self._table = QTableWidget(0, 5)
        self._table.setHorizontalHeaderLabels(["Type", "Start Time", "Total", "OK", "Folder / Label"])
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.doubleClicked.connect(self._load)
        layout.addWidget(self._table)

        btn_row = QHBoxLayout()
        load_btn  = QPushButton("Load Selected")
        close_btn = QPushButton("Cancel")
        load_btn.clicked.connect(self._load)
        close_btn.clicked.connect(self.reject)
        btn_row.addStretch()
        btn_row.addWidget(load_btn)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

        self._run_store = run_store
        self._summaries: list[dict] = []
        self._records: list[MeasurementRecord] = []
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
        batch = self._run_store.load(self._summaries[row]["file_path"])
        self._records = self._extract_records(batch)
        self.accept()

    def selected_records(self) -> list[MeasurementRecord]:
        return self._records

    @staticmethod
    def _extract_records(batch) -> list[MeasurementRecord]:
        records: list[MeasurementRecord] = []
        manifest = getattr(batch, "output_manifest", None) or {}
        for result in manifest.get("results", []):
            for m_dict in result.get("measurements", []):
                try:
                    r = MeasurementRecord.from_dict(m_dict)
                    if r.status != "rejected":
                        records.append(r)
                except Exception:
                    pass
        return records


# ── Main dialog ────────────────────────────────────────────────────────────────

_COL_POS  = 0
_COL_MEAS = 1
_COL_REF  = 2
_COL_BIAS = 3


class MeasureValidateDialog(QDialog):
    """Per-position compare-to-reference dialog."""

    def __init__(
        self,
        records: list[MeasurementRecord],
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Compare to Reference")
        self.setMinimumSize(820, 480)

        self._records = records
        self._run_store = BatchRunStore()
        # (cmg_id, col_id) → reference_nm; NaN means not set
        self._ref_values: dict[tuple[int, int], float] = {}

        self._build_ui()
        self._refresh_table()

    # ── UI construction ────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        # Top bar: load-from-history button
        top = QHBoxLayout()
        self._btn_load_hist = QPushButton("Load Reference from History…")
        self._btn_load_hist.setToolTip(
            "Populate Ref.(nm) column from a previously saved batch run"
        )
        self._btn_load_hist.clicked.connect(self._load_from_history)
        top.addWidget(self._btn_load_hist)
        top.addStretch()
        root.addLayout(top)

        # Main splitter
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)

        # Left: table
        left = QWidget()
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 0, 0)
        lv.setSpacing(4)
        lv.addWidget(QLabel("Ref.(nm) column is editable — click a cell to enter a value:"))

        self._table = QTableWidget(0, 4)
        self._table.setHorizontalHeaderLabels(
            ["Position", "Meas.(nm)", "Ref.(nm)", "Bias(nm)"]
        )
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._table.cellChanged.connect(self._on_ref_edited)
        lv.addWidget(self._table)
        splitter.addWidget(left)

        # Right: summary + buttons
        right = QWidget()
        right.setFixedWidth(210)
        rv = QVBoxLayout(right)
        rv.setContentsMargins(8, 0, 0, 0)
        rv.setSpacing(6)

        summary_box = QGroupBox("Overall Summary")
        sv = QVBoxLayout(summary_box)
        sv.setSpacing(3)

        def _lbl() -> QLabel:
            l = QLabel("—")
            l.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            return l

        self._lbl_n         = _lbl()
        self._lbl_mean_meas = _lbl()
        self._lbl_mean_ref  = _lbl()
        self._lbl_mean_bias = _lbl()
        self._lbl_std_bias  = _lbl()
        self._lbl_min_bias  = _lbl()
        self._lbl_max_bias  = _lbl()

        for label, widget in [
            ("N:",          self._lbl_n),
            ("Mean Meas:",  self._lbl_mean_meas),
            ("Mean Ref:",   self._lbl_mean_ref),
            ("Mean Bias:",  self._lbl_mean_bias),
            ("Std Bias:",   self._lbl_std_bias),
            ("Min Bias:",   self._lbl_min_bias),
            ("Max Bias:",   self._lbl_max_bias),
        ]:
            row = QHBoxLayout()
            lbl = QLabel(label)
            lbl.setFixedWidth(80)
            row.addWidget(lbl)
            row.addWidget(widget)
            sv.addLayout(row)

        rv.addWidget(summary_box)
        rv.addStretch()

        btn_export = QPushButton("Export CSV…")
        btn_export.clicked.connect(self._export_csv)
        btn_close  = QPushButton("Close")
        btn_close.clicked.connect(self.reject)
        rv.addWidget(btn_export)
        rv.addWidget(btn_close)

        splitter.addWidget(right)
        splitter.setSizes([600, 210])
        root.addWidget(splitter)

    # ── Table population ───────────────────────────────────────────────────────

    def _refresh_table(self) -> None:
        self._table.blockSignals(True)
        self._table.setRowCount(0)
        for r in self._records:
            row = self._table.rowCount()
            self._table.insertRow(row)

            key = (r.cmg_id, r.col_id)
            ref = self._ref_values.get(key, math.nan)
            bias = r.calibrated_nm - ref if not math.isnan(ref) else math.nan

            pos_item = QTableWidgetItem(f"CMG{r.cmg_id}-C{r.col_id}")
            pos_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)

            meas_item = QTableWidgetItem(f"{r.calibrated_nm:.3f}")
            meas_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            meas_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            ref_item = QTableWidgetItem("" if math.isnan(ref) else f"{ref:.3f}")
            ref_item.setFlags(
                Qt.ItemFlag.ItemIsEnabled
                | Qt.ItemFlag.ItemIsSelectable
                | Qt.ItemFlag.ItemIsEditable
            )
            ref_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            bias_item = QTableWidgetItem("" if math.isnan(bias) else f"{bias:+.3f}")
            bias_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            bias_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if not math.isnan(bias):
                bias_item.setForeground(_bias_color(bias))

            self._table.setItem(row, _COL_POS,  pos_item)
            self._table.setItem(row, _COL_MEAS, meas_item)
            self._table.setItem(row, _COL_REF,  ref_item)
            self._table.setItem(row, _COL_BIAS, bias_item)

        self._table.blockSignals(False)
        self._refresh_stats()

    def _on_ref_edited(self, row: int, col: int) -> None:
        if col != _COL_REF:
            return
        item = self._table.item(row, _COL_REF)
        text = (item.text() if item else "").strip()
        if row >= len(self._records):
            return
        r = self._records[row]
        key = (r.cmg_id, r.col_id)
        try:
            val = float(text)
            self._ref_values[key] = val
        except ValueError:
            self._ref_values.pop(key, None)

        # Update bias cell for this row
        ref = self._ref_values.get(key, math.nan)
        bias = r.calibrated_nm - ref if not math.isnan(ref) else math.nan

        self._table.blockSignals(True)
        bias_item = self._table.item(row, _COL_BIAS)
        if bias_item is None:
            bias_item = QTableWidgetItem()
            bias_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            bias_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self._table.setItem(row, _COL_BIAS, bias_item)
        bias_item.setText("" if math.isnan(bias) else f"{bias:+.3f}")
        if not math.isnan(bias):
            bias_item.setForeground(_bias_color(bias))
        self._table.blockSignals(False)

        self._refresh_stats()

    # ── Summary stats ──────────────────────────────────────────────────────────

    def _refresh_stats(self) -> None:
        meas_vals = [r.calibrated_nm for r in self._records]
        biases: list[float] = []
        ref_vals: list[float] = []
        for r in self._records:
            key = (r.cmg_id, r.col_id)
            ref = self._ref_values.get(key, math.nan)
            if not math.isnan(ref):
                biases.append(r.calibrated_nm - ref)
                ref_vals.append(ref)

        n = len(self._records)
        self._lbl_n.setText(f"{len(biases)} / {n}")
        self._lbl_n.setToolTip("有輸入參考值的筆數 / 總量測筆數")

        if meas_vals:
            self._lbl_mean_meas.setText(f"{statistics.mean(meas_vals):.3f} nm")
        else:
            self._lbl_mean_meas.setText("—")

        if ref_vals:
            self._lbl_mean_ref.setText(f"{statistics.mean(ref_vals):.3f} nm")
        else:
            self._lbl_mean_ref.setText("—")

        if biases:
            mean_b = statistics.mean(biases)
            self._lbl_mean_bias.setText(f"{mean_b:+.3f} nm")
            self._lbl_min_bias.setText(f"{min(biases):+.3f} nm")
            self._lbl_max_bias.setText(f"{max(biases):+.3f} nm")
            if len(biases) > 1:
                self._lbl_std_bias.setText(f"{statistics.stdev(biases):.3f} nm")
            else:
                self._lbl_std_bias.setText("N/A (n=1)")
        else:
            for lbl in (self._lbl_mean_bias, self._lbl_std_bias,
                        self._lbl_min_bias, self._lbl_max_bias):
                lbl.setText("—")

    # ── Load from history ──────────────────────────────────────────────────────

    def _load_from_history(self) -> None:
        dlg = _RefHistoryPickerDialog(self._run_store, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            ref_records = dlg.selected_records()
            self._ref_values = {
                (r.cmg_id, r.col_id): float(r.calibrated_nm)
                for r in ref_records
            }
            self._refresh_table()

    # ── Export CSV ─────────────────────────────────────────────────────────────

    def _export_csv(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Export CSV", "", "CSV Files (*.csv)"
        )
        if not path:
            return
        if not path.lower().endswith(".csv"):
            path += ".csv"

        biases: list[float] = []
        rows: list[list[str]] = []
        for r in self._records:
            key = (r.cmg_id, r.col_id)
            ref = self._ref_values.get(key, math.nan)
            bias = r.calibrated_nm - ref if not math.isnan(ref) else math.nan
            if not math.isnan(bias):
                biases.append(bias)
            rows.append([
                f"CMG{r.cmg_id}-C{r.col_id}",
                f"{r.calibrated_nm:.4f}",
                "" if math.isnan(ref) else f"{ref:.4f}",
                "" if math.isnan(bias) else f"{bias:+.4f}",
            ])

        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["position", "measured_nm", "reference_nm", "bias_nm"])
            writer.writerows(rows)
            writer.writerow([])
            writer.writerow(["# summary"])
            writer.writerow(["n_with_ref", str(len(biases))])
            writer.writerow(["n_total",    str(len(self._records))])
            if biases:
                writer.writerow(["mean_bias_nm", f"{statistics.mean(biases):.4f}"])
                writer.writerow(["min_bias_nm",  f"{min(biases):.4f}"])
                writer.writerow(["max_bias_nm",  f"{max(biases):.4f}"])
                if len(biases) > 1:
                    writer.writerow(["std_bias_nm", f"{statistics.stdev(biases):.4f}"])
