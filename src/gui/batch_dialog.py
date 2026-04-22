"""Batch processing dialog with progress bar, ETA, and cancel support."""

from __future__ import annotations
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
import cv2
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QProgressBar, QPushButton,
    QTextEdit, QHBoxLayout,
)
from PyQt6.QtCore import QThread, pyqtSignal, Qt


def _process_one(args: tuple) -> dict:
    """Top-level worker function (must be picklable for multiprocessing)."""
    image_path, nm_per_pixel, gl_min, gl_max, gauss_k, morph_open_k, morph_close_k, use_clahe, min_area, cards = args
    from ..core.image_loader import load_grayscale
    from ..core.preprocessor import preprocess, PreprocessParams, apply_column_strip_mask
    from ..core.mg_detector import detect_blobs, Blob, regularize_blobs_to_columns
    from ..core.cmg_analyzer import analyze

    result: dict = {"path": str(image_path), "status": "OK", "cuts": [], "error": ""}
    try:
        img = load_grayscale(image_path)
        cards = cards or []
        import numpy as np
        mask = np.zeros_like(img, dtype=np.uint8)
        cuts = []
        cmg_offset = 0
        h, w = img.shape
        for i, card in enumerate(cards):
            axis = str(card.get("axis", "Y")).upper()
            roi = img if axis.startswith("Y") else cv2.rotate(img, cv2.ROTATE_90_CLOCKWISE)
            params = PreprocessParams(
                gl_min=int(card.get("gl_min", gl_min)),
                gl_max=int(card.get("gl_max", gl_max)),
                gauss_kernel=gauss_k,
                morph_open_k=morph_open_k,
                morph_close_k=morph_close_k,
                use_clahe=use_clahe,
                vert_erode_k=int(card.get("vert_erode_k", 0)),
                vert_erode_iter=int(card.get("vert_erode_iter", 1)),
            )
            m_roi = preprocess(roi, params)
            # Column strip masking (Strategy 1) with optional auto xproj centers (F1c)
            col_centers: list[int] = []
            edge_margin = int(card.get("col_mask_edge_margin_px", 0))
            half_w = int(card.get("col_mask_width_px", 22)) // 2
            margin = int(card.get("col_mask_margin_px", 4))
            if card.get("col_mask_enabled", False):
                start_x = int(card.get("col_mask_start_x", 0))
                pitch = int(card.get("col_mask_pitch_px", 44))
                cw = m_roi.shape[1]
                if card.get("col_mask_auto_centers", False):
                    from ..core.mg_detector import detect_mg_column_centers_pitch_phase
                    col_centers = detect_mg_column_centers_pitch_phase(
                        m_roi,
                        pitch_px=int(card.get("col_mask_pitch_px", 44)),
                        smooth_k=int(card.get("xproj_smooth_k", 5)),
                        min_height_frac=float(card.get("xproj_peak_min_frac", 0.3)),
                        edge_margin_px=edge_margin,
                    )
                if not col_centers:  # fallback to manual start_x + pitch
                    col_centers = list(range(start_x, cw, pitch)) if pitch > 0 and start_x < cw else []
                m_roi = apply_column_strip_mask(m_roi, col_centers, half_w, margin, edge_margin)
            m_ori = m_roi if axis.startswith("Y") else cv2.rotate(m_roi, cv2.ROTATE_90_COUNTERCLOCKWISE)
            mask = np.maximum(mask, m_ori)
            blobs = detect_blobs(m_roi, min_area=int(card.get("min_area", min_area)))
            # Geometric filters (0 = disabled)
            _min_ar = float(card.get("min_aspect_ratio", 0.0))
            _max_ar = float(card.get("max_aspect_ratio", 0.0))
            _min_w  = int(card.get("min_width", 0))
            _max_w  = int(card.get("max_width", 0))
            _min_h  = int(card.get("min_height", 0))
            if any([_min_ar, _max_ar, _min_w, _max_w, _min_h]):
                filtered = []
                for b in blobs:
                    ar = b.height / max(b.width, 1)
                    if _min_ar and ar < _min_ar: continue
                    if _max_ar and ar > _max_ar: continue
                    if _min_w and b.width < _min_w: continue
                    if _max_w and b.width > _max_w: continue
                    if _min_h and b.height < _min_h: continue
                    filtered.append(b)
                blobs = filtered
            # Pitch Grid Regularization: snap blobs onto layout grid, normalize X bounds
            if card.get("col_mask_enabled", False) and card.get("col_mask_regularize", False) and col_centers:
                half_w = int(card.get("col_mask_width_px", 22)) // 2
                tol    = int(card.get("col_mask_pitch_tol_px", 5))
                norm_x = bool(card.get("col_mask_normalize_x", True))
                blobs  = regularize_blobs_to_columns(blobs, col_centers, half_w, tol, norm_x)
            if axis.startswith("X"):
                blobs = [Blob(
                    label=b.label,
                    x0=b.y0, y0=(h - 1) - (b.x1 - 1),
                    x1=b.y1, y1=(h - 1) - b.x0 + 1,
                    area=b.area, cx=b.cy, cy=(h - 1) - b.cx
                ) for b in blobs]
            c = analyze(blobs, nm_per_pixel)
            if card.get("range_enabled", False):
                c = _filter_by_range(
                    c,
                    float(card.get("min_line_px", 0)),
                    float(card.get("max_line_px", 0)),
                )
            for cut in c:
                cut.cmg_id += cmg_offset
                for m in cut.measurements:
                    m.cmg_id = cut.cmg_id
                    m.col_id = i * 1000 + m.col_id
                    m.axis = "X" if axis.startswith("X") else "Y"
                    m.state_name = str(card.get("name", f"Measure {i+1}"))
            cmg_offset += len(c)
            cuts.extend(c)

        if not cuts:
            result["status"] = "FAIL"
            result["error"] = "No structures detected"
        else:
            # Serialise cuts to plain dicts (not dataclasses) for cross-process transport
            result["cuts"] = _serialise_cuts(cuts)
            result["mask_shape"] = list(mask.shape)
    except Exception as exc:
        result["status"] = "FAIL"
        result["error"] = str(exc)
    return result


