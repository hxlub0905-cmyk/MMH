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
        self._profile_masks: list[tuple[np.ndarray, tuple[int, int, int], str]] = []
        self._mask_state_filter: str = ""
        self._mode: str = "raw"
        self._nm_per_pixel: float = 1.0
        self._measure_start: QPointF | None = None
        self._measure_line: QGraphicsLineItem | None = None
        self._measure_label: QGraphicsSimpleTextItem | None = None
        self._ruler_mode: bool = False

    # ── public API ────────────────────────────────────────────────────────────

    def set_images(
        self,
        raw: np.ndarray,
        mask: np.ndarray | None = None,
        annotated: np.ndarray | None = None,
        profile_masks: list[tuple[np.ndarray, tuple[int, int, int], str]] | None = None,
    ) -> None:
        self._raw = raw
        self._mask = mask
        self._annotated = annotated
        self._profile_masks = profile_masks or []
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

    def set_mask_state_filter(self, state_name: str) -> None:
        self._mask_state_filter = state_name
        self._refresh()

    def set_ruler_mode(self, enabled: bool) -> None:
        self._ruler_mode = enabled
        if enabled:
            self.setCursor(Qt.CursorShape.CrossCursor)
            self.setDragMode(QGraphicsView.DragMode.NoDrag)
        else:
            self.setCursor(Qt.CursorShape.ArrowCursor)
            self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
            self._clear_measurement_overlay()
            self.measure_updated.emit("")

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
            bgr = cv2.cvtColor(self._raw, cv2.COLOR_GRAY2BGR)
            overlay = bgr.copy()
            if self._profile_masks:
                for pmask, col, _name in self._profile_masks:
                    if self._mask_state_filter and _name != self._mask_state_filter:
                        continue
                    overlay[pmask > 0] = col
            else:
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
        is_ruler_click = event.button() == Qt.MouseButton.LeftButton and (
            self._ruler_mode or (event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        )
        if is_ruler_click:
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
        dx = abs(end_pt.x() - sp.x())
        dy = abs(end_pt.y() - sp.y())
        px_dist = float(np.hypot(dx, dy))
        nm_dist = px_dist * self._nm_per_pixel
        msg = f"dx={dx:.0f}  dy={dy:.0f}  |d|={px_dist:.1f} px  ({nm_dist:.1f} nm)"
        if self._measure_label:
            self._measure_label.setText(msg)
            mid_x = (sp.x() + end_pt.x()) / 2
            mid_y = (sp.y() + end_pt.y()) / 2
            self._measure_label.setPos(mid_x + 6, mid_y - 14)
        hint = "  ·  Click to reset" if self._ruler_mode else "  ·  Shift+Click to remeasure"
        self.measure_updated.emit(msg if not final else f"{msg}{hint}")

    def _clear_measurement_overlay(self) -> None:
        if self._measure_line is not None:
            self._scene.removeItem(self._measure_line)
            self._measure_line = None
        if self._measure_label is not None:
            self._scene.removeItem(self._measure_label)
            self._measure_label = None
        self._measure_start = None
