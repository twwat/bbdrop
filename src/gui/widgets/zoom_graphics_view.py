"""Reusable QGraphicsView with scroll-wheel zoom and drag pan."""
from PyQt6.QtWidgets import QGraphicsView
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QWheelEvent


class ZoomGraphicsView(QGraphicsView):
    """Graphics view with scroll-wheel zoom and click-drag pan."""

    zoom_changed = pyqtSignal(float)

    ZOOM_MIN = 0.05
    ZOOM_MAX = 10.0
    ZOOM_FACTOR = 1.15

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setRenderHints(self.renderHints())
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._current_zoom = 1.0

    def wheelEvent(self, event: QWheelEvent):
        if event.angleDelta().y() > 0:
            factor = self.ZOOM_FACTOR
        else:
            factor = 1.0 / self.ZOOM_FACTOR

        new_zoom = self._current_zoom * factor
        if new_zoom < self.ZOOM_MIN or new_zoom > self.ZOOM_MAX:
            return

        self.scale(factor, factor)
        self._current_zoom = new_zoom
        self.zoom_changed.emit(self._current_zoom)

    def zoom_to_fit(self):
        scene = self.scene()
        if scene is None or scene.sceneRect().isEmpty():
            return
        self.resetTransform()
        self.fitInView(scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)
        self._current_zoom = self.transform().m11()
        self.zoom_changed.emit(self._current_zoom)

    def set_zoom(self, zoom: float):
        zoom = max(self.ZOOM_MIN, min(self.ZOOM_MAX, zoom))
        self.resetTransform()
        self.scale(zoom, zoom)
        self._current_zoom = zoom
        self.zoom_changed.emit(self._current_zoom)
