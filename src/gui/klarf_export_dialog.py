"""KLARF Export Dialog — filter a KLARF to the top-N defects by CD value.

Layout: QSplitter(Horizontal)
  Left  (~300 px) — file picker, batch source, top-N, output path, status
  Right           — summary stat cards + preview table
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from PyQt6.QtWidgets import (
    QDialog, QHBoxLayout, QVBoxLayout, QSplitter,
    QLabel, QPushButton, QSpinBox, QFileDialog,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QGroupBox, QFrame, QMessageBox, QWidget, QSizePolicy,
    QComboBox,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QColor


class NumericItem(QTableWidgetItem):
    """Table item that sorts numerically."""
    def __lt__(self, other: QTableWidgetItem) -> bool:
        try:
            return float(self.text()) < float(other.text())
        except (ValueError, TypeError):
            return super().__lt__(other)


# ── Background workers ────────────────────────────────────────────────────────

class _ExportWorker(QThread):
    finished = pyqtSignal(dict)
    error    = pyqtSignal(str)

    def __init__(
        self,
        klarf_path: str,
        batch_run: Any,
        top_n: int,
        output_path: str,
        ascending: bool,
        dry_run: bool,
    ):
        super().__init__()
        self._klarf_path  = klarf_path
        self._batch_run   = batch_run
        self._top_n       = top_n
        self._output_path = output_path
        self._ascending   = ascending
        self._dry_run     = dry_run

    def run(self) -> None:
        try:
            from ..core.klarf_exporter import KlarfTopNExporter
            result = KlarfTopNExporter().export(
                klarf_path=self._klarf_path,
                batch_run=self._batch_run,
                top_n=self._top_n,
                output_path=self._output_path,
                ascending=self._ascending,
                dry_run=self._dry_run,
            )
            self.finished.emit(result)
        except Exception as exc:
            self.error.emit(str(exc))


# ── Dialog ────────────────────────────────────────────────────────────────────

class KlarfExportDialog(QDialog):
    """Dialog for exporting a KLARF filtered to top-N defects by CD value."""

    def __init__(
        self,
        batch_run: Any = None,
        run_store: Any = None,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Export KLARF — Top-N by CD")
        self.setMinimumSize(1000, 600)

        self._batch_run  = batch_run
        self._run_store  = run_store
        self._klarf_path = ""
        self._output_path = ""
        self._worker: _ExportWorker | None = None

        self._build_ui()
        if batch_run is not None:
            self._update_batch_label()

    # ── Public API ────────────────────────────────────────────────────────────

    def set_batch_run(self, batch_run: Any) -> None:
        self._batch_run = batch_run
        self._update_batch_label()

    # ── Construction ──────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)

        # ── Left panel ────────────────────────────────────────────────────────
        left = QFrame()
        left.setObjectName("leftPanel")
        left.setFixedWidth(310)
        lv = QVBoxLayout(left)
        lv.setContentsMargins(12, 12, 12, 12)
        lv.setSpacing(10)

        # KLARF 檔案列
        klarf_grp = QGroupBox("KLARF 檔案")
        kg = QVBoxLayout(klarf_grp)
        kg.setSpacing(4)
        self._klarf_label = QLabel("（未選擇）")
        self._klarf_label.setWordWrap(True)
        self._klarf_label.setStyleSheet("color:#9a8a7a; font-size:11px;")
        klarf_btn = QPushButton("瀏覽…")
        klarf_btn.setFixedHeight(28)
        klarf_btn.clicked.connect(self._browse_klarf)
        kg.addWidget(self._klarf_label)
        kg.addWidget(klarf_btn)
        lv.addWidget(klarf_grp)

        # Batch 結果列
        batch_grp = QGroupBox("Batch 結果")
        bg = QVBoxLayout(batch_grp)
        bg.setSpacing(4)
        batch_row = QHBoxLayout()
        self._batch_dot = QLabel("●")
        self._batch_dot.setStyleSheet("color:#cc7b6c; font-size:12px; background:transparent;")
        self._batch_info_label = QLabel("（未載入）")
        self._batch_info_label.setStyleSheet("color:#9a8a7a; font-size:11px;")
        self._batch_info_label.setWordWrap(True)
        batch_row.addWidget(self._batch_dot)
        batch_row.addWidget(self._batch_info_label, stretch=1)
        bg.addLayout(batch_row)
        hist_btn = QPushButton("從歷史載入…")
        hist_btn.setFixedHeight(28)
        hist_btn.clicked.connect(self._load_from_history)
        bg.addWidget(hist_btn)
        lv.addWidget(batch_grp)

        # Top N + 升/降冪
        topn_grp = QGroupBox("篩選條件")
        tg = QVBoxLayout(topn_grp)
        tg.setSpacing(4)

        topn_row = QHBoxLayout()
        topn_row.addWidget(QLabel("取前 N 顆:"))
        self._topn_spin = QSpinBox()
        self._topn_spin.setRange(1, 9999)
        self._topn_spin.setValue(100)
        self._topn_spin.setFixedWidth(80)
        topn_row.addWidget(self._topn_spin)
        topn_row.addStretch()
        tg.addLayout(topn_row)

        sort_row = QHBoxLayout()
        sort_row.addWidget(QLabel("排序方式:"))
        self._sort_combo = QComboBox()
        self._sort_combo.addItem("最小 CD 優先（升冪）", True)
        self._sort_combo.addItem("最大 CD 優先（降冪）", False)
        sort_row.addWidget(self._sort_combo, stretch=1)
        tg.addLayout(sort_row)

        hint_lbl = QLabel("取前 N 顆最小/最大 Y-CD 位置")
        hint_lbl.setStyleSheet("color:#9a8a7a; font-size:10px;")
        tg.addWidget(hint_lbl)
        lv.addWidget(topn_grp)

        # 輸出路徑
        out_grp = QGroupBox("輸出路徑")
        og = QVBoxLayout(out_grp)
        og.setSpacing(4)
        self._output_label = QLabel("（將隨 KLARF 選擇自動填入）")
        self._output_label.setWordWrap(True)
        self._output_label.setStyleSheet("color:#9a8a7a; font-size:11px;")
        out_btn = QPushButton("變更…")
        out_btn.setFixedHeight(28)
        out_btn.clicked.connect(self._browse_output)
        og.addWidget(self._output_label)
        og.addWidget(out_btn)
        lv.addWidget(out_grp)

        # 狀態標籤
        self._status_label = QLabel("")
        self._status_label.setWordWrap(True)
        self._status_label.setStyleSheet("color:#a05020; font-size:11px;")
        lv.addWidget(self._status_label)

        lv.addStretch()

        # 底部按鈕
        btn_row = QHBoxLayout()
        self._preview_btn = QPushButton("預覽")
        self._preview_btn.setFixedHeight(32)
        self._preview_btn.clicked.connect(self._run_preview)
        self._export_btn = QPushButton("執行並輸出 KLARF")
        self._export_btn.setObjectName("primaryBtn")
        self._export_btn.setFixedHeight(36)
        self._export_btn.clicked.connect(self._run_export)
        btn_row.addWidget(self._preview_btn)
        btn_row.addWidget(self._export_btn)
        lv.addLayout(btn_row)

        splitter.addWidget(left)

        # ── Right panel ───────────────────────────────────────────────────────
        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(12, 12, 12, 12)
        rv.setSpacing(8)

        # Stat cards
        cards_w = QWidget()
        cards_hl = QHBoxLayout(cards_w)
        cards_hl.setContentsMargins(0, 0, 0, 0)
        cards_hl.setSpacing(8)

        self._stat_selected  = self._make_stat_card("—", "已選取")
        self._stat_min_cd    = self._make_stat_card("—", "最小 Y-CD (nm)")
        self._stat_nth_cd    = self._make_stat_card("—", "第 N 筆 Y-CD (nm)")
        for card in (self._stat_selected, self._stat_min_cd, self._stat_nth_cd):
            cards_hl.addWidget(card[0])
        rv.addWidget(cards_w)

        # Preview table
        self._table = QTableWidget(0, 7)
        self._table.setHorizontalHeaderLabels([
            "DefectID", "影像", "Y-CD (nm)",
            "XREL 原始", "XREL 新", "YREL 原始", "YREL 新",
        ])
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.horizontalHeader().setSortIndicatorShown(True)
        self._table.setSortingEnabled(True)
        self._table.setSelectionBehavior(self._table.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(self._table.EditTrigger.NoEditTriggers)
        rv.addWidget(self._table, stretch=1)

        # Coordinate note
        coord_note = QLabel(
            "座標換算說明：Step1 pixel offset（以影像中心為基準）→ Step2 換算 nm → Step3 更新 KLARF 座標。"
            "影像 Y 軸向下，KLARF Y 軸向上，兩者方向相反，因此 YREL 使用<b>減號</b>（YREL_new = YREL_orig − dy_nm）。"
        )
        coord_note.setWordWrap(True)
        coord_note.setStyleSheet("color:#9a8a7a; font-size:10px;")
        coord_note.setTextFormat(Qt.TextFormat.RichText)
        rv.addWidget(coord_note)

        splitter.addWidget(right)
        splitter.setSizes([310, 690])
        root.addWidget(splitter)

    def _make_stat_card(self, val: str, label: str) -> tuple[QFrame, QLabel]:
        card = QFrame()
        card.setStyleSheet("background:#f5f1eb; border-radius:8px; border:none;")
        cl = QVBoxLayout(card)
        cl.setContentsMargins(12, 10, 12, 10)
        cl.setSpacing(2)
        val_lbl = QLabel(val)
        val_lbl.setStyleSheet("font-size:22px; font-weight:500; color:#3f3428; background:transparent;")
        desc_lbl = QLabel(label)
        desc_lbl.setStyleSheet("font-size:11px; color:#9a8a7a; background:transparent;")
        cl.addWidget(val_lbl)
        cl.addWidget(desc_lbl)
        return card, val_lbl

    # ── File pickers ──────────────────────────────────────────────────────────

    def _browse_klarf(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "選擇 KLARF 檔案", "",
            "KLARF Files (*.klarf *.000 *.001);;All Files (*)"
        )
        if not path:
            return
        self._klarf_path = path
        self._klarf_label.setText(Path(path).name)
        self._klarf_label.setStyleSheet("color:#3f3428; font-size:11px;")
        self._auto_output_path()

    def _browse_output(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "輸出 KLARF 路徑", self._output_path or "",
            "KLARF Files (*.klarf);;All Files (*)"
        )
        if path:
            self._output_path = path
            self._output_label.setText(Path(path).name)
            self._output_label.setStyleSheet("color:#3f3428; font-size:11px;")

    def _auto_output_path(self) -> None:
        if not self._klarf_path:
            return
        p = Path(self._klarf_path)
        n = self._topn_spin.value()
        out = p.parent / f"{p.stem}_topN{n}.klarf"
        self._output_path = str(out)
        self._output_label.setText(out.name)
        self._output_label.setStyleSheet("color:#3f3428; font-size:11px;")

    def _load_from_history(self) -> None:
        if not self._run_store:
            QMessageBox.information(self, "無歷史記錄", "未設定 run store。")
            return
        from .workspaces.batch_workspace import _HistoryDialog
        dlg = _HistoryDialog(self._run_store, self)
        dlg.run_selected.connect(self._on_history_selected)
        dlg.exec()

    def _on_history_selected(self, file_path: str) -> None:
        if not self._run_store:
            return
        try:
            result = self._run_store.load(file_path)
            self.set_batch_run(result)
        except Exception as exc:
            QMessageBox.critical(self, "載入失敗", str(exc))

    def _update_batch_label(self) -> None:
        if self._batch_run is None:
            self._batch_dot.setStyleSheet("color:#cc7b6c; font-size:12px; background:transparent;")
            self._batch_info_label.setText("（未載入）")
            return
        from ..core.models import MultiDatasetBatchRun
        if isinstance(self._batch_run, MultiDatasetBatchRun):
            n = self._batch_run.total_images
            d = len(self._batch_run.datasets)
            label = f"Multi-batch · {d} datasets · {n} 張影像"
        else:
            n = self._batch_run.total_images
            label = f"Batch · {n} 張影像"
        self._batch_dot.setStyleSheet("color:#3e7f5d; font-size:12px; background:transparent;")
        self._batch_info_label.setText(label)
        self._batch_info_label.setStyleSheet("color:#3f3428; font-size:11px;")

    # ── Preview / Export ──────────────────────────────────────────────────────

    def _validate_inputs(self) -> bool:
        if not self._klarf_path:
            QMessageBox.warning(self, "缺少輸入", "請選擇 KLARF 檔案。")
            return False
        if self._batch_run is None:
            QMessageBox.warning(self, "缺少 Batch 結果", "請載入 Batch 量測結果。")
            return False
        return True

    def _run_preview(self) -> None:
        if not self._validate_inputs():
            return
        self._preview_btn.setEnabled(False)
        self._export_btn.setEnabled(False)
        self._start_worker(dry_run=True)

    def _run_export(self) -> None:
        if not self._validate_inputs():
            return
        if not self._output_path:
            self._auto_output_path()
        self._preview_btn.setEnabled(False)
        self._export_btn.setEnabled(False)
        self._start_worker(dry_run=False)

    def _start_worker(self, dry_run: bool) -> None:
        if self._worker and self._worker.isRunning():
            return
        ascending = bool(self._sort_combo.currentData())
        self._worker = _ExportWorker(
            klarf_path=self._klarf_path,
            batch_run=self._batch_run,
            top_n=self._topn_spin.value(),
            output_path=self._output_path or str(Path(self._klarf_path).parent / "output.klarf"),
            ascending=ascending,
            dry_run=dry_run,
        )
        self._worker.finished.connect(lambda r: self._on_done(r, dry_run))
        self._worker.error.connect(self._on_error)
        self._worker.start()

    @pyqtSlot(dict)
    def _on_done(self, result: dict, dry_run: bool) -> None:
        self._preview_btn.setEnabled(True)
        self._export_btn.setEnabled(True)

        # Update stat cards
        self._stat_selected[1].setText(str(result.get("exported_count", 0)))
        mn = result.get("min_ycd_nm", 0.0)
        mx = result.get("max_ycd_nm", 0.0)
        self._stat_min_cd[1].setText(f"{mn:.2f}")
        self._stat_nth_cd[1].setText(f"{mx:.2f}")

        # Unmatched warning
        uc = result.get("unmatched_count", 0)
        if uc:
            self._status_label.setText(f"⚠ {uc} 筆 defect 找不到對應影像")
        else:
            self._status_label.setText("")

        # Fill table
        self._fill_table(result.get("preview_rows", []), mn)

        if not dry_run:
            QMessageBox.information(
                self, "輸出完成",
                f"已輸出 {result['exported_count']} 筆 defect\n"
                f"最小 Y-CD：{mn:.2f} nm\n"
                f"第 N 筆 Y-CD：{mx:.2f} nm\n"
                f"輸出檔案：{result.get('output_path', '')}",
            )

    @pyqtSlot(str)
    def _on_error(self, msg: str) -> None:
        self._preview_btn.setEnabled(True)
        self._export_btn.setEnabled(True)
        QMessageBox.critical(self, "錯誤", f"匯出失敗：\n{msg}")

    def _fill_table(self, rows: list[dict], global_min: float) -> None:
        self._table.setSortingEnabled(False)
        self._table.setRowCount(0)
        amber = QColor("#FFF3CD")

        for row in rows:
            r = self._table.rowCount()
            self._table.insertRow(r)

            def _nitem(v: Any, fmt: str = "") -> QTableWidgetItem:
                txt = f"{v:{fmt}}" if fmt else str(v)
                item = NumericItem(txt)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                return item

            ycd = float(row.get("ycd_nm", 0.0))
            is_min = abs(ycd - global_min) < 1e-9

            items = [
                QTableWidgetItem(str(row.get("defect_id", ""))),
                QTableWidgetItem(str(row.get("image_stem", ""))),
                _nitem(ycd, ".2f"),
                _nitem(row.get("xrel_orig", 0), ".0f"),
                _nitem(row.get("xrel_new", 0), ".0f"),
                _nitem(row.get("yrel_orig", 0), ".0f"),
                _nitem(row.get("yrel_new", 0), ".0f"),
            ]
            for col, item in enumerate(items):
                if is_min:
                    item.setBackground(amber)
                self._table.setItem(r, col, item)

        self._table.setSortingEnabled(True)
        self._table.resizeColumnsToContents()
