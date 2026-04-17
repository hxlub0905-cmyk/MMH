"""Zoomable / pannable image viewer built on QGraphicsView.

Supports three display modes toggled via set_mode():
  "raw"        – original grayscale image
  "mask"       – binary mask overlay (cyan) on grayscale
  "annotated"  – fully annotated image with measurement lines
"""

from __future__ import annotations
import numpy as np
import cv2
from PyQt6.QtWidgets import (
    QGraphicsView, QGraphicsScene, QGraphicsPixmapItem,
    QGraphicsLineItem, QGraphicsSimpleTextItem,
)
from PyQt6.QtGui import QImage, QPixmap, QWheelEvent, QMouseEvent, QPen, QColor
from PyQt6.QtCore import Qt, QPointF, pyqtSignal


def _ndarray_to_pixmap(img: np.ndarray) -> QPixmap:
    """Convert a uint8 numpy array (gray or BGR) to QPixmap."""
    if img.ndim == 2:
        h, w = img.shape
        qimg = QImage(img.data, w, h, w, QImage.Format.Format_Grayscale8)
    else:
        h, w, _ = img.shape
        rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        qimg = QImage(rgb.data, w, h, w * 3, QImage.Format.Format_RGB888)
    return QPixmap.fromImage(qimg.copy())


class ImageViewer(QGraphicsView):
    measure_updated = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._scene = QGraphicsScene(self)
        self._pixmap_item = QGraphicsPixmapItem()
        self._scene.addItem(self._pixmap_item)
        self.setScene(self._scene)

        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self._raw: np.ndarray | None = None
        self._mask: np.ndarray | None = None
        self._annotated: np.ndarray | None = None
        self._mode: str = "raw"
        self._nm_per_pixel: float = 1.0
        self._measure_start: QPointF | None = None
        self._measure_line: QGraphicsLineItem | None = None
        self._measure_label: QGraphicsSimpleTextItem | None = None

    # ── public API ────────────────────────────────────────────────────────────

    def set_images(
        self,
        raw: np.ndarray,
        mask: np.ndarray | None = None,
        annotated: np.ndarray | None = None,
    ) -> None:
        self._raw = raw
        self._mask = mask
        self._annotated = annotated
        self._refresh()

    def set_mode(self, mode: str) -> None:
        """mode: 'raw' | 'mask' | 'annotated'"""
        self._mode = mode
        self._refresh()

    def clear(self) -> None:
        self._raw = self._mask = self._annotated = None
        self._pixmap_item.setPixmap(QPixmap())
        self._clear_measurement_overlay()

    def fit_in_view(self) -> None:
        if self._pixmap_item.pixmap().isNull():
            return
        self.fitInView(self._pixmap_item, Qt.AspectRatioMode.KeepAspectRatio)

    def set_nm_per_pixel(self, nm_per_pixel: float) -> None:
        self._nm_per_pixel = max(1e-9, nm_per_pixel)

    # ── internal ──────────────────────────────────────────────────────────────

    def _refresh(self) -> None:
        img = self._current_img()
        if img is None:
            return
        pix = _ndarray_to_pixmap(img)
        self._pixmap_item.setPixmap(pix)
        self._scene.setSceneRect(self._pixmap_item.boundingRect())

    def _current_img(self) -> np.ndarray | None:
        if self._mode == "annotated" and self._annotated is not None:
            return self._annotated
        if self._mode == "mask" and self._mask is not None:
            # cyan overlay on grayscale
            bgr = cv2.cvtColor(self._raw, cv2.COLOR_GRAY2BGR)
            overlay = bgr.copy()
            overlay[self._mask > 0] = (255, 255, 0)
            cv2.addWeighted(overlay, 0.35, bgr, 0.65, 0, bgr)
            return bgr
        return self._raw

    # ── zoom / pan ────────────────────────────────────────────────────────────

    def wheelEvent(self, event: QWheelEvent) -> None:
        factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
        self.scale(factor, factor)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        self.fit_in_view()
        super().mouseDoubleClickEvent(event)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and (
            event.modifiers() & Qt.KeyboardModifier.ShiftModifier
        ):
            scene_pos = self.mapToScene(event.position().toPoint())
            if self._measure_start is None:
                self._measure_start = scene_pos
                self._ensure_measure_items()
                if self._measure_line:
                    self._measure_line.setLine(scene_pos.x(), scene_pos.y(), scene_pos.x(), scene_pos.y())
            else:
                self._update_measurement(scene_pos, final=True)
                self._measure_start = None
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._measure_start is not None:
            scene_pos = self.mapToScene(event.position().toPoint())
            self._update_measurement(scene_pos, final=False)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def _ensure_measure_items(self) -> None:
        if self._measure_line is None:
            pen = QPen(QColor("#f29f4b"))
            pen.setWidth(2)
            self._measure_line = self._scene.addLine(0, 0, 0, 0, pen)
        if self._measure_label is None:
            self._measure_label = self._scene.addSimpleText("")
            self._measure_label.setBrush(QColor("#6b513a"))

    def _update_measurement(self, end_pt: QPointF, final: bool) -> None:
        if self._measure_start is None:
            return
        self._ensure_measure_items()
        sp = self._measure_start
        if self._measure_line:
            self._measure_line.setLine(sp.x(), sp.y(), end_pt.x(), end_pt.y())
        dx = end_pt.x() - sp.x()
        dy = end_pt.y() - sp.y()
        px_dist = float(np.hypot(dx, dy))
        nm_dist = px_dist * self._nm_per_pixel
        msg = f"Ruler: {px_dist:.3f} px  ({nm_dist:.3f} nm)"
        if self._measure_label:
            self._measure_label.setText(msg)
            self._measure_label.setPos((sp.x() + end_pt.x()) / 2 + 6, (sp.y() + end_pt.y()) / 2 - 14)
        self.measure_updated.emit(msg if not final else f"{msg}  ·  fixed (Shift+Click to remeasure)")

    def _clear_measurement_overlay(self) -> None:
        if self._measure_line is not None:
            self._scene.removeItem(self._measure_line)
            self._measure_line = None
        if self._measure_label is not None:
            self._scene.removeItem(self._measure_label)
            self._measure_label = None
        self._measure_start = None
