"""Review workspace — browse single or batch measurement results."""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QLabel, QPushButton, QButtonGroup, QFrame,
    QListWidget, QListWidgetItem, QGroupBox,
)
from PyQt6.QtCore import Qt, pyqtSignal

from ..image_viewer import ImageViewer
from ..results_panel import ResultsPanel
from ...core.models import BatchRunRecord, MeasurementRecord
from ...core.recipe_base import PipelineResult
from ...core.annotator import OverlayOptions, draw_overlays
from ..._compat import records_to_legacy_cuts


class ReviewWorkspace(QWidget):
    status_message = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._result: PipelineResult | None = None
        self._focused: tuple[int, int] | None = None

        # Batch mode state
        self._batch_entries: list[dict] = []   # raw entry dicts from output_manifest
        self._batch_records: list[list[MeasurementRecord]] = []  # per-image records

        self._build_ui()

    # ── Construction ──────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        root.addWidget(self._build_header())

        # Outer horizontal splitter: image list (batch) | viewer area
        self._outer_split = QSplitter(Qt.Orientation.Horizontal)
        self._outer_split.setChildrenCollapsible(False)

        # Left: batch image list (hidden in single-image mode)
        list_panel = QGroupBox("Batch Images")
        lv = QVBoxLayout(list_panel)
        lv.setContentsMargins(4, 8, 4, 4)
        self._img_list = QListWidget()
        self._img_list.currentRowChanged.connect(self._on_batch_row_changed)
        lv.addWidget(self._img_list)
        self._list_panel = list_panel
        self._list_panel.setVisible(False)
        self._list_panel.setMinimumWidth(180)
        self._list_panel.setMaximumWidth(280)
        self._outer_split.addWidget(self._list_panel)

        # Right: vertical splitter — viewer on top, results on bottom
        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(0, 0, 0, 0)

        v_split = QSplitter(Qt.Orientation.Vertical)
        v_split.setChildrenCollapsible(False)

        self._viewer = ImageViewer()
        v_split.addWidget(self._viewer)

        self._results = ResultsPanel()
        self._results.setMinimumHeight(120)
        v_split.addWidget(self._results)
        v_split.setSizes([550, 220])
        v_split.setStretchFactor(0, 1)
        v_split.setStretchFactor(1, 0)

        rv.addWidget(v_split)
        self._outer_split.addWidget(right)
        self._outer_split.setStretchFactor(1, 1)

        root.addWidget(self._outer_split, stretch=1)

        self._results.row_selected.connect(self._on_result_selected)

    def _build_header(self) -> QFrame:
        header = QFrame()
        header.setObjectName("viewerHeader")
        hbox = QHBoxLayout(header)
        hbox.setContentsMargins(10, 0, 12, 0)
        hbox.setSpacing(0)

        self._btn_raw  = QPushButton("Raw");       self._btn_raw.setObjectName("segLeft")
        self._btn_mask = QPushButton("Mask");      self._btn_mask.setObjectName("segMid")
        self._btn_ann  = QPushButton("Annotated"); self._btn_ann.setObjectName("segRight")
        for btn in (self._btn_raw, self._btn_mask, self._btn_ann):
            btn.setCheckable(True)
            btn.setFixedHeight(26)
        self._btn_ann.setChecked(True)

        grp = QButtonGroup(self)
        grp.setExclusive(True)
        for btn in (self._btn_raw, self._btn_mask, self._btn_ann):
            grp.addButton(btn)

        self._btn_raw.clicked.connect(lambda: self._viewer.set_mode("raw"))
        self._btn_mask.clicked.connect(lambda: self._viewer.set_mode("mask"))
        self._btn_ann.clicked.connect(lambda: self._viewer.set_mode("annotated"))

        hbox.addWidget(self._btn_raw)
        hbox.addWidget(self._btn_mask)
        hbox.addWidget(self._btn_ann)

        # Batch navigation
        self._prev_btn = QPushButton("◀")
        self._next_btn = QPushButton("▶")
        self._prev_btn.setFixedWidth(28)
        self._next_btn.setFixedWidth(28)
        self._prev_btn.setFixedHeight(26)
        self._next_btn.setFixedHeight(26)
        self._prev_btn.clicked.connect(self._nav_prev)
        self._next_btn.clicked.connect(self._nav_next)
        self._nav_label = QLabel("")
        self._nav_label.setStyleSheet("color:#8c7a66; font-size:11px; margin: 0 6px;")

        self._batch_nav = QWidget()
        bnav = QHBoxLayout(self._batch_nav)
        bnav.setContentsMargins(8, 0, 0, 0)
        bnav.setSpacing(2)
        bnav.addWidget(self._prev_btn)
        bnav.addWidget(self._nav_label)
        bnav.addWidget(self._next_btn)
        self._batch_nav.setVisible(False)
        hbox.addWidget(self._batch_nav)

        hbox.addStretch()
        self._info_label = QLabel("No result loaded.")
        self._info_label.setStyleSheet("color:#9f8f7b; font-size:11px;")
        hbox.addWidget(self._info_label)

        return header

    # ── Public API ────────────────────────────────────────────────────────────

    def load_result(self, result: PipelineResult) -> None:
        """Load a single-image pipeline result (from Measure → Run Single)."""
        self._batch_entries = []
        self._batch_records = []
        self._list_panel.setVisible(False)
        self._batch_nav.setVisible(False)
        self._img_list.clear()

        self._result = result
        self._focused = None
        cuts = records_to_legacy_cuts(result.records)

        self._viewer.set_images(result.raw, result.mask, result.annotated)
        self._viewer.set_mode("annotated")
        self._btn_ann.setChecked(True)

        name = Path(result.image_record.file_path).name
        if cuts:
            self._results.show_results(name, cuts)
        else:
            self._results.show_fail(name, result.error or "No measurements")

        n = len(result.records)
        self._info_label.setText(f"{name}  ·  {n} measurement(s)")
        self.status_message.emit(f"Review: {name}  ·  {n} measurement(s)")

    def load_batch_run(self, batch_run: BatchRunRecord) -> None:
        """Load batch results for image-by-image browsing."""
        results = batch_run.output_manifest.get("results", [])
        if not results:
            self._info_label.setText("Batch produced no results.")
            return

        self._batch_entries = results
        self._batch_records = []

        self._img_list.clear()
        for entry in results:
            status = entry.get("status", "?")
            name = Path(entry.get("image_path", "?")).name
            item = QListWidgetItem(f"[{status}]  {name}")
            item.setForeground(
                Qt.GlobalColor.darkRed if status != "OK" else Qt.GlobalColor.darkGreen
            )
            self._img_list.addItem(item)

            records = []
            for m_dict in entry.get("measurements", []):
                try:
                    records.append(MeasurementRecord.from_dict(m_dict))
                except Exception:
                    pass
            self._batch_records.append(records)

        self._list_panel.setVisible(True)
        self._batch_nav.setVisible(True)

        # Load first image
        self._img_list.setCurrentRow(0)

        ok = batch_run.success_count
        total = batch_run.total_images
        self.status_message.emit(
            f"Review: batch loaded  ·  {ok}/{total} OK  —  click image to inspect"
        )

    def clear(self) -> None:
        self._result = None
        self._focused = None
        self._batch_entries = []
        self._batch_records = []
        self._results.clear()
        self._img_list.clear()
        self._list_panel.setVisible(False)
        self._batch_nav.setVisible(False)
        self._info_label.setText("No result loaded.")

    # ── Internal — batch navigation ───────────────────────────────────────────

    def _on_batch_row_changed(self, row: int) -> None:
        if row < 0 or row >= len(self._batch_entries):
            return
        self._load_batch_entry(row)
        total = len(self._batch_entries)
        self._nav_label.setText(f"{row + 1} / {total}")

    def _nav_prev(self) -> None:
        row = self._img_list.currentRow()
        if row > 0:
            self._img_list.setCurrentRow(row - 1)

    def _nav_next(self) -> None:
        row = self._img_list.currentRow()
        if row < self._img_list.count() - 1:
            self._img_list.setCurrentRow(row + 1)

    def _load_batch_entry(self, idx: int) -> None:
        entry = self._batch_entries[idx]
        records = self._batch_records[idx]
        image_path = entry.get("image_path", "")
        name = Path(image_path).name
        status = entry.get("status", "?")

        # Load raw image
        raw = None
        if image_path and Path(image_path).exists():
            try:
                from ...core.image_loader import load_grayscale
                raw = load_grayscale(image_path)
            except Exception:
                raw = None

        if raw is None:
            self._results.clear()
            self._info_label.setText(f"{name}  ·  {status}  ·  image not found")
            return

        self._focused = None
        cuts = records_to_legacy_cuts(records)

        annotated = None
        if cuts:
            try:
                annotated = draw_overlays(raw, None, cuts)
            except Exception:
                annotated = cv2.cvtColor(raw, cv2.COLOR_GRAY2BGR)
        else:
            annotated = cv2.cvtColor(raw, cv2.COLOR_GRAY2BGR)

        self._viewer.set_images(raw, None, annotated)
        self._viewer.set_mode("annotated")
        self._btn_ann.setChecked(True)

        if cuts:
            self._results.show_results(name, cuts)
        else:
            err = entry.get("error", "No measurements")
            self._results.show_fail(name, err)

        n = len(records)
        self._info_label.setText(
            f"{name}  ·  {status}  ·  {n} measurement(s)"
        )

    # ── Slots ─────────────────────────────────────────────────────────────────

    def _on_result_selected(self, cmg_id: int, col_id: int) -> None:
        self._focused = (cmg_id, col_id)
        opts = OverlayOptions(focus=self._focused)

        # Single-image mode
        if self._result is not None and not self._batch_entries:
            annotated = draw_overlays(
                self._result.raw, self._result.mask,
                records_to_legacy_cuts(self._result.records), opts,
            )
            self._viewer.set_images(self._result.raw, self._result.mask, annotated)
            self._btn_ann.setChecked(True)
            self._viewer.set_mode("annotated")
            return

        # Batch mode — re-render current entry
        row = self._img_list.currentRow()
        if row < 0 or row >= len(self._batch_entries):
            return
        entry = self._batch_entries[row]
        records = self._batch_records[row]
        image_path = entry.get("image_path", "")
        if not image_path or not Path(image_path).exists():
            return
        try:
            from ...core.image_loader import load_grayscale
            raw = load_grayscale(image_path)
            cuts = records_to_legacy_cuts(records)
            annotated = draw_overlays(raw, None, cuts, opts)
            self._viewer.set_images(raw, None, annotated)
            self._btn_ann.setChecked(True)
            self._viewer.set_mode("annotated")
        except Exception:
            pass
