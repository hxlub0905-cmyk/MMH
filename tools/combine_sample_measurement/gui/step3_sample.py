"""Step 3 — Sampling Panel.

User picks Min/Max CD and Top-N count.
Preview shows selected rows + summary stats.
Emits `sampled(df)` where new_did has been assigned (1…N).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QAbstractItemView, QFrame, QGroupBox, QHBoxLayout,
    QLabel, QMessageBox, QPushButton, QRadioButton,
    QSpinBox, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget, QHeaderView,
)

_HERE = Path(__file__).parent
_PROJECT_ROOT = _HERE.parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


class Step3SampleWidget(QWidget):
    """Sampling configuration panel."""

    sampled = pyqtSignal(object)   # pd.DataFrame with new_did assigned

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._df: pd.DataFrame | None = None
        self._build_ui()

    def set_dataframe(self, df: pd.DataFrame) -> None:
        self._df = df.copy()
        self._update_stats_cards(df)
        self._run_preview()

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QHBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(12)

        # ── Left control panel ────────────────────────────────────────────
        left = QWidget()
        left.setFixedWidth(260)
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 0, 0)
        lv.setSpacing(12)

        sort_grp = QGroupBox("採樣方式")
        sg = QVBoxLayout(sort_grp)
        sg.setSpacing(8)
        self._min_radio = QRadioButton("最小 CD 優先（升冪）")
        self._max_radio = QRadioButton("最大 CD 優先（降冪）")
        self._min_radio.setChecked(True)
        sg.addWidget(self._min_radio)
        sg.addWidget(self._max_radio)
        lv.addWidget(sort_grp)

        topn_grp = QGroupBox("取前 N 筆")
        tg = QVBoxLayout(topn_grp)
        tg.setSpacing(6)
        topn_row = QHBoxLayout()
        topn_row.addWidget(QLabel("N ="))
        self._topn_spin = QSpinBox()
        self._topn_spin.setRange(1, 99999)
        self._topn_spin.setValue(500)
        self._topn_spin.setFixedWidth(90)
        topn_row.addWidget(self._topn_spin)
        topn_row.addStretch()
        tg.addLayout(topn_row)
        lv.addWidget(topn_grp)

        prev_btn = QPushButton("更新預覽")
        prev_btn.setFixedHeight(30)
        prev_btn.clicked.connect(self._run_preview)
        lv.addWidget(prev_btn)

        # ── Stat cards ────────────────────────────────────────────────────
        stats_grp = QGroupBox("採樣後統計")
        sg2 = QVBoxLayout(stats_grp)
        sg2.setSpacing(6)

        self._card_total  = self._make_card("0", "總資料筆數")
        self._card_select = self._make_card("0", "採樣筆數")
        self._card_min    = self._make_card("—", "最小 CD (nm)")
        self._card_max    = self._make_card("—", "最大 CD (nm)")
        self._card_mean   = self._make_card("—", "平均 CD (nm)")

        for card, _ in (self._card_total, self._card_select,
                        self._card_min, self._card_max, self._card_mean):
            sg2.addWidget(card)
        lv.addWidget(stats_grp)

        lv.addStretch()

        self._next_btn = QPushButton("確認採樣 → Step 4")
        self._next_btn.setObjectName("primaryBtn")
        self._next_btn.setFixedHeight(36)
        self._next_btn.clicked.connect(self._emit_sampled)
        lv.addWidget(self._next_btn)

        root.addWidget(left)

        # ── Right: preview table ──────────────────────────────────────────
        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(0, 0, 0, 0)
        rv.setSpacing(4)

        rv.addWidget(QLabel("採樣預覽（僅顯示選中的 N 筆）："))

        self._table = QTableWidget(0, 9)
        self._table.setHorizontalHeaderLabels([
            "新 DID", "Dataset", "圖片檔名",
            "CD (nm)", "nm/px", "Laplacian",
            "舊 DID", "orig XREL", "orig YREL",
        ])
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.setSortingEnabled(True)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        rv.addWidget(self._table, stretch=1)

        self._result_lbl = QLabel("")
        self._result_lbl.setStyleSheet("color:#9a8a7a; font-size:11px;")
        rv.addWidget(self._result_lbl)

        root.addWidget(right, stretch=1)

    def _make_card(self, val: str, label: str) -> tuple[QFrame, QLabel]:
        card = QFrame()
        card.setStyleSheet("background:#f5f1eb; border-radius:6px; border:none;")
        cl = QVBoxLayout(card)
        cl.setContentsMargins(10, 6, 10, 6)
        cl.setSpacing(1)
        val_lbl = QLabel(val)
        val_lbl.setStyleSheet(
            "font-size:18px; font-weight:500; color:#3f3428; background:transparent;"
        )
        desc_lbl = QLabel(label)
        desc_lbl.setStyleSheet("font-size:10px; color:#9a8a7a; background:transparent;")
        cl.addWidget(val_lbl)
        cl.addWidget(desc_lbl)
        return card, val_lbl

    def _update_stats_cards(self, df: pd.DataFrame) -> None:
        self._card_total[1].setText(str(len(df)))
        cds = pd.to_numeric(df["cd_nm"], errors="coerce").dropna()
        if not cds.empty:
            self._card_min[1].setText(f"{cds.min():.2f}")
            self._card_max[1].setText(f"{cds.max():.2f}")
            self._card_mean[1].setText(f"{cds.mean():.2f}")
        else:
            for card, lbl in (self._card_min, self._card_max, self._card_mean):
                lbl.setText("—")

    # ── Preview ───────────────────────────────────────────────────────────────

    def _run_preview(self) -> None:
        if self._df is None or self._df.empty:
            return
        sampled = self._do_sample(self._df)
        self._fill_table(sampled)
        self._card_select[1].setText(str(len(sampled)))
        cds = pd.to_numeric(sampled["cd_nm"], errors="coerce").dropna()
        if not cds.empty:
            self._result_lbl.setText(
                f"採樣 {len(sampled)} 筆  |  "
                f"CD 範圍：{cds.min():.2f} ~ {cds.max():.2f} nm  |  "
                f"平均：{cds.mean():.2f} nm"
            )

    def _do_sample(self, df: pd.DataFrame) -> pd.DataFrame:
        """Sort by cd_nm, take top-N, assign new_did."""
        ascending = self._min_radio.isChecked()
        sorted_df = df.sort_values("cd_nm", ascending=ascending, na_position="last")
        n = self._topn_spin.value()
        selected = sorted_df.head(n).copy()
        selected = selected.reset_index(drop=True)
        selected["new_did"] = range(1, len(selected) + 1)
        return selected

    def _fill_table(self, df: pd.DataFrame) -> None:
        self._table.setSortingEnabled(False)
        self._table.setRowCount(0)

        for _, row in df.iterrows():
            r = self._table.rowCount()
            self._table.insertRow(r)

            lap = row.get("laplacian_score", float("nan"))
            lap_str = f"{lap:.1f}" if not pd.isna(lap) else "—"

            vals = [
                str(int(row.get("new_did", 0))),
                str(row.get("source_dataset", "")),
                str(row.get("image_file", "")),
                f"{float(row.get('cd_nm', 0) or 0):.2f}",
                f"{float(row.get('nm_per_pixel', 0) or 0):.4f}",
                lap_str,
                str(row.get("old_did", "")),
                _fmt(row.get("orig_xrel")),
                _fmt(row.get("orig_yrel")),
            ]
            for c, v in enumerate(vals):
                item = QTableWidgetItem(v)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self._table.setItem(r, c, item)

        self._table.setSortingEnabled(True)
        self._table.resizeColumnsToContents()

    # ── Emit ──────────────────────────────────────────────────────────────────

    def _emit_sampled(self) -> None:
        if self._df is None or self._df.empty:
            QMessageBox.warning(self, "無資料", "請先完成 Step 2 篩選。")
            return
        sampled = self._do_sample(self._df)
        if sampled.empty:
            QMessageBox.warning(self, "無資料", "採樣後無任何結果，請調整設定。")
            return
        self.sampled.emit(sampled)


def _fmt(v) -> str:
    try:
        if v is None or pd.isna(float(v)):
            return "—"
        return f"{float(v):.0f}"
    except (TypeError, ValueError):
        return str(v)
