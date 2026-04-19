"""Review workspace — view and annotate measurement results (Phase A foundation)."""
from __future__ import annotations

from pathlib import Path

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QLabel, QPushButton, QGroupBox, QFormLayout, QButtonGroup,
    QFrame, QCheckBox, QSizePolicy,
)
from PyQt6.QtCore import Qt, pyqtSignal

from ..image_viewer import ImageViewer
from ..results_panel import ResultsPanel
from ...core.recipe_base import PipelineResult
from ...core.annotator import OverlayOptions, draw_overlays
from ..._compat import records_to_legacy_cuts


class ReviewWorkspace(QWidget):
    status_message = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._result: PipelineResult | None = None
        self._focused: tuple[int, int] | None = None
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        # Viewer header
        root.addWidget(self._build_header())

        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.setChildrenCollapsible(False)

        self._viewer = ImageViewer()
        splitter.addWidget(self._viewer)

        self._results = ResultsPanel()
        self._results.setMinimumHeight(120)
        splitter.addWidget(self._results)
        splitter.setSizes([550, 220])
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 0)

        root.addWidget(splitter, stretch=1)

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

        hbox.addStretch()
        self._info_label = QLabel("No result loaded.")
        self._info_label.setStyleSheet("color:#9f8f7b; font-size:11px;")
        hbox.addWidget(self._info_label)

        return header

    # ── Public API ────────────────────────────────────────────────────────────

    def load_result(self, result: PipelineResult) -> None:
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
        self.status_message.emit(f"Review loaded: {name}  ·  {n} measurement(s)")

    def clear(self) -> None:
        self._result = None
        self._focused = None
        self._results.clear()
        self._info_label.setText("No result loaded.")

    # ── Slots ─────────────────────────────────────────────────────────────────

    def _on_result_selected(self, cmg_id: int, col_id: int) -> None:
        if self._result is None:
            return
        self._focused = (cmg_id, col_id)
        opts = OverlayOptions(focus=self._focused)
        annotated = draw_overlays(
            self._result.raw, self._result.mask,
            records_to_legacy_cuts(self._result.records), opts,
        )
        self._viewer.set_images(self._result.raw, self._result.mask, annotated)
        self._btn_ann.setChecked(True)
        self._viewer.set_mode("annotated")
