# -*- coding: utf-8 -*-
"""无边框贴图：原始图片、外侧柔光与透明关闭按钮。"""
from PySide6.QtCore import QEvent, QPoint, QPointF, QRect, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QGuiApplication, QLinearGradient, QPainter, QPen, QPixmap, QRadialGradient, QShortcut, QKeySequence
from PySide6.QtWidgets import QAbstractButton, QMenu, QWidget

GLOW_MARGIN = 18


class ImageCanvas(QWidget):
    def __init__(self, source, parent):
        super().__init__(parent)
        self.source = source
        self.setCursor(Qt.OpenHandCursor)
        self.setAttribute(Qt.WA_TranslucentBackground)

    def image_rect(self):
        size = self.source.size().scaled(self.size(), Qt.KeepAspectRatio)
        return QRect((self.width() - size.width()) // 2, (self.height() - size.height()) // 2,
                     size.width(), size.height())

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        # 不绘制底板，也不裁切或填充原图的透明部分。
        painter.drawPixmap(self.image_rect(), self.source)
        painter.end()


class CloseButton(QAbstractButton):
    """透明按钮，仅绘制带轻微对比描边的半透明叉号。"""

    def __init__(self, parent):
        super().__init__(parent)
        self.setFixedSize(28, 28)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip("关闭（Esc）")
        self.setAccessibleName("关闭贴图")
        self.setAttribute(Qt.WA_TranslucentBackground)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        lines = [(QPointF(9, 9), QPointF(19, 19)),
                 (QPointF(19, 9), QPointF(9, 19))]
        for color, width in [(QColor(5, 10, 20, 130), 3.6),
                             (QColor(255, 255, 255, 245 if self.underMouse() else 175), 1.7)]:
            pen = QPen(color, width)
            pen.setCapStyle(Qt.RoundCap)
            painter.setPen(pen)
            for start, end in lines:
                painter.drawLine(start, end)
        painter.end()

    def enterEvent(self, event):
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.update()
        super().leaveEvent(event)


