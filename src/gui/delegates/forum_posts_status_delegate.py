"""Pill-based delegate for the Forum Posts column.

Each forum destination that has a post gets one pill. Color encodes status.

Data roles expected on the model index:
  UserRole      — gallery path (str)
  UserRole + 1  — list[dict] of forum_post rows, each with:
                  forum_fk (int), status (str), forum_name (str)

Clicking a pill emits post_clicked(gallery_path, forum_fk).
"""

from __future__ import annotations

from PyQt6.QtCore import QEvent, QObject, QRect, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QPainter
from PyQt6.QtWidgets import QApplication, QStyle, QStyledItemDelegate, QStyleOptionViewItem


_STATUS_COLORS: dict[str, str] = {
    "posted":   "#3d874a",
    "stale":    "#e67e22",
    # queued/posting/updating are all grey by design — they are transient in-progress
    # states where the pill color signals "not yet done" without further distinction.
    "queued":   "#888888",
    "posting":  "#888888",
    "updating": "#888888",
    "failed":   "#c0392b",
}

_PILL_H = 16
_PILL_PAD_H = 6
_PILL_SPACING = 4
_CELL_PAD = 4
_RADIUS = 3


def _status_color(status: str) -> str:
    return _STATUS_COLORS.get(status, "#888888")


class _Signals(QObject):
    post_clicked = pyqtSignal(str, int)   # gallery_path, forum_fk


class ForumPostsStatusDelegate(QStyledItemDelegate):
    """Renders per-forum status pills in the forum posts column."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._signals = _Signals()

    @property
    def post_clicked(self):
        return self._signals.post_clicked

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index):
        style = option.widget.style() if option.widget else QApplication.style()
        style.drawPrimitive(
            QStyle.PrimitiveElement.PE_PanelItemViewItem, option, painter, option.widget
        )

        posts: list[dict] = index.data(Qt.ItemDataRole.UserRole + 1) or []
        if not posts:
            painter.save()
            painter.setPen(QColor("#aaaaaa"))
            f = painter.font()
            f.setPointSizeF(max(f.pointSizeF() * 0.85, 8.0))
            painter.setFont(f)
            painter.drawText(
                option.rect.adjusted(_CELL_PAD, 0, -_CELL_PAD, 0),
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                "Post →",
            )
            painter.restore()
            return

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        pill_font = QFont(painter.font())
        pt = pill_font.pointSizeF()
        if pt > 0:
            pill_font.setPointSizeF(pt * 0.82)
        painter.setFont(pill_font)
        fm = painter.fontMetrics()

        x = option.rect.x() + _CELL_PAD
        cy = option.rect.y() + (option.rect.height() - _PILL_H) // 2

        for post in posts:
            label = post.get("forum_name") or f"Forum {post.get('forum_fk', '?')}"
            bg = QColor(_status_color(post.get("status", "queued")))

            pill_w = fm.horizontalAdvance(label) + 2 * _PILL_PAD_H
            pill_rect = QRect(x, cy, pill_w, _PILL_H)

            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(bg)
            painter.drawRoundedRect(pill_rect, _RADIUS, _RADIUS)

            painter.setPen(QColor("white"))
            painter.drawText(pill_rect, Qt.AlignmentFlag.AlignCenter, label)

            x += pill_w + _PILL_SPACING

        painter.restore()

    def sizeHint(self, option, index) -> QSize:
        posts: list[dict] = index.data(Qt.ItemDataRole.UserRole + 1) or []
        n = max(1, len(posts))
        return QSize(_CELL_PAD * 2 + n * (80 + _PILL_SPACING), _PILL_H + 8)

    def editorEvent(self, event, model, option, index) -> bool:
        if event.type() == QEvent.Type.MouseButtonRelease:
            path = index.data(Qt.ItemDataRole.UserRole)
            posts: list[dict] = index.data(Qt.ItemDataRole.UserRole + 1) or []
            if path and posts:
                pos = event.position().toPoint()
                widget_font = option.widget.font() if option.widget else None
                pill_rects = self._compute_pill_rects(option.rect, posts, widget_font)
                for post, rect in zip(posts, pill_rects):
                    if rect.contains(pos):
                        self._signals.post_clicked.emit(path, post.get("forum_fk", 0))
                        return True
        return super().editorEvent(event, model, option, index)

    def _compute_pill_rects(self, cell_rect: QRect, posts: list, font: QFont | None = None) -> list[QRect]:
        # Use the same scaled font as paint() so hit-rects match rendered pill widths.
        pill_font = QFont(font) if font else QFont()
        pt = pill_font.pointSizeF()
        if pt > 0:
            pill_font.setPointSizeF(pt * 0.82)
        fm = QFontMetrics(pill_font)
        x = cell_rect.x() + _CELL_PAD
        cy = cell_rect.y() + (cell_rect.height() - _PILL_H) // 2
        rects = []
        for post in posts:
            label = post.get("forum_name") or f"Forum {post.get('forum_fk', '?')}"
            pill_w = fm.horizontalAdvance(label) + 2 * _PILL_PAD_H
            rects.append(QRect(x, cy, pill_w, _PILL_H))
            x += pill_w + _PILL_SPACING
        return rects
