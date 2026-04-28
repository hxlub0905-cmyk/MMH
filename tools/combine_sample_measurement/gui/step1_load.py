"""Step 1 — Dataset Loading Panel.

User adds (Dataset Name, Excel, Image Folder, KLARF) tuples,
selects which KLARF to use as output template, then clicks Load.
Emits `loaded(df, ds_klafs, template_parsed)` when done.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pandas as pd
from PyQt6.QtCore import Qt, QThread, pyqtSignal, pyqtSlot
from PyQt6.QtWidgets import (
    QComboBox, QFileDialog, QGroupBox, QHBoxLayout,
    QLabel, QMessageBox, QProgressBar, QPushButton,
    QSizePolicy, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget, QHeaderView, QAbstractItemView,
    QLineEdit,
)

_HERE = Path(__file__).parent
_PROJECT_ROOT = _HERE.parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from tools.combine_sample_measurement.core.data_loader import (
    DatasetEntry, load_dataset, combine_datasets,
)


# ── Background worker ─────────────────────────────────────────────────────────

class _LoadWorker(QThread):
    progress  = pyqtSignal(int, int, str)   # current, total, message
    finished  = pyqtSignal(object, dict, dict)   # df, ds_klafs, template_parsed
    error     = pyqtSignal(str)

    def __init__(self, entries: list[DatasetEntry], template_idx: int):
        super().__init__()
        self._entries      = entries
        self._template_idx = template_idx

    def run(self) -> None:
        try:
            dfs: list[pd.DataFrame]         = []
            ds_klafs: dict[str, dict]        = {}
            template_parsed: dict[str, Any]  = {}

            total = len(self._entries)
            for i, entry in enumerate(self._entries):
                self.progress.emit(i, total, f"載入：{entry.name}")
                df, parsed = load_dataset(entry)
                dfs.append(df)
                ds_klafs[entry.name] = parsed
                if i == self._template_idx:
                    template_parsed = parsed

            self.progress.emit(total, total, "合併資料集…")
            combined = combine_datasets(dfs)
            self.finished.emit(combined, ds_klafs, template_parsed)
        except Exception as exc:
            self.error.emit(str(exc))


# ── Step 1 Widget ─────────────────────────────────────────────────────────────

class Step1LoadWidget(QWidget):
    """Dataset loading panel."""

    loaded = pyqtSignal(object, dict, dict)   # df, ds_klafs, template_parsed

    # Column indices in dataset table
    _COL_NAME   = 0
    _COL_EXCEL  = 1
    _COL_FOLDER = 2
    _COL_KLARF  = 3
    _COL_STATUS = 4

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._worker: _LoadWorker | None = None
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        # ── Dataset table ──────────────────────────────────────────────────────
        grp = QGroupBox("Dataset 列表（每列：名稱 | Excel | 圖片資料夾 | KLARF）")
        gv  = QVBoxLayout(grp)
        gv.setSpacing(6)

        self._table = QTableWidget(0, 5)
        self._table.setHorizontalHeaderLabels(
            ["Dataset 名稱", "Excel 路徑", "圖片資料夾", "KLARF 路徑", "狀態"]
        )
        self._table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Interactive
        )
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked)
        self._table.setMinimumHeight(160)
        gv.addWidget(self._table)

        btn_row = QHBoxLayout()
        add_btn = QPushButton("新增 Dataset")
        add_btn.setFixedHeight(28)
        add_btn.clicked.connect(self._add_dataset)
        rem_btn = QPushButton("刪除選取")
        rem_btn.setFixedHeight(28)
        rem_btn.clicked.connect(self._remove_selected)
        btn_row.addWidget(add_btn)
        btn_row.addWidget(rem_btn)
        btn_row.addStretch()
        gv.addLayout(btn_row)

        root.addWidget(grp)

        # ── Template KLARF selector ────────────────────────────────────────────
        tmpl_row = QHBoxLayout()
        tmpl_row.addWidget(QLabel("輸出 KLARF 模板（取哪個 Dataset 的 KLARF 作 header）："))
        self._template_combo = QComboBox()
        self._template_combo.setMinimumWidth(200)
        tmpl_row.addWidget(self._template_combo)
        tmpl_row.addStretch()
        root.addLayout(tmpl_row)

        # ── Load button + progress ────────────────────────────────────────────
        load_row = QHBoxLayout()
        self._load_btn = QPushButton("載入並合併所有 Dataset")
        self._load_btn.setObjectName("primaryBtn")
        self._load_btn.setFixedHeight(36)
        self._load_btn.clicked.connect(self._run_load)
        self._progress_bar = QProgressBar()
        self._progress_bar.setFixedHeight(6)
        self._progress_bar.setTextVisible(False)
        self._progress_bar.hide()
        self._status_lbl = QLabel("")
        self._status_lbl.setStyleSheet("color:#9a8a7a; font-size:11px;")
        load_row.addWidget(self._load_btn)
        load_row.addWidget(self._status_lbl)
        load_row.addStretch()
        root.addLayout(load_row)
        root.addWidget(self._progress_bar)

        # ── Combined preview table ─────────────────────────────────────────────
        prev_grp = QGroupBox("合併預覽（載入後顯示）")
        pv = QVBoxLayout(prev_grp)
        self._preview = QTableWidget(0, 9)
        self._preview.setHorizontalHeaderLabels([
            "來源 Dataset", "圖片檔名", "CD (nm)", "nm/px",
            "cd_x_px", "cd_y_px", "舊 DID",
            "orig XREL", "orig YREL",
        ])
        self._preview.horizontalHeader().setStretchLastSection(True)
        self._preview.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._preview.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._preview.setMinimumHeight(200)
        pv.addWidget(self._preview)
        self._count_lbl = QLabel("共 0 筆")
        self._count_lbl.setStyleSheet("color:#9a8a7a; font-size:11px;")
        pv.addWidget(self._count_lbl)
        root.addWidget(prev_grp, stretch=1)

    # ── Add / Remove ──────────────────────────────────────────────────────────

    def _add_dataset(self) -> None:
        excel, _ = QFileDialog.getOpenFileName(
            self, "選擇 Excel 檔案", "",
            "Excel Files (*.xlsx *.xls);;All Files (*)"
        )
        if not excel:
            return

        folder = QFileDialog.getExistingDirectory(self, "選擇圖片資料夾")
        if not folder:
            return

        klarf, _ = QFileDialog.getOpenFileName(
            self, "選擇對應 KLARF 檔案", Path(excel).parent.as_posix(),
            "KLARF Files (*.klarf *.000 *.001);;All Files (*)"
        )
        if not klarf:
            return

        name = Path(excel).stem
        r    = self._table.rowCount()
        self._table.insertRow(r)
        self._table.setItem(r, self._COL_NAME,   QTableWidgetItem(name))
        self._table.setItem(r, self._COL_EXCEL,  QTableWidgetItem(excel))
        self._table.setItem(r, self._COL_FOLDER, QTableWidgetItem(folder))
        self._table.setItem(r, self._COL_KLARF,  QTableWidgetItem(klarf))
        self._table.setItem(r, self._COL_STATUS, QTableWidgetItem("待載入"))

        self._rebuild_template_combo()

    def _remove_selected(self) -> None:
        rows = sorted(
            {idx.row() for idx in self._table.selectedIndexes()}, reverse=True
        )
        for r in rows:
            self._table.removeRow(r)
        self._rebuild_template_combo()

    def _rebuild_template_combo(self) -> None:
        prev = self._template_combo.currentText()
        self._template_combo.clear()
        for r in range(self._table.rowCount()):
            name = (self._table.item(r, self._COL_NAME) or QTableWidgetItem("")).text()
            self._template_combo.addItem(name)
        idx = self._template_combo.findText(prev)
        if idx >= 0:
            self._template_combo.setCurrentIndex(idx)

    # ── Load ──────────────────────────────────────────────────────────────────

    def _run_load(self) -> None:
        if self._table.rowCount() == 0:
            QMessageBox.warning(self, "無 Dataset", "請先新增至少一個 Dataset。")
            return

        entries: list[DatasetEntry] = []
        for r in range(self._table.rowCount()):
            def _cell(c: int) -> str:
                item = self._table.item(r, c)
                return item.text().strip() if item else ""

            name   = _cell(self._COL_NAME)   or f"DS{r+1}"
            excel  = _cell(self._COL_EXCEL)
            folder = _cell(self._COL_FOLDER)
            klarf  = _cell(self._COL_KLARF)

            missing = []
            if not excel:  missing.append("Excel")
            if not folder: missing.append("圖片資料夾")
            if not klarf:  missing.append("KLARF")
            if missing:
                QMessageBox.warning(self, "資料不完整",
                                    f"第 {r+1} 列缺少：{', '.join(missing)}")
                return
            entries.append(DatasetEntry(name=name, excel_path=excel,
                                        image_folder=folder, klarf_path=klarf))

        tmpl_name = self._template_combo.currentText()
        tmpl_idx  = next(
            (i for i, e in enumerate(entries) if e.name == tmpl_name), 0
        )

        if self._worker and self._worker.isRunning():
            return
        self._load_btn.setEnabled(False)
        self._progress_bar.setRange(0, len(entries))
        self._progress_bar.setValue(0)
        self._progress_bar.show()

        self._worker = _LoadWorker(entries, tmpl_idx)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_loaded)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    @pyqtSlot(int, int, str)
    def _on_progress(self, cur: int, total: int, msg: str) -> None:
        self._progress_bar.setMaximum(max(total, 1))
        self._progress_bar.setValue(cur)
        self._status_lbl.setText(msg)
        r = cur - 1
        if 0 <= r < self._table.rowCount():
            self._table.setItem(r, self._COL_STATUS, QTableWidgetItem("✓ 已載入"))

    @pyqtSlot(object, dict, dict)
    def _on_loaded(self, df: pd.DataFrame, ds_klafs: dict, template_parsed: dict) -> None:
        self._progress_bar.hide()
        self._load_btn.setEnabled(True)
        self._status_lbl.setText(f"完成，共 {len(df)} 筆")
        self._fill_preview(df)
        self.loaded.emit(df, ds_klafs, template_parsed)

    @pyqtSlot(str)
    def _on_error(self, msg: str) -> None:
        self._progress_bar.hide()
        self._load_btn.setEnabled(True)
        self._status_lbl.setText("")
        QMessageBox.critical(self, "載入失敗", msg)

    def _fill_preview(self, df: pd.DataFrame) -> None:
        self._preview.setSortingEnabled(False)
        self._preview.setRowCount(0)

        cols_map = [
            "source_dataset", "image_file", "cd_nm", "nm_per_pixel",
            "cd_line_x_px", "cd_line_y_px", "old_did", "orig_xrel", "orig_yrel",
        ]

        for _, row in df.iterrows():
            r = self._preview.rowCount()
            self._preview.insertRow(r)
            for c, col in enumerate(cols_map):
                val = row.get(col, "")
                if isinstance(val, float):
                    txt = f"{val:.2f}" if not pd.isna(val) else "—"
                else:
                    txt = str(val) if val != "" else "—"
                item = QTableWidgetItem(txt)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self._preview.setItem(r, c, item)

        self._preview.setSortingEnabled(True)
        self._preview.resizeColumnsToContents()
        self._count_lbl.setText(f"共 {len(df)} 筆")
