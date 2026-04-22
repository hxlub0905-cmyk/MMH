"""Reusable collapsible section widget for settings panels.

Usage:
    sec = CollapsibleSection("Filters", tier=2, collapsed=False)
    form = QFormLayout()
    form.addRow("Min area", spin)
    wrap = QWidget(); wrap.setLayout(form)
    sec.add_widget(wrap)
    parent_layout.addWidget(sec)
"""
from __future__ import annotations

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QPushButton, QSizePolicy
from PyQt6.QtCore import Qt


class CollapsibleSection(QWidget):
    """A titled section whose content can be collapsed/expanded.

    Visual tiers:
      1 = accent header  (top-level section, orange)
      2 = standard header  (parameter group, muted orange)
      3 = subtle header  (advanced / rarely-changed, grey)
    """

    def __init__(
        self,
        title: str,
        tier: int = 1,
        collapsed: bool = False,
        content_margins: tuple[int, int, int, int] = (8, 4, 8, 6),
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self._title = title
        self._collapsed = collapsed
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ── toggle button (acts as header) ──────────────────────────────────
        self._btn = QPushButton()
        self._btn.setObjectName(f"sectionHeader{tier}")
        self._btn.setFlat(True)
        self._btn.setCheckable(False)
        self._btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._btn.setFixedHeight(24)
        self._btn.clicked.connect(self._toggle)
        # left-align text
        self._btn.setStyleSheet(self._btn.styleSheet() + "text-align: left;")
        self._update_label()
        outer.addWidget(self._btn)

        # ── content body ────────────────────────────────────────────────────
        self._body = QWidget()
        self._body.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        self._body_layout = QVBoxLayout(self._body)
        self._body_layout.setContentsMargins(*content_margins)
        self._body_layout.setSpacing(5)
        outer.addWidget(self._body)
        self._body.setVisible(not collapsed)

    # ── public API ────────────────────────────────────────────────────────────

    @property
    def content_layout(self) -> QVBoxLayout:
        return self._body_layout

    def add_widget(self, w: QWidget) -> None:
        self._body_layout.addWidget(w)

    def set_collapsed(self, val: bool) -> None:
        self._collapsed = val
        self._body.setVisible(not val)
        self._update_label()

    def is_collapsed(self) -> bool:
        return self._collapsed

    # ── private ───────────────────────────────────────────────────────────────

    def _toggle(self) -> None:
        self.set_collapsed(not self._collapsed)

    def _update_label(self) -> None:
        arrow = "▸" if self._collapsed else "▾"
        self._btn.setText(f"  {arrow}  {self._title}")
