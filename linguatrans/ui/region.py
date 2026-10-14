"""框选遮罩：全屏半透明蒙层，让用户拖出要识别的矩形。

用户在屏幕上拖出一个框，松开鼠标即确定；按 Esc 取消。
选中的矩形会换算成屏幕绝对坐标，交给屏幕截取模块。
"""

from __future__ import annotations

from PySide6.QtCore import QRect, Qt, Signal
from PySide6.QtGui import QColor, QGuiApplication, QPainter, QPen
from PySide6.QtWidgets import QWidget


class RegionSelector(QWidget):
    """全屏拖拽框选。"""

    selected = Signal(tuple)   # (left, top, right, bottom)
    cancelled = Signal()

    def __init__(self, background: str | None = None):
        super().__init__()
        self._origin = None
        self._current = None
        self._background_pixmap = None
        if background:
            from PySide6.QtGui import QPixmap

            self._background_pixmap = QPixmap(background)

        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground, False)
        self.setCursor(Qt.CrossCursor)

        # 覆盖所有显示器
        geo = self._virtual_geometry()
        self.setGeometry(geo)

    @staticmethod
    def _virtual_geometry() -> QRect:
        """所有显示器拼成的整体区域，保证跨屏也能框选。"""
        rect = QRect()
        for screen in QGuiApplication.screens():
            rect = rect.united(screen.geometry())
        return rect

    # ---------- 绘制 ----------

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        if self._background_pixmap:
            painter.drawPixmap(self.rect(), self._background_pixmap)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 120))

        if self._origin and self._current:
            box = self._selection()
            # 选中的区域透出原始画面
            painter.setCompositionMode(QPainter.CompositionMode_Clear)
            painter.fillRect(box, Qt.transparent)
            painter.setCompositionMode(QPainter.CompositionMode_SourceOver)

            pen = QPen(QColor(90, 160, 255), 2)
            painter.setPen(pen)
            painter.drawRect(box)

            painter.setPen(QColor(255, 255, 255))
            painter.drawText(
                box.left() + 6, box.top() - 8,
                f"{box.width()} x {box.height()}  松开确定，按 Esc 取消",
            )
        else:
            painter.setPen(QColor(240, 240, 240))
            painter.drawText(
                self.rect().adjusted(0, 40, 0, 0),
                Qt.AlignHCenter | Qt.AlignTop,
                "拖动鼠标框选要识别的区域，松开即开始识别，按 Esc 取消",
            )

    def _selection(self) -> QRect:
        """由起点终点算出矩形，用最小最大值显式构造，避免包含式坐标差一像素。"""
        x1, y1 = self._origin.x(), self._origin.y()
        x2, y2 = self._current.x(), self._current.y()
        left, right = min(x1, x2), max(x1, x2)
        top, bottom = min(y1, y2), max(y1, y2)
        return QRect(left, top, right - left, bottom - top)

    # ---------- 交互 ----------

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self._origin = event.position().toPoint()
            self._current = self._origin
            self.update()

    def mouseMoveEvent(self, event) -> None:
        if self._origin is not None:
            self._current = event.position().toPoint()
            self.update()

    def mouseReleaseEvent(self, event) -> None:
        if event.button() != Qt.LeftButton or self._origin is None:
            return
        box = self._selection()
        self._origin = None
        self._current = None
        self.hide()
        if box.width() < 8 or box.height() < 8:
            self.cancelled.emit()
            return
        # 换算成屏幕绝对坐标。right 用 x+width 而非 right()，
        # 这样 right-left 正好等于宽度，与截图接口的约定一致。
        offset = self.geometry().topLeft()
        self.selected.emit((
            box.x() + offset.x(),
            box.y() + offset.y(),
            box.x() + box.width() + offset.x(),
            box.y() + box.height() + offset.y(),
        ))

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key_Escape:
            self._origin = None
            self._current = None
            self.hide()
            self.cancelled.emit()