class PinnedImageWindow(QWidget):
    closed = Signal()
    copy_requested = Signal(object)

    def __init__(self, pixmap):
        if pixmap.isNull():
            raise ValueError("Cannot pin an empty image")
        super().__init__(None, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.source = QPixmap(pixmap)
        self.setWindowTitle("图片贴屏")
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setMinimumSize(GLOW_MARGIN * 2 + 1, GLOW_MARGIN * 2 + 1)
        self._drag_offset = None
        self._zoom = 1.0
        self.canvas = ImageCanvas(self.source, self)
        self.close_btn = CloseButton(self)
        self.close_btn.clicked.connect(self.close)
        for widget in (self, self.canvas):
            widget.installEventFilter(self)
        self._shortcuts = []
        for key, callback in [
            ("Escape", self.close), ("Ctrl+C", self.copy_image),
            ("+", lambda: self.set_zoom(self.zoom * 1.15)),
            ("-", lambda: self.set_zoom(self.zoom / 1.15)),
            ("0", lambda: self.set_zoom(1.0)),
        ]:
            shortcut = QShortcut(QKeySequence(key), self)
            shortcut.activated.connect(callback)
            self._shortcuts.append(shortcut)
        self.set_zoom(min(1.0, 640 / self.source.width(), 460 / self.source.height()))

    @property
    def zoom(self):
        rect = self.canvas.image_rect()
        return rect.width() / self.source.width() if rect.width() > 0 else self._zoom

    @property
    def topmost(self):
        return bool(self.windowFlags() & Qt.WindowStaysOnTopHint)

    def set_zoom(self, zoom):
        screen = self.screen() or QGuiApplication.primaryScreen()
        bounds = screen.availableGeometry()
        max_zoom = min(4.0, (bounds.width() - GLOW_MARGIN * 2) / self.source.width(),
                       (bounds.height() - GLOW_MARGIN * 2) / self.source.height())
        zoom = min(max_zoom, max(min(.1, max_zoom), zoom))
        center = self.geometry().center()
        self._zoom = zoom
        self.resize(max(1, round(self.source.width() * zoom)) + GLOW_MARGIN * 2,
                    max(1, round(self.source.height() * zoom)) + GLOW_MARGIN * 2)
        self._layout_image()
        self.move(self._bounded_position(center - QPoint(self.width() // 2, self.height() // 2), bounds))

    def _bounded_position(self, point, bounds):
        return QPoint(max(bounds.left(), min(point.x(), bounds.right() - self.width() + 1)),
                      max(bounds.top(), min(point.y(), bounds.bottom() - self.height() + 1)))

    def show_near(self, anchor):
        screen = anchor.screen() or QGuiApplication.primaryScreen()
        self.show_on_screen(screen, anchor.geometry().center())

    def show_on_screen(self, screen, center=None, activate=True):
        bounds = screen.availableGeometry()
        # 在目标显示器上重新限制尺寸，适应多个不同分辨率的屏幕。
        self.setScreen(screen)
        self.set_zoom(self._zoom)
        self.move(self._bounded_position((center or bounds.center()) -
                  QPoint(self.width() // 2, self.height() // 2), bounds))
        self.setAttribute(Qt.WA_ShowWithoutActivating, not activate)
        self.show()
        self.raise_()
        if activate:
            self.activateWindow()

    def toggle_topmost(self, checked):
        geometry = self.geometry()
        self.setWindowFlag(Qt.WindowStaysOnTopHint, checked)
        self.setGeometry(geometry)
        self.show()

    def copy_image(self):
        self.copy_requested.emit(self.source.toImage())

    def _layout_image(self):
        self.canvas.setGeometry(self.rect().adjusted(GLOW_MARGIN, GLOW_MARGIN, -GLOW_MARGIN, -GLOW_MARGIN))
        rect = self.canvas.image_rect().translated(self.canvas.pos())
        self.close_btn.move(max(0, rect.right() - self.close_btn.width() - 3), rect.top() + 4)
        self.close_btn.raise_()
        self.update()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._layout_image()

    def eventFilter(self, watched, event):
        kind = event.type()
        if kind == QEvent.MouseButtonPress and event.button() == Qt.LeftButton:
            self._drag_offset = event.globalPosition().toPoint() - self.pos()
            self.canvas.setCursor(Qt.ClosedHandCursor)
            return True
        if kind == QEvent.MouseMove and self._drag_offset is not None and event.buttons() & Qt.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_offset)
            return True
        if kind == QEvent.MouseButtonRelease and event.button() == Qt.LeftButton:
            self._drag_offset = None
            self.canvas.setCursor(Qt.OpenHandCursor)
            return True
        if kind == QEvent.Wheel:
            delta = event.angleDelta().y()
            if delta:
                self.set_zoom(self.zoom * 1.15 ** (delta / 120))
            event.accept()
            return True
        if kind == QEvent.MouseButtonDblClick and event.button() == Qt.LeftButton:
            self.set_zoom(1.0)
            return True
        return super().eventFilter(watched, event)

    def contextMenuEvent(self, event):
        menu = QMenu(self)
        menu.addAction("复制图片", self.copy_image)
        menu.addAction("放大", lambda: self.set_zoom(self.zoom * 1.15))
        menu.addAction("缩小", lambda: self.set_zoom(self.zoom / 1.15))
        menu.addAction("恢复原始大小", lambda: self.set_zoom(1.0))
        menu.addSeparator()
        top = menu.addAction("始终置顶")
        top.setCheckable(True)
        top.setChecked(self.topmost)
        top.triggered.connect(self.toggle_topmost)
        menu.addSeparator()
        menu.addAction("关闭", self.close)
        menu.exec(event.globalPos())

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        image = QRectF(self.canvas.image_rect().translated(self.canvas.pos()))
        margin = GLOW_MARGIN

        def faded(gradient):
            gradient.setColorAt(0, QColor(153, 191, 255, 38))
            gradient.setColorAt(.35, QColor(153, 191, 255, 14))
            gradient.setColorAt(.7, QColor(153, 191, 255, 3))
            gradient.setColorAt(1, QColor(153, 191, 255, 0))
            return gradient

        # 四边与四角各占独立区域，柔光连续衰减，不叠成实线边框。
        x, y, w, h = image.x(), image.y(), image.width(), image.height()
        for rect, start, end in [
            (QRectF(x - margin, y, margin, h), QPointF(x, y), QPointF(x - margin, y)),
            (QRectF(x + w, y, margin, h), QPointF(x + w, y), QPointF(x + w + margin, y)),
            (QRectF(x, y - margin, w, margin), QPointF(x, y), QPointF(x, y - margin)),
            (QRectF(x, y + h, w, margin), QPointF(x, y + h), QPointF(x, y + h + margin)),
        ]:
            painter.fillRect(rect, faded(QLinearGradient(start, end)))
        for rect, corner in [
            (QRectF(x - margin, y - margin, margin, margin), QPointF(x, y)),
            (QRectF(x + w, y - margin, margin, margin), QPointF(x + w, y)),
            (QRectF(x - margin, y + h, margin, margin), QPointF(x, y + h)),
            (QRectF(x + w, y + h, margin, margin), QPointF(x + w, y + h)),
        ]:
            painter.fillRect(rect, faded(QRadialGradient(corner, margin)))
        painter.end()

    def closeEvent(self, event):
        self.closed.emit()
        super().closeEvent(event)
