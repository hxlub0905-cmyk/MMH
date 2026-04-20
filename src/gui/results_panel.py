"""Bottom results panel: per-structure, per-feature CD measurement table."""

from __future__ import annotations
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QTableWidget, QTableWidgetItem,
    QLabel, QHeaderView, QAbstractItemView, QFrame, QHBoxLayout, QComboBox,
)
from PyQt6.QtGui import QColor
from PyQt6.QtCore import pyqtSignal, Qt
from ..core.cmg_analyzer import CMGCut

_COLUMNS = ["State", "Image", "Structure", "Feature ID", "CD (px)", "CD (nm)", "Axis", "Flag", "Status"]

_ROW_COLOURS = {
    "MIN": QColor(255, 244, 232),
    "MAX": QColor(236, 245, 252),
}
_FLAG_TEXT = {
    "MIN": QColor(210, 122, 52),
    "MAX": QColor(86, 138, 186),
}


class ResultsPanel(QWidget):
    row_selected = pyqtSignal(int, int)   # cmg_id, col_id
    state_filter_changed = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── header bar ────────────────────────────────────────────────────────
        header = QFrame()
        header.setObjectName("resultsHeader")
        hbox = QHBoxLayout(header)
        hbox.setContentsMargins(12, 0, 12, 0)

        self._status_label = QLabel("No results.")
        self._status_label.setStyleSheet("color:#8f7f6b; font-size:11px;")
        hbox.addWidget(self._status_label)
        hbox.addStretch()
        self._state_filter = QComboBox()
        self._state_filter.addItem("All states")
        self._state_filter.currentIndexChanged.connect(self._on_state_filter_changed)
        hbox.addWidget(self._state_filter)

        layout.addWidget(header)

        # ── table ─────────────────────────────────────────────────────────────
        self._table = QTableWidget(0, len(_COLUMNS))
        self._table.setHorizontalHeaderLabels(_COLUMNS)
        self._table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents
        )
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.verticalHeader().setVisible(False)
        self._table.setAlternatingRowColors(True)
        self._table.itemSelectionChanged.connect(self._on_selection)
        layout.addWidget(self._table)
        self._rows: list[dict] = []

    # ── public API ────────────────────────────────────────────────────────────

    def show_results(self, image_name: str, cuts: list[CMGCut]) -> None:
        self._rows = []
        total = sum(len(c.measurements) for c in cuts)
        n_cuts = len(cuts)
        self._status_label.setText(
            f"{image_name}  ·  {n_cuts} structure{'s' if n_cuts != 1 else ''}  ·  "
            f"{total} measurement{'s' if total != 1 else ''}"
        )
        for cut in cuts:
            for m in cut.measurements:
                self._rows.append({
                    "state_name": getattr(m, "state_name", "") or "Default",
                    "image_name": image_name,
                    "structure_name": getattr(m, "structure_name", "") or "—",
                    "feature_id": f"{m.cmg_id}:{m.col_id}",
                    "cd_px": m.cd_px,
                    "cd_nm": m.cd_nm,
                    "axis": getattr(m, "axis", "Y"),
                    "flag": m.flag or "—",
                    "status": "OK",
                })
        self._sync_state_filter()
        self._render_table()

    def show_fail(self, image_name: str, reason: str = "") -> None:
        self._rows = []
        self._status_label.setText(
            f"{image_name}  ·  FAIL{('  — ' + reason) if reason else ''}"
        )
        self._table.insertRow(0)
        fail_vals = ["—", image_name, "—", "—", "—", "—", "—", "—", "FAIL"]
        for col, val in enumerate(fail_vals):
            item = QTableWidgetItem(val)
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item.setForeground(QColor(200, 80, 80))
            self._table.setItem(0, col, item)

    def clear(self) -> None:
        self._rows = []
        self._table.setRowCount(0)
        self._status_label.setText("Select an image and press  ▶ Run Single  to measure.")
        self._state_filter.blockSignals(True)
        self._state_filter.clear()
        self._state_filter.addItem("All states")
        self._state_filter.blockSignals(False)

    def update_summary(self, n_images: int, n_meas: int, n_fail: int) -> None:
        self._status_label.setText(
            f"Batch complete  ·  {n_images} images  ·  {n_meas} measurements  ·  "
            f"{n_fail} failure{'s' if n_fail != 1 else ''}"
        )

    # ── internal ──────────────────────────────────────────────────────────────

    def _on_selection(self) -> None:
        row = self._table.currentRow()
        if row < 0:
            return
        try:
            # Column 3 = feature_id, format "cmg_id:col_id"
            feat = self._table.item(row, 3).text()
            cmg_id, col_id = (int(v) for v in feat.split(":"))
            self.row_selected.emit(cmg_id, col_id)
        except (AttributeError, ValueError):
            pass

    def _sync_state_filter(self) -> None:
        states = sorted({r["state_name"] for r in self._rows})
        cur = self._state_filter.currentText()
        self._state_filter.blockSignals(True)
        self._state_filter.clear()
        self._state_filter.addItem("All states")
        self._state_filter.addItems(states)
        idx = self._state_filter.findText(cur)
        self._state_filter.setCurrentIndex(max(0, idx))
        self._state_filter.blockSignals(False)

    def _render_table(self) -> None:
        sel = self._state_filter.currentText()
        rows = self._rows if sel == "All states" else [r for r in self._rows if r["state_name"] == sel]
        self._table.setRowCount(0)
        for r in rows:
            row = self._table.rowCount()
            self._table.insertRow(row)
            values = [
                r["state_name"], r["image_name"], r["structure_name"], r["feature_id"],
                f"{r['cd_px']:.1f}", f"{r['cd_nm']:.2f}", r["axis"], r["flag"], r["status"],
            ]
            bg = _ROW_COLOURS.get(r["flag"])
            for col, val in enumerate(values):
                item = QTableWidgetItem(val)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if bg:
                    item.setBackground(bg)
                if col == 7 and r["flag"] in _FLAG_TEXT:
                    item.setForeground(_FLAG_TEXT[r["flag"]])
                self._table.setItem(row, col, item)

    def _on_state_filter_changed(self) -> None:
        self._render_table()
        txt = self._state_filter.currentText()
        self.state_filter_changed.emit("" if txt == "All states" else txt)
