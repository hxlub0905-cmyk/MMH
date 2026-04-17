"""Zoomable / pannable image viewer built on QGraphicsView.

Supports three display modes toggled via set_mode():
  "raw"        – original grayscale image
  "mask"       – binary mask overlay (cyan) on grayscale
  "annotated"  – fully annotated image with measurement lines
"""

from __future__ import annotations
import numpy as np
import cv2
from PyQt6.QtWidgets import QGraphicsView, QGraphicsScene, QGraphicsPixmapItem
from PyQt6.QtGui import QImage, QPixmap, QWheelEvent, QMouseEvent
from PyQt6.QtCore import Qt, QPointF


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

    def fit_in_view(self) -> None:
        if self._pixmap_item.pixmap().isNull():
            return
        self.fitInView(self._pixmap_item, Qt.AspectRatioMode.KeepAspectRatio)

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