def _filter_by_range(cuts, min_px: float, max_px: float) -> list:
    """Keep only measurements whose cd_px falls within [min_px, max_px] (0 = disabled)."""
    from ..core.cmg_analyzer import CMGCut, _flag_top3
    filtered = []
    for cut in cuts:
        kept = [
            m for m in cut.measurements
            if (min_px <= 0 or m.cd_px >= min_px)
            and (max_px <= 0 or m.cd_px <= max_px)
        ]
        if kept:
            filtered.append(CMGCut(cmg_id=cut.cmg_id, measurements=kept))
    for cut in filtered:
        _flag_top3(cut.measurements)
    return filtered


def _serialise_cuts(cuts) -> list:
    out = []
    for cut in cuts:
        measurements = []
        for m in cut.measurements:
            measurements.append({
                "cmg_id": m.cmg_id,
                "col_id": m.col_id,
                "y_cd_px": m.cd_px,
                "y_cd_nm": m.cd_nm,
                "flag": m.flag,
                "axis": m.axis,
                "state_name": m.state_name,
                "upper_bbox": (m.upper_blob.x0, m.upper_blob.y0, m.upper_blob.x1, m.upper_blob.y1),
                "lower_bbox": (m.lower_blob.x0, m.lower_blob.y0, m.lower_blob.x1, m.lower_blob.y1),
            })
        out.append({"cmg_id": cut.cmg_id, "measurements": measurements})
    return out


class _BatchWorker(QThread):
    progress = pyqtSignal(int, int, str)   # done, total, current_file
    finished = pyqtSignal(list)            # list of result dicts

    def __init__(self, image_paths: list[Path], params: dict, max_workers: int):
        super().__init__()
        self._paths = image_paths
        self._params = params
        self._max_workers = max_workers
        self.cancelled = False

    def run(self) -> None:
        results = []
        total = len(self._paths)
        p = self._params

        self.progress.emit(0, total, f"Preparing {total} job(s)…")

        args_list = [
            (
                path,
                p["nm_per_pixel"],
                p["gl_min"],
                p["gl_max"],
                p["gauss_k"],
                p["morph_open_k"],
                p["morph_close_k"],
                p["use_clahe"],
                p["min_area"],
                p.get("cards", []),
            )
            for path in self._paths
        ]

        with ProcessPoolExecutor(max_workers=self._max_workers) as pool:
            future_map = {pool.submit(_process_one, args): args[0] for args in args_list}
            self.progress.emit(0, total, f"Submitted {total} job(s), waiting for results…")
            done = 0
            for future in as_completed(future_map):
                if self.cancelled:
                    pool.shutdown(wait=False, cancel_futures=True)
                    break
                done += 1
                result = future.result()
                results.append(result)
                self.progress.emit(done, total, Path(result["path"]).name)

        self.finished.emit(results)


class BatchDialog(QDialog):
    batch_done = pyqtSignal(list)   # forwarded to main window

    def __init__(self, image_paths: list[Path], params: dict, max_workers: int, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Batch Processing")
        self.setMinimumWidth(500)
        self._worker = _BatchWorker(image_paths, params, max_workers)
        self._start_time = time.time()

        layout = QVBoxLayout(self)

        self._lbl_current = QLabel("Initializing…")
        layout.addWidget(self._lbl_current)

        self._progress = QProgressBar()
        self._progress.setRange(0, len(image_paths))
        layout.addWidget(self._progress)

        self._lbl_eta = QLabel("ETA: —")
        layout.addWidget(self._lbl_eta)

        self._log = QTextEdit()
        self._log.setReadOnly(True)
        self._log.setMaximumHeight(120)
        layout.addWidget(self._log)

        btn_row = QHBoxLayout()
        self._cancel_btn = QPushButton("Cancel")
        self._cancel_btn.clicked.connect(self._cancel)
        btn_row.addStretch()
        btn_row.addWidget(self._cancel_btn)
        layout.addLayout(btn_row)

        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_finished)
        self._worker.start()

    def _on_progress(self, done: int, total: int, name: str) -> None:
        self._progress.setValue(done)
        self._lbl_current.setText(f"[{done}/{total}]  {name}")
        elapsed = time.time() - self._start_time
        if done > 0:
            eta = elapsed / done * (total - done)
            self._lbl_eta.setText(f"ETA: {eta:.0f}s")
        self._log.append(name)

    def _on_finished(self, results: list) -> None:
        self._cancel_btn.setText("Close")
        self._lbl_current.setText("Done.")
        self.batch_done.emit(results)
        self.accept()

    def _cancel(self) -> None:
        if self._worker.isRunning():
            self._worker.cancelled = True
            self._worker.wait(2000)
        self.reject()
