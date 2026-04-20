"""LayerControlPanel — per-config visibility toggles for overlay rendering."""
from __future__ import annotations

from dataclasses import dataclass, field
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QCheckBox, QFrame,
)
from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtCore import pyqtSignal, Qt

# Default palette (BGR → displayed as RGB swapped for Qt, so store as RGB here)
_PALETTE_RGB = [
    (100, 200, 120),   # green
    (220, 90, 90),     # red
    (80, 140, 220),    # blue
    (210, 140, 60),    # orange
]


@dataclass
class LayerConfig:
    name: str
    color_bgr: tuple          # BGR for OpenCV rendering
    color_rgb: tuple          # RGB for Qt display
    cuts: list = field(default_factory=list)
    show_annot: bool = True
    show_mask: bool = True


class LayerControlPanel(QFrame):
    """Displays a row per active recipe/card with per-layer annotation and mask toggles."""

    layers_changed = pyqtSignal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("layerControlPanel")
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self._configs: list[LayerConfig] = []
        self._rows: list[dict] = []

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(6, 4, 6, 4)
        self._layout.setSpacing(2)

        header = QLabel("Layers")
        header.setStyleSheet("color:#8c7a66; font-size:10px; font-weight:bold;")
        self._layout.addWidget(header)

    # ── Public API ────────────────────────────────────────────────────────────

    def set_layers(self, names: list[str], cuts_per_layer: list[list]) -> None:
        """Populate the panel with one row per layer (name + cuts list)."""
        self._configs = []
        for i, (name, cuts) in enumerate(zip(names, cuts_per_layer)):
            rgb = _PALETTE_RGB[i % len(_PALETTE_RGB)]
            bgr = (rgb[2], rgb[1], rgb[0])
            self._configs.append(LayerConfig(name=name, color_bgr=bgr, color_rgb=rgb, cuts=cuts))
        self._rebuild_rows()

    def get_configs(self) -> list[LayerConfig]:
        return list(self._configs)

    # ── Internal ──────────────────────────────────────────────────────────────

    def _rebuild_rows(self) -> None:
        # Remove old rows
        for row_data in self._rows:
            row_data["widget"].deleteLater()
        self._rows = []

        for i, cfg in enumerate(self._configs):
            row_w = QWidget()
            row_l = QHBoxLayout(row_w)
            row_l.setContentsMargins(0, 0, 0, 0)
            row_l.setSpacing(6)

            # Color swatch
            swatch = QLabel("●")
            r, g, b = cfg.color_rgb
            swatch.setStyleSheet(f"color: rgb({r},{g},{b}); font-size:14px;")
            row_l.addWidget(swatch)

            # Layer name
            lbl = QLabel(cfg.name)
            lbl.setStyleSheet("color:#5a4a38; font-size:11px;")
            lbl.setMinimumWidth(80)
            row_l.addWidget(lbl, stretch=1)

            # Annot toggle
            annot_chk = QCheckBox("Annot")
            annot_chk.setChecked(cfg.show_annot)
            annot_chk.setStyleSheet("color:#5a4a38; font-size:10px;")
            annot_chk.stateChanged.connect(self._make_annot_handler(i))
            row_l.addWidget(annot_chk)

            # Mask toggle
            mask_chk = QCheckBox("Mask")
            mask_chk.setChecked(cfg.show_mask)
            mask_chk.setStyleSheet("color:#5a4a38; font-size:10px;")
            mask_chk.stateChanged.connect(self._make_mask_handler(i))
            row_l.addWidget(mask_chk)

            self._layout.addWidget(row_w)
            self._rows.append({"widget": row_w, "annot": annot_chk, "mask": mask_chk})

    def _make_annot_handler(self, idx: int):
        def handler(state: int) -> None:
            self._configs[idx].show_annot = bool(state)
            self.layers_changed.emit()
        return handler

    def _make_mask_handler(self, idx: int):
        def handler(state: int) -> None:
            self._configs[idx].show_mask = bool(state)
            self.layers_changed.emit()
        return handler
