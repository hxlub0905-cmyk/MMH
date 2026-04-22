"""HistoryWorkspace — 歷史批次趨勢 Run Chart。"""
from __future__ import annotations

from io import BytesIO

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox,
    QLabel, QPushButton, QComboBox, QTableWidget, QTableWidgetItem,
    QAbstractItemView, QScrollArea, QSizePolicy,
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QPixmap

from ...core.batch_run_store import BatchRunStore


class HistoryWorkspace(QWidget):
    status_message = pyqtSignal(str)
    load_requested = pyqtSignal(str)   # file_path

    def __init__(self, run_store: BatchRunStore, parent: QWidget | None = None):
        super().__init__(parent)
        self._run_store = run_store
        self._summaries: list[dict] = []
        self._first_shown = False
        self._build_ui()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if not self._first_shown:
            self._first_shown = True
            self._refresh()

    # ── Construction ──────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        # ── Filter row ─────────────────────────────────────────────────────────
        filter_box = QGroupBox("Filter")
        fh = QHBoxLayout(filter_box)
        fh.addWidget(QLabel("Recipe:"))
        self._recipe_combo = QComboBox()
        self._recipe_combo.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        fh.addWidget(self._recipe_combo, 1)
        fh.addWidget(QLabel("Time range:"))
        self._time_combo = QComboBox()
        self._time_combo.addItems(
            ["Last 7 days", "Last 30 days", "Last 90 days", "All"]
        )
        self._time_combo.setCurrentText("All")
        fh.addWidget(self._time_combo)
        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self._refresh)
        fh.addWidget(refresh_btn)
        root.addWidget(filter_box)

        # ── Run Chart ──────────────────────────────────────────────────────────
        chart_box = QGroupBox("Run Chart — CD Mean Trend")
        cv = QVBoxLayout(chart_box)
        self._chart_label = QLabel("Press Refresh to generate chart.")
        self._chart_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._chart_label.setMinimumHeight(220)
        self._chart_label.setStyleSheet("color:#888; background:#1e1e1e;")
        cv.addWidget(self._chart_label)
        root.addWidget(chart_box)

        # ── Batch list ──────────────────────────────────────────────────────────
        list_box = QGroupBox("Batch Runs")
        lv = QVBoxLayout(list_box)
        self._batch_table = QTableWidget(0, 8)
        self._batch_table.setHorizontalHeaderLabels(
            ["Date", "Type", "Images", "OK", "Failed",
             "Mean CD (nm)", "Std (nm)", "Folder"]
        )
        self._batch_table.horizontalHeader().setStretchLastSection(True)
        self._batch_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._batch_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._batch_table.doubleClicked.connect(self._on_row_double_clicked)
        lv.addWidget(self._batch_table)
        load_btn = QPushButton("Load Selected in Report Tab")
        load_btn.clicked.connect(self._on_load_selected)
        lv.addWidget(load_btn, alignment=Qt.AlignmentFlag.AlignLeft)
        root.addWidget(list_box, stretch=1)

        # _refresh() is NOT called here — deferred to first showEvent

    # ── Public / Internal ─────────────────────────────────────────────────────

    def _refresh(self) -> None:
        recipe_id: str | None = self._recipe_combo.currentData() or None

        # list_runs() called ONCE; result shared with all downstream methods
        all_summaries = self._run_store.list_runs()
        summary_by_path = {s["file_path"]: s for s in all_summaries}

        stats_list = self._run_store.get_stats_for_recipe(
            recipe_id, _summaries=all_summaries
        )
        stats_list = self._apply_time_filter(stats_list)

        self._populate_recipe_combo(all_summaries)
        self._render_table(stats_list, summary_by_path)
        self._render_chart(stats_list)

    def _apply_time_filter(self, stats_list: list[dict]) -> list[dict]:
        time_sel = self._time_combo.currentText()
        if time_sel == "All" or not stats_list:
            return stats_list
        from datetime import datetime, timezone, timedelta
        days = {"Last 7 days": 7, "Last 30 days": 30, "Last 90 days": 90}.get(time_sel)
        if days is None:
            return stats_list
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        result = []
        for s in stats_list:
            try:
                ts = datetime.fromisoformat(s["start_time"])
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                if ts >= cutoff:
                    result.append(s)
            except Exception:
                result.append(s)
        return result

    def _populate_recipe_combo(self, all_summaries: list[dict]) -> None:
        cur_id = self._recipe_combo.currentData()
        self._recipe_combo.blockSignals(True)
        self._recipe_combo.clear()
        self._recipe_combo.addItem("All Recipes", None)
        seen: set[str] = set()
        for s in all_summaries:
            fp = s.get("file_path", "")
            try:
                import json
                from pathlib import Path
                d = json.loads(Path(fp).read_text(encoding="utf-8"))
                datasets = d.get("datasets", [d])
                for ds in datasets:
                    for rid in ds.get("recipe_ids", []):
                        if rid and rid not in seen:
                            self._recipe_combo.addItem(rid, rid)
                            seen.add(rid)
            except Exception:
                pass
        if cur_id:
            for i in range(self._recipe_combo.count()):
                if self._recipe_combo.itemData(i) == cur_id:
                    self._recipe_combo.setCurrentIndex(i)
                    break
        self._recipe_combo.blockSignals(False)

    def _render_table(self, stats_list: list[dict], summary_by_path: dict) -> None:
        self._summaries = []
        self._batch_table.setRowCount(0)
        for s in reversed(stats_list):  # most recent first
            run_summary = summary_by_path.get(
                s.get("file_path", ""), {"file_path": s.get("file_path", "")}
            )
            self._summaries.append(run_summary)
            row = self._batch_table.rowCount()
            self._batch_table.insertRow(row)
            start = s.get("start_time", "")[:19].replace("T", " ")
            vals = [
                start,
                run_summary.get("type", "single"),
                str(run_summary.get("total_images", s.get("n", 0))),
                str(run_summary.get("success_count", "")),
                str(run_summary.get("fail_count", "")),
                f"{s['mean_nm']:.3f}" if s.get("mean_nm") is not None else "—",
                f"{s['std_nm']:.3f}" if s.get("std_nm") is not None else "—",
                s.get("label", ""),
            ]
            for col, v in enumerate(vals):
                item = QTableWidgetItem(v)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self._batch_table.setItem(row, col, item)

    def _render_chart(self, stats_list: list[dict]) -> None:
        if not stats_list:
            self._chart_label.setPixmap(QPixmap())
            self._chart_label.setText("No data available for chart.")
            return
        try:
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
            import numpy as np
        except ImportError:
            self._chart_label.setText(
                "Run Chart 需要 matplotlib。\n請執行：pip install matplotlib>=3.7"
            )
            return

        xs = list(range(len(stats_list)))
        means = [s["mean_nm"] for s in stats_list]
        stds  = [s["std_nm"] for s in stats_list]
        labels = [s.get("start_time", "")[:10] for s in stats_list]

        overall_mean = float(np.mean(means))
        overall_std  = float(np.std(means)) if len(means) > 1 else 0.0
        ucl = overall_mean + 3 * overall_std
        lcl = overall_mean - 3 * overall_std

        fig, ax = plt.subplots(figsize=(8, 3), dpi=90)
        fig.patch.set_facecolor("#1e1e1e")
        ax.set_facecolor("#2a2a2a")

        ax.errorbar(xs, means, yerr=stds, fmt="o-", color="#5b9bd5",
                    ecolor="#aaa", capsize=4, linewidth=1.5, label="Mean ± 1σ")
        ax.axhline(ucl, color="orange", linestyle="--", linewidth=1, label=f"UCL ({ucl:.2f})")
        ax.axhline(lcl, color="orange", linestyle="--", linewidth=1, label=f"LCL ({lcl:.2f})")
        ax.axhline(overall_mean, color="#80cc80", linestyle="-", linewidth=1, alpha=0.5)

        ax.set_xticks(xs)
        ax.set_xticklabels(labels, rotation=30, ha="right", fontsize=8, color="#ccc")
        ax.tick_params(axis="y", colors="#ccc")
        ax.set_ylabel("CD Mean (nm)", color="#ccc")
        ax.legend(fontsize=8, facecolor="#333", labelcolor="#ccc")
        ax.spines[:].set_color("#555")
        fig.tight_layout()

        buf = BytesIO()
        fig.savefig(buf, format="png", dpi=90, facecolor=fig.get_facecolor())
        plt.close(fig)
        buf.seek(0)

        pix = QPixmap()
        pix.loadFromData(buf.read())
        self._chart_label.setPixmap(pix)
        self._chart_label.setText("")

    def _on_row_double_clicked(self) -> None:
        self._on_load_selected()

    def _on_load_selected(self) -> None:
        row = self._batch_table.currentRow()
        if row < 0 or row >= len(self._summaries):
            return
        fp = self._summaries[row].get("file_path", "")
        if fp:
            self.load_requested.emit(fp)
            self.status_message.emit(f"Loading: {fp}")
