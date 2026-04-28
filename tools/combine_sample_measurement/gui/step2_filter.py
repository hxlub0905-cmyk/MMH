"""Step 2 — Image Quality Filter Panel.

Re-runs Laplacian sharpness check on all images.
User adjusts threshold, auto-filters low-quality rows,
and can manually delete rows before proceeding.
Emits `filtered(df)` with only keep=True rows.
"""
from __future__ import annotations

import sys
from pathlib import Path

import cv2
import numpy as np
import pandas as pd
from PyQt6.QtCore import Qt, QThread, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QColor, QImage, QPixmap
from PyQt6.QtWidgets import (
    QAbstractItemView, QDoubleSpinBox, QGroupBox, QHBoxLayout,
    QLabel, QMessageBox, QProgressBar, QPushButton,
    QSizePolicy, QSplitter, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget, QHeaderView,
)

_HERE = Path(__file__).parent
_PROJECT_ROOT = _HERE.parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from tools.combine_sample_measurement.core.data_loader import _laplacian_var


class _NumericItem(QTableWidgetItem):
    def __lt__(self, other: QTableWidgetItem) -> bool:
        try:
            return float(self.text()) < float(other.text())
        except (ValueError, TypeError):
            return super().__lt__(other)


# ── Background worker ─────────────────────────────────────────────────────────

class _QualityWorker(QThread):
    row_done = pyqtSignal(int, float, int)  # row_index, laplacian_score, completed_count
    finished = pyqtSignal()
    error    = pyqtSignal(str)

    def __init__(self, image_paths: list[str]):
        super().__init__()
        self._paths = image_paths

    def run(self) -> None:
        from concurrent.futures import ThreadPoolExecutor, as_completed
        try:
            n = len(self._paths)
            completed = 0
            max_workers = min(6, max(1, n))
            with ThreadPoolExecutor(max_workers=max_workers) as ex:
                futures = {ex.submit(_laplacian_var, p): i
                           for i, p in enumerate(self._paths)}
                for future in as_completed(futures):
                    i = futures[future]
                    try:
                        score = future.result()
                    except Exception:
                        score = 0.0
                    completed += 1
                    self.row_done.emit(i, score, completed)
            self.finished.emit()
        except Exception as exc:
            self.error.emit(str(exc))


# ── Step 2 Widget ─────────────────────────────────────────────────────────────

