"""Main application window — 3-panel dark UI."""

from __future__ import annotations
import os
import shutil
from pathlib import Path
from datetime import datetime
import numpy as np
import cv2

from PyQt6.QtWidgets import (
    QMainWindow, QSplitter, QFileDialog, QMessageBox,
    QStatusBar, QWidget, QVBoxLayout, QHBoxLayout,
    QFrame, QLabel, QPushButton, QButtonGroup, QCheckBox,
    QSizePolicy,
)
from PyQt6.QtCore import Qt, QTimer, pyqtSlot
from PyQt6.QtGui import QAction, QFont

from .file_tree_panel import FileTreePanel
from .image_viewer import ImageViewer
from .control_panel import ControlPanel
from .results_panel import ResultsPanel
from .batch_dialog import BatchDialog
from .batch_review_dialog import BatchReviewDialog
from .styles import STYLE

from ..core.image_loader import load_grayscale, scan_folder
from ..core.preprocessor import preprocess, PreprocessParams
from ..core.mg_detector import detect_blobs, Blob
from ..core.cmg_analyzer import analyze
from ..core.annotator import draw_overlays, OverlayOptions


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("SEM MM — Massive Measurement")
        self.resize(1400, 860)
        self.setMinimumSize(900, 600)
        self.setStyleSheet(STYLE)

        self._current_path: Path | None = None
        self._current_raw  = None
        self._current_mask = None
        self._current_profile_masks: list = []
        self._active_state_filter: str = ""
        self._current_cuts: list = []
        self._batch_results: list = []
        self._last_batch_input: Path | None = None
        self._focused_measurement: tuple[int, int] | None = None

        self._preview_timer = QTimer()
        self._preview_timer.setSingleShot(True)
        self._preview_timer.timeout.connect(self._run_preview)

        self._build_ui()
        self._connect_signals()
        self._viewer.set_nm_per_pixel(self._ctrl.get_nm_per_pixel())

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        self._build_menubar()

        # ── Root splitter: Left | Center | Right ──────────────────────────────
        root_splitter = QSplitter(Qt.Orientation.Horizontal)
        root_splitter.setChildrenCollapsible(False)
        self.setCentralWidget(root_splitter)

        root_splitter.addWidget(self._make_left_panel())
        root_splitter.addWidget(self._make_center_panel())
        root_splitter.addWidget(self._ctrl)   # right panel IS the control panel

        root_splitter.setSizes([210, 960, 250])
        root_splitter.setStretchFactor(0, 0)
        root_splitter.setStretchFactor(1, 1)
        root_splitter.setStretchFactor(2, 0)

        # ── Status bar ────────────────────────────────────────────────────────
        sb = QStatusBar()
        self.setStatusBar(sb)
        sb.showMessage("Ready — open a folder to begin.")

    def _build_menubar(self) -> None:
        mb = self.menuBar()

        fm = mb.addMenu("&File")
        self._act_open = QAction("Open Folder…  Ctrl+O", self)
        self._act_open.setShortcut("Ctrl+O")
        fm.addAction(self._act_open)
        fm.addSeparator()
        fm.addAction(QAction("Quit  Ctrl+Q", self, shortcut="Ctrl+Q",
                             triggered=self.close))

        rm = mb.addMenu("&Run")
        self._act_single = QAction("Run Single  F5", self)
        self._act_single.setShortcut("F5")
        rm.addAction(self._act_single)
        self._act_batch = QAction("Run Batch…  F6", self)
        self._act_batch.setShortcut("F6")
        rm.addAction(self._act_batch)

        em = mb.addMenu("&Export")
        self._act_export = QAction("Export Results…  Ctrl+E", self)
        self._act_export.setShortcut("Ctrl+E")
        em.addAction(self._act_export)

        vm = mb.addMenu("&View")
        self._act_fullscreen = QAction("Toggle Full Screen  F11", self)
        self._act_fullscreen.setShortcut("F11")
        vm.addAction(self._act_fullscreen)

    def _make_left_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("leftPanel")
        panel.setMinimumWidth(160)
        panel.setMaximumWidth(300)

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        title = QLabel("FILES")
        title.setObjectName("panelTitle")
        layout.addWidget(title)

        self._file_tree = FileTreePanel()
        layout.addWidget(self._file_tree)

        return panel

    def _make_center_panel(self) -> QWidget:
        center = QWidget()
        vbox = QVBoxLayout(center)
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.setSpacing(0)

        # ── viewer header ─────────────────────────────────────────────────────
        header = QFrame()
        header.setObjectName("viewerHeader")
        hbox = QHBoxLayout(header)
        hbox.setContentsMargins(10, 0, 12, 0)
        hbox.setSpacing(0)

        # Segmented mode buttons
        self._btn_raw  = QPushButton("Raw")
        self._btn_mask = QPushButton("Mask")
        self._btn_ann  = QPushButton("Annotated")
        self._btn_raw.setObjectName("segLeft")
        self._btn_mask.setObjectName("segMid")
        self._btn_ann.setObjectName("segRight")
        for btn in (self._btn_raw, self._btn_mask, self._btn_ann):
            btn.setCheckable(True)
            btn.setFixedHeight(26)
        self._btn_raw.setChecked(True)

        self._view_group = QButtonGroup(self)
        self._view_group.setExclusive(True)
        for btn in (self._btn_raw, self._btn_mask, self._btn_ann):
            self._view_group.addButton(btn)

        hbox.addWidget(self._btn_raw)
        hbox.addWidget(self._btn_mask)
        hbox.addWidget(self._btn_ann)

        # ── overlay options (visible only in Annotated mode) ──────────────────
        sep = QLabel("  |  ")
        sep.setStyleSheet("color: #d8cbb8;")
        hbox.addWidget(sep)

        self._overlay_widget = QWidget()
        self._overlay_widget.setVisible(False)
        ov_hbox = QHBoxLayout(self._overlay_widget)
        ov_hbox.setContentsMargins(0, 0, 0, 0)
        ov_hbox.setSpacing(12)

        self._chk_lines  = _ov_chk("Lines",   checked=True)
        self._chk_labels = _ov_chk("Values",  checked=True)
        self._chk_boxes  = _ov_chk("Boxes",   checked=False)
        self._chk_legend = _ov_chk("Legend", checked=True)
        for chk in (self._chk_lines, self._chk_labels, self._chk_boxes, self._chk_legend):
            chk.stateChanged.connect(self._refresh_annotated)
            ov_hbox.addWidget(chk)

        hbox.addWidget(self._overlay_widget)
        hbox.addStretch()

        self._zoom_label = QLabel("Double-click to fit")
        self._zoom_label.setStyleSheet("color: #9f8f7b; font-size: 11px;")
        hbox.addWidget(self._zoom_label)

        vbox.addWidget(header)

        # ── vertical splitter: image viewer | results table ───────────────────
        v_split = QSplitter(Qt.Orientation.Vertical)
        v_split.setChildrenCollapsible(False)

        self._viewer = ImageViewer()
        v_split.addWidget(self._viewer)

        self._results = ResultsPanel()
        self._results.setMinimumHeight(100)
        v_split.addWidget(self._results)

        v_split.setSizes([600, 200])
        v_split.setStretchFactor(0, 1)
        v_split.setStretchFactor(1, 0)

        vbox.addWidget(v_split, stretch=1)

        # control panel (right dock) — instantiate here so it exists before
        # _build_ui() needs to reference it
        self._ctrl = ControlPanel()
        self._ctrl.setMinimumWidth(230)
        self._ctrl.setMaximumWidth(310)

        return center

    def _connect_signals(self) -> None:
        self._act_open.triggered.connect(self._open_folder)
        self._act_single.triggered.connect(self._run_single)
        self._act_batch.triggered.connect(self._run_batch)
        self._act_export.triggered.connect(self._export)
        self._act_fullscreen.triggered.connect(self._toggle_fullscreen)

        self._file_tree.file_selected.connect(self._on_file_selected)
        self._ctrl.params_changed.connect(self._on_params_changed)
        self._ctrl.run_single.connect(self._run_single)
        self._ctrl.run_batch.connect(self._run_batch)
        self._results.row_selected.connect(self._on_result_selected)
        self._results.state_filter_changed.connect(self._on_state_filter_changed)

        self._btn_raw.clicked.connect(self._on_mode_raw)
        self._btn_mask.clicked.connect(self._on_mode_mask)
        self._btn_ann.clicked.connect(self._on_mode_ann)
        self._viewer.measure_updated.connect(self._on_measure_updated)

    # ── slots ─────────────────────────────────────────────────────────────────

    @pyqtSlot()
    def _open_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Select SEM Image Folder")
        if folder:
            self._file_tree.set_root(folder)
            self.statusBar().showMessage(f"Folder: {folder}")

    @pyqtSlot(Path)
    def _on_file_selected(self, path: Path) -> None:
        self._current_path = path
        try:
            self._current_raw = load_grayscale(path)
        except Exception as exc:
            self.statusBar().showMessage(f"Load error: {exc}")
            return
        self._current_mask = None
        self._current_profile_masks = []
        self._current_cuts = []
        self._viewer.set_images(self._current_raw, profile_masks=self._current_profile_masks)
        self._viewer.fit_in_view()
        self._results.clear()
        self.statusBar().showMessage(str(path))
        self._schedule_preview()

    # ── mode switch helpers ───────────────────────────────────────────────────

    def _on_mode_raw(self) -> None:
        self._overlay_widget.setVisible(False)
        self._focused_measurement = None
        self._viewer.set_mode("raw")

    def _on_mode_mask(self) -> None:
        self._overlay_widget.setVisible(False)
        self._focused_measurement = None
        self._viewer.set_mode("mask")

    def _on_mode_ann(self) -> None:
        self._overlay_widget.setVisible(True)
        self._viewer.set_mode("annotated")

    def _on_params_changed(self, _nm: float, _p) -> None:
        self._viewer.set_nm_per_pixel(self._ctrl.get_nm_per_pixel())
        self._schedule_preview()

    def _schedule_preview(self) -> None:
        self._preview_timer.start(180)

    def _run_preview(self) -> None:
        if self._current_raw is None:
            return
        try:
            mask, _, profile_masks = self._analyze_with_cards(self._current_raw, preview_only=True)
        except Exception:
            return
        self._current_mask = mask
        self._current_profile_masks = profile_masks
        annotated = self._make_annotated()
        self._viewer.set_images(self._current_raw, mask, annotated, profile_masks=self._current_profile_masks)

    def _get_overlay_opts(self) -> OverlayOptions:
        return OverlayOptions(
            show_lines=self._chk_lines.isChecked(),
            show_labels=self._chk_labels.isChecked(),
            show_boxes=self._chk_boxes.isChecked(),
            show_legend=self._chk_legend.isChecked(),
            focus=self._focused_measurement,
        )

    def _make_annotated(self):
        if self._current_mask is not None and self._current_cuts:
            cuts = self._filtered_cuts_by_state(self._current_cuts, self._active_state_filter)
            return draw_overlays(self._current_raw, self._current_mask,
                                 cuts, self._get_overlay_opts())
        return None

    def _refresh_annotated(self) -> None:
        """Re-render annotated layer when overlay checkboxes change."""
        if self._current_raw is None or not self._current_cuts:
            return
        annotated = self._make_annotated()
        self._viewer.set_images(self._current_raw, self._current_mask, annotated, profile_masks=self._current_profile_masks)

    @pyqtSlot(int, int)
    def _on_result_selected(self, cmg_id: int, col_id: int) -> None:
        self._focused_measurement = (cmg_id, col_id)
        self._btn_ann.setChecked(True)
        self._overlay_widget.setVisible(True)
        self._viewer.set_mode("annotated")
        self._refresh_annotated()

    @pyqtSlot(str)
    def _on_state_filter_changed(self, state_name: str) -> None:
        self._active_state_filter = state_name
        self._viewer.set_mask_state_filter(state_name)
        self._refresh_annotated()

    @pyqtSlot()
    def _run_single(self) -> None:
        if self._current_raw is None:
            QMessageBox.information(self, "No image", "Select an image first.")
            return
        if not self._ctrl.get_measurement_cards():
            QMessageBox.information(self, "No measurements", "Please add at least one measurement profile.")
            return
        try:
            mask, cuts, profile_masks = self._analyze_with_cards(self._current_raw, preview_only=False)
        except Exception as exc:
            QMessageBox.critical(self, "Processing error", str(exc))
            return

        self._current_mask = mask
        self._current_profile_masks = profile_masks
        self._current_cuts = cuts
        self._focused_measurement = None
        annotated = (draw_overlays(self._current_raw, mask, cuts, self._get_overlay_opts())
                     if cuts else None)
        self._viewer.set_images(self._current_raw, mask, annotated, profile_masks=self._current_profile_masks)

        name = self._current_path.name if self._current_path else "image"
        if cuts:
            self._results.show_results(name, cuts)
            self._btn_ann.setChecked(True)
            self._viewer.set_mode("annotated")
        else:
            self._results.show_fail(name, "No CMG cuts detected")

        n_meas = sum(len(c.measurements) for c in cuts)
        self.statusBar().showMessage(
            f"{name}  ·  {len(cuts)} CMG cut(s)  ·  {n_meas} measurement(s)"
        )

    @pyqtSlot()
    def _run_batch(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Select Input Folder")
        if not folder:
            return
        paths = scan_folder(folder)
        self._last_batch_input = Path(folder)
        if not paths:
            QMessageBox.information(self, "No images", "No supported images found.")
            return

        params = self._ctrl.get_preprocess_params()
        batch_params = {
            "nm_per_pixel": self._ctrl.get_nm_per_pixel(),
            "gl_min": params.gl_min,
            "gl_max": params.gl_max,
            "gauss_k": params.gauss_kernel,
            "morph_open_k": params.morph_open_k,
            "morph_close_k": params.morph_close_k,
            "use_clahe": params.use_clahe,
            "min_area": self._ctrl.get_min_area(),
            "cards": self._ctrl.get_measurement_cards(),
        }
        workers = max(1, (os.cpu_count() or 2) - 1)
        dlg = BatchDialog(paths, batch_params, workers, parent=self)
        dlg.batch_done.connect(self._on_batch_done)
        dlg.exec()

    @pyqtSlot(list)
    def _on_batch_done(self, results: list) -> None:
        self._batch_results = results
        n_ok   = sum(1 for r in results if r["status"] == "OK")
        n_fail = len(results) - n_ok
        n_meas = sum(
            sum(len(c["measurements"]) for c in r.get("cuts", []))
            for r in results
        )
        self._results.update_summary(len(results), n_meas, n_fail)
        self.statusBar().showMessage(
            f"Batch done  ·  {len(results)} images  ·  {n_meas} measurements  ·  {n_fail} failures"
        )
        QTimer.singleShot(0, self._open_batch_review)

    def _open_batch_review(self) -> None:
        viewer = BatchReviewDialog(self._batch_results, annotated_dir=None, parent=self)
        viewer.export_requested.connect(self._export)
        viewer.report_requested.connect(self._quick_report)
        viewer.export_annotated_requested.connect(self._export_annotated_from_viewer)
        viewer.exec()

    @pyqtSlot()
    def _export(self) -> None:
        if not self._batch_results and not self._current_cuts:
            QMessageBox.information(self, "Nothing to export", "Run single or batch first.")
            return
        out_dir = QFileDialog.getExistingDirectory(self, "Select Output Directory")
        if not out_dir:
            return
        nm_px = self._ctrl.get_nm_per_pixel()
        if self._batch_results:
            data = self._batch_results
        else:
            from .batch_dialog import _serialise_cuts
            data = [{
                "path": str(self._current_path or ""),
                "status": "OK" if self._current_cuts else "FAIL",
                "cuts": _serialise_cuts(self._current_cuts),
                "error": "",
            }]
        self._do_export(data, Path(out_dir), nm_px)
        QMessageBox.information(self, "Export complete",
                                f"Results saved to:\n{out_dir}")

    @pyqtSlot()
    def _quick_report(self) -> None:
        if not self._batch_results and not self._current_cuts:
            QMessageBox.information(self, "Nothing to report", "Run single or batch first.")
            return
        base = (self._current_path.parent if self._current_path else Path.cwd())
        out_dir = base / f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        out_dir.mkdir(parents=True, exist_ok=True)
        nm_px = self._ctrl.get_nm_per_pixel()
        if self._batch_results:
            data = self._batch_results
        else:
            from .batch_dialog import _serialise_cuts
            data = [{
                "path": str(self._current_path or ""),
                "status": "OK" if self._current_cuts else "FAIL",
                "cuts": _serialise_cuts(self._current_cuts),
                "error": "",
            }]
        self._do_export(data, out_dir, nm_px)
        QMessageBox.information(self, "One-click report complete",
                                f"Report package saved to:\n{out_dir}")

    @pyqtSlot(dict)
    def _export_annotated_from_viewer(self, opts_dict: dict) -> None:
        if not self._batch_results:
            QMessageBox.information(self, "No batch results", "Run batch first.")
            return
        out_dir = QFileDialog.getExistingDirectory(self, "Select Annotated Output Folder")
        if not out_dir:
            return
        opts = OverlayOptions(**opts_dict)
        self._export_annotated_images(self._batch_results, Path(out_dir), opts)
        QMessageBox.information(self, "Batch Output Exported", f"Saved to:\n{out_dir}")

    @pyqtSlot(str)
    def _on_measure_updated(self, text: str) -> None:
        self.statusBar().showMessage(text)

    @pyqtSlot()
    def _toggle_fullscreen(self) -> None:
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()
        self._viewer.fit_in_view()

    def _do_export(self, results: list, out_path: Path, nm_px: float) -> None:
        import cv2
        from ..output.csv_exporter import export_csv
        from ..output.excel_exporter import export_excel
        from ..output.json_exporter import export_json
        from ..output.report_generator import generate_report

        ts      = datetime.now().strftime("%Y%m%d_%H%M%S")
        ann_dir = out_path / "annotated"
        ann_dir.mkdir(exist_ok=True)
        fail_dir = out_path / "_failed"

        params   = self._ctrl.get_preprocess_params()
        min_area = self._ctrl.get_min_area()

        for r in results:
            img_path = Path(r["path"])
            if r["status"] == "FAIL":
                fail_dir.mkdir(exist_ok=True)
                if img_path.exists():
                    shutil.copy(img_path, fail_dir / img_path.name)
                continue
            try:
                raw   = load_grayscale(img_path)
                mask  = preprocess(raw, params)
                blobs = detect_blobs(mask, min_area=min_area)
                cuts  = analyze(blobs, nm_px)
                ann   = draw_overlays(raw, mask, cuts)
                cv2.imwrite(str(ann_dir / (img_path.stem + "_annotated.png")), ann)
            except Exception:
                pass

        export_csv(results,   out_path / f"{ts}_measurements.csv",  nm_px)
        export_excel(results, out_path / f"{ts}_measurements.xlsx", nm_px)
        export_json(results,  out_path / f"{ts}_measurements.json", nm_px)
        generate_report(results, out_path / f"{ts}_report.html",    nm_px)

    def _export_annotated_images(self, results: list, out_dir: Path, opts: OverlayOptions) -> None:
        import cv2
        out_dir.mkdir(parents=True, exist_ok=True)
        params = self._ctrl.get_preprocess_params()
        min_area = self._ctrl.get_min_area()
        nm_px = self._ctrl.get_nm_per_pixel()
        for r in results:
            if r.get("status") != "OK":
                continue
            img_path = Path(r["path"])
            try:
                raw = load_grayscale(img_path)
                mask = preprocess(raw, params)
                blobs = detect_blobs(mask, min_area=min_area)
                cuts = analyze(blobs, nm_px)
                ann = draw_overlays(raw, mask, cuts, opts)
                cv2.imwrite(str(out_dir / f"{img_path.stem}_annotated.png"), ann)
            except Exception:
                continue

    def _analyze_with_cards(self, raw: np.ndarray, preview_only: bool) -> tuple[np.ndarray, list, list]:
        cards = self._ctrl.get_measurement_cards()
        base_params = self._ctrl.get_preprocess_params()
        min_area = self._ctrl.get_min_area()
        nm_px = self._ctrl.get_nm_per_pixel()
        full_mask = np.zeros_like(raw, dtype=np.uint8)
        cuts_all = []
        profile_masks = []
        cmg_offset = 0
        if not cards:
            return full_mask, cuts_all, profile_masks

        for ci, card in enumerate(cards):
            axis = card.get("axis", "Y")
            roi = raw if axis == "Y" else cv2.rotate(raw, cv2.ROTATE_90_CLOCKWISE)
            params = PreprocessParams(
                gl_min=card["gl_min"],
                gl_max=card["gl_max"],
                gauss_kernel=base_params.gauss_kernel,
                morph_open_k=base_params.morph_open_k,
                morph_close_k=base_params.morph_close_k,
                use_clahe=base_params.use_clahe,
                clahe_clip=base_params.clahe_clip,
                clahe_grid=base_params.clahe_grid,
            )
            mask_local = preprocess(roi, params)
            mask_ori = mask_local if axis == "Y" else cv2.rotate(mask_local, cv2.ROTATE_90_COUNTERCLOCKWISE)
            full_mask = np.maximum(full_mask, mask_ori)
            palette = [(255, 170, 70), (110, 180, 250), (120, 210, 160), (220, 130, 220), (120, 220, 230)]
            profile_masks.append((mask_ori, palette[ci % len(palette)], card.get("name", f"S{ci+1}")))
            if preview_only:
                continue
            blobs = detect_blobs(mask_local, min_area=card.get("min_area", min_area))
            if axis == "X":
                blobs = [self._blob_rot_to_ori(b, raw.shape[0]) for b in blobs]
            cuts = analyze(blobs, nm_px)
            for c in cuts:
                c.cmg_id += cmg_offset
                for m in c.measurements:
                    m.cmg_id = c.cmg_id
                    m.col_id = ci * 1000 + m.col_id
                    m.axis = axis
                    m.state_name = card.get("name", f"Measure {ci+1}")
            cmg_offset += len(cuts)
            cuts_all.extend(cuts)
        return full_mask, cuts_all, profile_masks

    @staticmethod
    def _filtered_cuts_by_state(cuts: list, state_name: str) -> list:
        if not state_name:
            return cuts
        filtered = []
        for cut in cuts:
            keep = [m for m in cut.measurements if getattr(m, "state_name", "") == state_name]
            if keep:
                cut_new = type(cut)(cmg_id=cut.cmg_id, measurements=keep)
                filtered.append(cut_new)
        return filtered

    @staticmethod
    def _blob_rot_to_ori(b: Blob, orig_h: int) -> Blob:
        pts = [
            (b.x0, b.y0),
            (b.x1 - 1, b.y0),
            (b.x0, b.y1 - 1),
            (b.x1 - 1, b.y1 - 1),
        ]
        ox = [py for _, py in pts]
        oy = [orig_h - 1 - px for px, _ in pts]
        return Blob(
            label=b.label,
            x0=min(ox),
            y0=min(oy),
            x1=max(ox) + 1,
            y1=max(oy) + 1,
            area=b.area,
            cx=b.cy,
            cy=(orig_h - 1) - b.cx,
        )


# ── module-level helpers ──────────────────────────────────────────────────────

def _ov_chk(text: str, checked: bool = True) -> QCheckBox:
    chk = QCheckBox(text)
    chk.setChecked(checked)
    chk.setStyleSheet(
        "QCheckBox { color:#8c7a66; font-size:11px; spacing:4px; }"
        "QCheckBox::indicator { width:12px; height:12px; }"
    )
    return chk
