"""Shared delegate that paints a colored kind pill on forum-target rows.

Renders ``Subforum #304`` (blue) or ``Thread #12345`` (green) at the row's
right edge, with the row's display text on the left. Used by the Forums
settings tab and by the ForumTargetPicker popup so both lists look the same.

Items must populate two custom roles:
    item.setData(TARGET_KIND_ROLE, "subforum" | "thread")
    item.setData(TARGET_TID_ROLE, <int>)
"""

from __future__ import annotations

from PyQt6.QtCore import QRect, Qt
from PyQt6.QtGui import QColor, QFont
from PyQt6.QtWidgets import QApplication, QStyle, QStyledItemDelegate


TARGET_KIND_ROLE = Qt.ItemDataRole.UserRole + 1
TARGET_TID_ROLE = Qt.ItemDataRole.UserRole + 2


class TargetKindDelegate(QStyledItemDelegate):
    """Paints a small colored pill at the row's right edge showing
    ``Subforum #304`` or ``Thread #12345``. Slimmer than the row so the
    row height doesn't grow; color alone tells kinds apart at a glance."""

    _PILL_BG = {
        "subforum": "#2f6aa1",   # blue
        "thread":   "#3d874a",   # green
    }
    _PILL_LABEL = {"subforum": "Subforum", "thread": "Thread"}
    _PAD_H = 6
    _GAP = 8
    _RADIUS = 3

    def paint(self, painter, option, index):
        self.initStyleOption(option, index)
        # Force consistent weight; Qt's default selection rendering can
        # bold the active row, which reads as random and is unwanted.
        option.font.setBold(False)
        widget = option.widget
        style = widget.style() if widget else QApplication.style()

        option.text = ""
        style.drawControl(
            QStyle.ControlElement.CE_ItemViewItem, option, painter, widget,
        )

        kind = index.data(TARGET_KIND_ROLE) or ""
        tid = index.data(TARGET_TID_ROLE)
        kind_label = self._PILL_LABEL.get(kind, "")
        pill_text = (
            f"{kind_label} #{tid}" if kind_label and tid else kind_label
        )

        painter.save()
        rect = option.rect.adjusted(6, 0, -6, 0)
        name_right = rect.right()

        if pill_text:
            pill_font = QFont(option.font)
            pt = pill_font.pointSizeF()
            if pt > 0:
                pill_font.setPointSizeF(pt * 0.85)
            painter.setFont(pill_font)
            fm = painter.fontMetrics()
            pill_w = fm.horizontalAdvance(pill_text) + 2 * self._PAD_H
            pill_h = fm.height()
            pill_h = min(pill_h, rect.height() - 4)
            pill_y = rect.y() + (rect.height() - pill_h) // 2
            pill_rect = QRect(
                rect.right() - pill_w, pill_y, pill_w, pill_h,
            )

            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(self._PILL_BG.get(kind, "#666")))
            painter.drawRoundedRect(pill_rect, self._RADIUS, self._RADIUS)
            painter.setPen(QColor("white"))
            painter.drawText(
                pill_rect, Qt.AlignmentFlag.AlignCenter, pill_text,
            )
            name_right = pill_rect.left() - self._GAP

        painter.setFont(option.font)
        if option.state & QStyle.StateFlag.State_Selected:
            painter.setPen(option.palette.highlightedText().color())
        else:
            painter.setPen(option.palette.text().color())
        text_rect = QRect(
            rect.x(), rect.y(),
            max(0, name_right - rect.x()), rect.height(),
        )
        text = index.data(Qt.ItemDataRole.DisplayRole) or ""
        fm = painter.fontMetrics()
        elided = fm.elidedText(text, Qt.TextElideMode.ElideRight, text_rect.width())
        painter.drawText(
            text_rect,
            int(
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft
            ),
            elided,
        )
        painter.restore()


class FilledTargetKindDelegate(QStyledItemDelegate):
    """Like TargetKindDelegate but the entire row is rendered as a filled
    pill in the kind color, with white name text and a small id pill on
    the right. Used by the picker popup so each list row reads as a
    selectable chip rather than a plain text line."""

    _PILL_BG = TargetKindDelegate._PILL_BG
    _PILL_LABEL = TargetKindDelegate._PILL_LABEL
    _PAD_H = 6
    _GAP = 6
    _RADIUS = 3
    _ROW_INSET_X = 4
    _ROW_INSET_Y = 1

    def paint(self, painter, option, index):
        self.initStyleOption(option, index)
        # Force consistent weight; Qt's default selection rendering can
        # bold the active row, which reads as random and is unwanted.
        option.font.setBold(False)

        kind = index.data(TARGET_KIND_ROLE) or ""
        bg = QColor(self._PILL_BG.get(kind, "#666"))

        painter.save()
        painter.setRenderHint(painter.RenderHint.Antialiasing, True)

        row = option.rect.adjusted(
            self._ROW_INSET_X, self._ROW_INSET_Y,
            -self._ROW_INSET_X, -self._ROW_INSET_Y,
        )

        if option.state & QStyle.StateFlag.State_Selected:
            border = QColor("#ffffff")
        elif option.state & QStyle.StateFlag.State_MouseOver:
            border = bg.lighter(135)
        else:
            border = bg

        painter.setPen(border)
        painter.setBrush(bg)
        painter.drawRoundedRect(row, self._RADIUS, self._RADIUS)

        tid = index.data(TARGET_TID_ROLE)
        kind_label = self._PILL_LABEL.get(kind, "")
        id_text = f"#{tid}" if tid else ""

        inner = row.adjusted(self._PAD_H, 0, -self._PAD_H, 0)
        name_right = inner.right()

        if id_text:
            id_font = QFont(option.font)
            pt = id_font.pointSizeF()
            if pt > 0:
                id_font.setPointSizeF(pt * 0.85)
            painter.setFont(id_font)
            fm = painter.fontMetrics()
            id_w = fm.horizontalAdvance(id_text)
            id_rect = QRect(
                inner.right() - id_w, inner.y(), id_w, inner.height(),
            )
            painter.setPen(QColor(255, 255, 255, 180))
            painter.drawText(
                id_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight, id_text,
            )
            name_right = id_rect.left() - self._GAP

        painter.setFont(option.font)
        painter.setPen(QColor("white"))
        text = index.data(Qt.ItemDataRole.DisplayRole) or ""
        fm = painter.fontMetrics()
        text_rect = QRect(
            inner.x(), inner.y(),
            max(0, name_right - inner.x()), inner.height(),
        )
        elided = fm.elidedText(text, Qt.TextElideMode.ElideRight, text_rect.width())
        painter.drawText(
            text_rect,
            int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft),
            elided,
        )

        painter.restore()

    def sizeHint(self, option, index):
        size = super().sizeHint(option, index)
        size.setHeight(max(size.height(), 22))
        return size