class Step2FilterWidget(QWidget):
    """Quality filter panel."""

    filtered = pyqtSignal(object)   # pd.DataFrame (keep=True rows)

    _COL_IDX    = 0
    _COL_DS     = 1
    _COL_FILE   = 2
    _COL_CD     = 3
    _COL_LAP    = 4
    _COL_PASS   = 5
    _COL_KEEP   = 6

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._df: pd.DataFrame | None = None
        self._worker: _QualityWorker | None = None
        self._build_ui()

    def set_dataframe(self, df: pd.DataFrame) -> None:
        self._df = df.copy()
        self._fill_table()
        self._update_counts()

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)

        # ── Left panel ─────────────────────────────────────────────────────
        left = QWidget()
        left.setFixedWidth(260)
        lv = QVBoxLayout(left)
        lv.setContentsMargins(12, 12, 12, 12)
        lv.setSpacing(10)

        thresh_grp = QGroupBox("Laplacian 閾值")
        tg = QVBoxLayout(thresh_grp)
        tg.setSpacing(6)
        tg.addWidget(QLabel("低於此值的圖片視為模糊 (FAIL)："))
        self._thresh_spin = QDoubleSpinBox()
        self._thresh_spin.setRange(0.0, 100000.0)
        self._thresh_spin.setValue(145.0)
        self._thresh_spin.setSingleStep(10.0)
        self._thresh_spin.setDecimals(1)
        tg.addWidget(self._thresh_spin)
        lv.addWidget(thresh_grp)

        self._run_btn = QPushButton("執行品質檢查")
        self._run_btn.setObjectName("primaryBtn")
        self._run_btn.setFixedHeight(34)
        self._run_btn.clicked.connect(self._run_quality_check)
        lv.addWidget(self._run_btn)

        self._progress = QProgressBar()
        self._progress.setFixedHeight(6)
        self._progress.setTextVisible(False)
        self._progress.hide()
        lv.addWidget(self._progress)

        self._status_lbl = QLabel("")
        self._status_lbl.setWordWrap(True)
        self._status_lbl.setStyleSheet("color:#9a8a7a; font-size:11px;")
        lv.addWidget(self._status_lbl)

        auto_grp = QGroupBox("篩選操作")
        ag = QVBoxLayout(auto_grp)
        ag.setSpacing(6)
        self._auto_btn = QPushButton("自動剔除 FAIL 列")
        self._auto_btn.setFixedHeight(28)
        self._auto_btn.clicked.connect(self._auto_filter)
        self._restore_btn = QPushButton("還原全部（重設 keep）")
        self._restore_btn.setFixedHeight(28)
        self._restore_btn.clicked.connect(self._restore_all)
        self._del_btn = QPushButton("手動刪除選取列")
        self._del_btn.setFixedHeight(28)
        self._del_btn.clicked.connect(self._delete_selected)
        ag.addWidget(self._auto_btn)
        ag.addWidget(self._del_btn)
        ag.addWidget(self._restore_btn)
        lv.addWidget(auto_grp)

        self._count_lbl = QLabel("通過 0 / 共 0 筆")
        self._count_lbl.setStyleSheet("font-size:12px; color:#3f3428;")
        lv.addWidget(self._count_lbl)

        lv.addStretch()

        self._next_btn = QPushButton("套用篩選 → Step 3")
        self._next_btn.setObjectName("primaryBtn")
        self._next_btn.setFixedHeight(36)
        self._next_btn.clicked.connect(self._emit_filtered)
        lv.addWidget(self._next_btn)

        splitter.addWidget(left)

        # ── Right panel ────────────────────────────────────────────────────
        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(0, 0, 0, 0)
        rv.setSpacing(0)

        right_split = QSplitter(Qt.Orientation.Vertical)
        right_split.setChildrenCollapsible(False)

        # Data table
        tbl_w = QWidget()
        tv = QVBoxLayout(tbl_w)
        tv.setContentsMargins(8, 8, 8, 4)

        self._table = QTableWidget(0, 7)
        self._table.setHorizontalHeaderLabels([
            "#", "Dataset", "圖片檔名", "CD (nm)", "Laplacian", "Pass?", "Keep"
        ])
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.setSortingEnabled(True)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.currentCellChanged.connect(self._on_row_changed)
        tv.addWidget(self._table)
        right_split.addWidget(tbl_w)

        # Image preview
        img_w = QWidget()
        iw = QVBoxLayout(img_w)
        iw.setContentsMargins(8, 4, 8, 8)

        img_hdr = QHBoxLayout()
        img_hdr.addWidget(QLabel("影像預覽"))
        self._lap_info_lbl = QLabel("")
        self._lap_info_lbl.setStyleSheet("color:#9a8a7a; font-size:11px;")
        img_hdr.addWidget(self._lap_info_lbl)
        img_hdr.addStretch()
        iw.addLayout(img_hdr)

        self._img_lbl = QLabel("選擇列以查看影像")
        self._img_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._img_lbl.setMinimumHeight(160)
        self._img_lbl.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self._img_lbl.setStyleSheet(
            "background:#f5f1eb; border-radius:6px; color:#b0a090; font-size:11px;"
        )
        iw.addWidget(self._img_lbl, stretch=1)
        right_split.addWidget(img_w)
        right_split.setSizes([420, 220])
        rv.addWidget(right_split)

        splitter.addWidget(right)
        splitter.setSizes([260, 740])
        root.addWidget(splitter)

    # ── Quality check ─────────────────────────────────────────────────────────

    def _run_quality_check(self) -> None:
        if self._df is None or self._df.empty:
            QMessageBox.warning(self, "無資料", "請先完成 Step 1 載入。")
            return
        if self._worker and self._worker.isRunning():
            return

        paths = list(self._df["image_path"].fillna("").astype(str))
        self._run_btn.setEnabled(False)
        self._progress.setRange(0, len(paths))
        self._progress.setValue(0)
        self._progress.show()

        self._status_lbl.setText(f"品質檢查中… 共 {len(paths)} 張")
        self._worker = _QualityWorker(paths)
        self._worker.row_done.connect(self._on_row_done)
        self._worker.finished.connect(self._on_quality_done)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    @pyqtSlot(int, float, int)
    def _on_row_done(self, row_idx: int, score: float, completed: int) -> None:
        if self._df is None:
            return
        self._df.at[self._df.index[row_idx], "laplacian_score"] = score
        self._progress.setValue(completed)

    @pyqtSlot()
    def _on_quality_done(self) -> None:
        self._progress.hide()
        self._run_btn.setEnabled(True)
        # Rebuild entire table once so all Laplacian/Pass columns are updated together
        self._fill_table()
        self._update_counts()
        self._status_lbl.setText("品質檢查完成")

    @pyqtSlot(str)
    def _on_error(self, msg: str) -> None:
        self._progress.hide()
        self._run_btn.setEnabled(True)
        QMessageBox.critical(self, "錯誤", msg)

    # ── Filter operations ─────────────────────────────────────────────────────

    def _auto_filter(self) -> None:
        if self._df is None:
            return
        threshold = self._thresh_spin.value()
        mask = self._df["laplacian_score"] < threshold
        self._df.loc[mask, "keep"] = False
        self._sync_keep_column()
        self._update_counts()

    def _restore_all(self) -> None:
        if self._df is None:
            return
        self._df["keep"] = True
        self._sync_keep_column()
        self._update_counts()

    def _delete_selected(self) -> None:
        """Mark selected table rows as keep=False."""
        if self._df is None:
            return
        rows = {idx.row() for idx in self._table.selectedIndexes()}
        for r in rows:
            idx_item = self._table.item(r, self._COL_IDX)
            if idx_item is None:
                continue
            df_idx = self._df.index[int(idx_item.text())]
            self._df.at[df_idx, "keep"] = False

        self._sync_keep_column()
        self._update_counts()

    def _sync_keep_column(self) -> None:
        """Refresh the Keep column in the table to match df["keep"]."""
        self._table.setSortingEnabled(False)
        for r in range(self._table.rowCount()):
            idx_item = self._table.item(r, self._COL_IDX)
            if idx_item is None:
                continue
            df_row_idx = int(idx_item.text())
            keep = bool(self._df.iloc[df_row_idx]["keep"])
            keep_item = self._table.item(r, self._COL_KEEP)
            if keep_item:
                keep_item.setText("✓" if keep else "✗")
                keep_item.setForeground(
                    QColor("#2e7d32") if keep else QColor("#c62828")
                )
        self._table.setSortingEnabled(True)

    def _update_counts(self) -> None:
        if self._df is None:
            self._count_lbl.setText("通過 0 / 共 0 筆")
            return
        total = len(self._df)
        keep  = int(self._df["keep"].sum())
        self._count_lbl.setText(f"保留 {keep} / 共 {total} 筆")

    def _emit_filtered(self) -> None:
        if self._df is None or self._df.empty:
            QMessageBox.warning(self, "無資料", "請先完成 Step 1 載入。")
            return
        filtered = self._df[self._df["keep"]].copy()
        if filtered.empty:
            QMessageBox.warning(self, "無資料", "所有列都被排除，請調整篩選條件。")
            return
        self.filtered.emit(filtered)

    # ── Fill table ─────────────────────────────────────────────────────────────

    def _fill_table(self) -> None:
        if self._df is None:
            return
        self._table.setSortingEnabled(False)
        self._table.setRowCount(0)

        for i, (_, row) in enumerate(self._df.iterrows()):
            r = self._table.rowCount()
            self._table.insertRow(r)

            lap = row.get("laplacian_score", float("nan"))
            lap_str  = f"{lap:.1f}" if not pd.isna(lap) else "—"
            pass_str = ""
            if not pd.isna(lap):
                pass_str = "PASS" if lap >= self._thresh_spin.value() else "FAIL"
            keep_str = "✓" if bool(row.get("keep", True)) else "✗"

            cd_str = f"{float(row.get('cd_nm', 0) or 0):.2f}"
            items = [
                QTableWidgetItem(str(i)),
                QTableWidgetItem(str(row.get("source_dataset", ""))),
                QTableWidgetItem(str(row.get("image_file", ""))),
                _NumericItem(cd_str),
                _NumericItem(lap_str),
                QTableWidgetItem(pass_str),
                QTableWidgetItem(keep_str),
            ]
            for c, item in enumerate(items):
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                item.setData(Qt.ItemDataRole.UserRole, i)
                self._table.setItem(r, c, item)

        self._table.setSortingEnabled(True)
        self._table.resizeColumnsToContents()

    # ── Image preview ──────────────────────────────────────────────────────────

    @pyqtSlot(int, int, int, int)
    def _on_row_changed(self, cur_row: int, *_) -> None:
        if cur_row < 0 or self._df is None:
            return
        idx_item = self._table.item(cur_row, self._COL_IDX)
        if idx_item is None:
            return
        df_row_idx = int(idx_item.text())
        row = self._df.iloc[df_row_idx]

        path = str(row.get("image_path", ""))
        lap  = row.get("laplacian_score", float("nan"))
        lap_txt = f"Laplacian = {lap:.1f}" if not pd.isna(lap) else ""
        self._lap_info_lbl.setText(lap_txt)

        if not path:
            self._img_lbl.setText("無影像路徑")
            return
        try:
            img = cv2.imread(path, cv2.IMREAD_UNCHANGED)
            if img is None:
                self._img_lbl.setText(f"無法載入：{path}")
                return
            if img.dtype != np.uint8:
                img = cv2.normalize(img, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
            if img.ndim == 2:
                img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
            elif img.shape[2] == 4:
                img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
            rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            h, w, ch = rgb.shape
            qi  = QImage(rgb.tobytes(), w, h, w * ch, QImage.Format.Format_RGB888)
            pix = QPixmap.fromImage(qi)
            lw  = max(self._img_lbl.width(),  100)
            lh  = max(self._img_lbl.height(), 100)
            self._img_lbl.setPixmap(
                pix.scaled(lw, lh,
                           Qt.AspectRatioMode.KeepAspectRatio,
                           Qt.TransformationMode.SmoothTransformation)
            )
        except Exception as exc:
            self._img_lbl.setText(f"載入失敗：{exc}")
