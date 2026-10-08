# -*- coding: utf-8 -*-
"""历史列表、完整预览与明确的复制和粘贴操作。"""
import datetime

from PySide6.QtCore import QEvent, QRect, QRectF, QSettings, Qt, QTimer
from PySide6.QtGui import QAction, QColor, QCursor, QGuiApplication, QImage, QKeySequence, QPainter, QPainterPath, QPixmap, QRadialGradient, QShortcut
from PySide6.QtWidgets import (
    QApplication, QButtonGroup, QFrame, QGraphicsDropShadowEffect, QHBoxLayout, QLabel, QLineEdit, QMainWindow, QMenu,
    QMessageBox, QPushButton, QRubberBand, QScrollArea, QSizePolicy, QSplitter,
    QStackedWidget, QSystemTrayIcon, QTextEdit, QVBoxLayout, QWidget,
)
from settings_dialog import SettingsDialog
from pinned_image import PinnedImageWindow
from theme import make_app_icon, make_search_icon, make_ui_icon
from win32utils import enable_dark_titlebar, get_foreground_window, paste_to_window

PAGE_SIZE = 60
FILTER_MAP = {0: None, 1: "text", 2: "image", 3: None}


def format_time(ts):
    dt = datetime.datetime.fromtimestamp(ts)
    seconds = max(0, int((datetime.datetime.now() - dt).total_seconds()))
    if seconds < 60:
        return "刚刚"
    if seconds < 3600:
        return f"{seconds // 60} 分钟前"
    if seconds < 86400:
        return f"{seconds // 3600} 小时前"
    if seconds < 86400 * 7:
        return f"{seconds // 86400} 天前"
    return dt.strftime("%m-%d %H:%M")


def label(text, name):
    widget = QLabel(text)
    widget.setObjectName(name)
    return widget


def button(text, callback, name="ghost", icon=None):
    widget = QPushButton(text)
    widget.setObjectName(name)
    widget.setCursor(Qt.PointingHandCursor)
    if icon:
        widget.setIcon(make_ui_icon(icon))
    widget.clicked.connect(callback)
    return widget


class ImagePreview(QLabel):
    def __init__(self):
        super().__init__()
        self.source = QPixmap()
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumSize(100, 40)
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Expanding)

    def set_source(self, path):
        self.source = QPixmap(path or "")
        self.setText("图片文件已失效" if self.source.isNull() else "")
        self.update()

    def paintEvent(self, event):
        if self.source.isNull():
            super().paintEvent(event)
        else:
            size = self.source.size().scaled(self.contentsRect().size(), Qt.KeepAspectRatio)
            target = QRect((self.width() - size.width()) // 2,
                           (self.height() - size.height()) // 2, size.width(), size.height())
            painter = QPainter(self)
            painter.setRenderHint(QPainter.SmoothPixmapTransform)
            painter.drawPixmap(target, self.source)
            painter.end()


class LightSurface(QWidget):
    """背景环境光；绘制区域固定，不影响子控件的鼠标交互。"""

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        for x, y, radius, color in [
            (self.width() * .12, 0, self.width() * .65, QColor(99, 119, 247, 42)),
            (self.width(), self.height() * .6, self.width() * .5, QColor(76, 154, 225, 24)),
        ]:
            glow = QRadialGradient(x, y, radius)
            glow.setColorAt(0, color)
            glow.setColorAt(1, QColor(color.red(), color.green(), color.blue(), 0))
            painter.fillRect(self.rect(), glow)
        painter.end()


class ListContainer(QWidget):
    """列表鼠标交互统一由主窗口的事件过滤器处理。"""


class CardWidget(QFrame):
    def __init__(self, record, window):
        super().__init__()
        self.record, self.window = record, window
        self.setObjectName("card")
        self.setProperty("pinned", bool(record["pinned"]))
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setMouseTracking(True)
        self._light_pos = None
        self._pressed = False
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(8)
        head = QHBoxLayout()
        head.addWidget(label("文字" if record["type"] == "text" else "图片", "typebadge"))
        if record["pinned"]:
            head.addWidget(label("已置顶", "pin"))
        head.addStretch()
        self.time_label = label(format_time(record["created_at"]), "time")
        self.time_label.setToolTip(datetime.datetime.fromtimestamp(record["created_at"]).strftime("%Y-%m-%d %H:%M:%S"))
        head.addWidget(self.time_label)
        self.sel_badge = label("", "selbadge")
        self.sel_badge.setPixmap(make_ui_icon("check").pixmap(16, 16))
        self.sel_badge.setAlignment(Qt.AlignCenter)
        self.sel_badge.setFixedSize(20, 20)
        self.sel_badge.hide()
        head.addWidget(self.sel_badge)
        lay.addLayout(head)
        preview = QLabel()
        preview.setTextFormat(Qt.PlainText)
        if record["type"] == "text":
            content = " ".join((record["content"] or "").split())
            preview.setText(content[:180] + ("…" if len(content) > 180 else ""))
            preview.setWordWrap(True)
            preview.setFixedHeight(preview.fontMetrics().lineSpacing() * 2 + 6)
            preview.setObjectName("cardtext")
        else:
            pix = QPixmap(record["thumb_path"] or "")
            if not pix.isNull():
                preview.setPixmap(pix.scaled(280, 110, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            else:
                preview.setText("图片文件已失效")
            preview.setFixedHeight(110)
        lay.addWidget(preview)
        for child in self.findChildren(QLabel):
            child.setAttribute(Qt.WA_TransparentForMouseEvents)

    def set_selected(self, selected):
        if self.property("selected") != bool(selected):
            self.setProperty("selected", bool(selected))
            self.style().unpolish(self)
            self.style().polish(self)
            self.update()
        self.sel_badge.setVisible(bool(selected) and self.window.manage_mode)

    def mousePressEvent(self, event):
        self._pressed = event.button() == Qt.LeftButton
        if self._pressed:
            self.setFocus(Qt.MouseFocusReason)
        event.accept()

    def mouseMoveEvent(self, event):
        self._light_pos = event.position()
        self.update()
        event.accept()

    def leaveEvent(self, event):
        self._light_pos = None
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event):
        super().paintEvent(event)
        if self._light_pos is not None:
            painter = QPainter(self)
            painter.setRenderHint(QPainter.Antialiasing)
            clip = QPainterPath()
            clip.addRoundedRect(QRectF(self.rect()).adjusted(1, 1, -1, -1), 10, 10)
            painter.setClipPath(clip)
            glow = QRadialGradient(self._light_pos, 180)
            glow.setColorAt(0, QColor(113, 151, 255, 42))
            glow.setColorAt(1, QColor(113, 151, 255, 0))
            painter.fillRect(self.rect(), glow)
            painter.end()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self._pressed and self.rect().contains(event.position().toPoint()):
            if self.window.manage_mode:
                self.window.toggle_select(self.record["id"])
            else:
                self.window.activate_record(self.record)
                if self.window.storage.settings.get("quick_paste"):
                    self.window.auto_paste(self.record)
        self._pressed = False
        event.accept()

    def mouseDoubleClickEvent(self, event):
        self._pressed = False
        if event.button() == Qt.LeftButton and not self.window.manage_mode:
            self.window.auto_paste(self.record)
        event.accept()

    def contextMenuEvent(self, event):
        menu = QMenu(self)
        if self.record["type"] == "image":
            menu.addAction("贴到屏幕", lambda: self.window.pin_image(self.record))
            menu.addSeparator()
        for text, callback in [
            ("复制", lambda: self.window.copy_only(self.record)),
            ("粘贴到原窗口", lambda: self.window.auto_paste(self.record)),
            ("取消置顶" if self.record["pinned"] else "置顶", lambda: self.window.toggle_pin(self.record["id"])),
            ("删除…", lambda: self.window.delete_record(self.record["id"])),
        ]:
            menu.addAction(text, callback)
        menu.exec(event.globalPos())


class MainWindow(QMainWindow):
    def __init__(self, storage, monitor, tray=None):
        super().__init__()
        self.storage, self.monitor, self.tray = storage, monitor, tray
        self._cards, self._selected = [], set()
        self._loaded = self._total = 0
        self._active_id = None
        self._manage_mode = False
        self._target_hwnd = None
        self._scroll_restore_token = None
        self._image_windows = {}
        self._box_origin = None
        self._box_dragging = False
        self._box_base = set()
        self._reload_after_drag = False
        self._drag_scroll_timer = QTimer(self)
        self._drag_scroll_timer.setInterval(25)
        self._drag_scroll_timer.timeout.connect(self._scroll_box_drag)
        self._qsettings = QSettings("HistoryClipboard", "HistoryClipboard")
        self.setWindowTitle("历史剪贴板")
        self.resize(940, 740)
        self.setMinimumSize(760, 580)
        self._build_ui()
        self._restore_geometry()
        enable_dark_titlebar(int(self.winId()))
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.timeout.connect(self.reload)
        self.search_edit.textChanged.connect(lambda: self._search_timer.start(180))
        self.monitor.new_record.connect(self._on_new_record)
        self.monitor.record_touched.connect(self._on_new_record)
        self.monitor.paused_changed.connect(self._update_recording)
        self._cleanup_timer = QTimer(self)
        self._cleanup_timer.timeout.connect(self._cleanup)
        self._cleanup_timer.start(30 * 60 * 1000)
        self._feedback_timer = QTimer(self)
        self._feedback_timer.setSingleShot(True)
        self._feedback_timer.timeout.connect(lambda: self.feedback_label.setText(""))
        self._shortcuts = []
        for key, callback in [
            ("Ctrl+F", self._focus_search), ("Ctrl+C", self._copy_active),
            ("Return", self._paste_active), ("Enter", self._paste_active),
            ("Up", lambda: self._navigate(-1)), ("Down", lambda: self._navigate(1)),
            ("Escape", self._escape), ("Delete", self._delete_active),
            ("Ctrl+A", self._select_all_active),
        ]:
            shortcut = QShortcut(QKeySequence(key), self)
            shortcut.activated.connect(callback)
            self._shortcuts.append(shortcut)
        self.reload()
        self._update_recording(self.monitor.paused)

    def _build_ui(self):
        central = LightSurface()
        central.setObjectName("appsurface")
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(24, 20, 24, 14)
        root.setSpacing(16)
        top = QHBoxLayout()
        logo = QLabel()
        logo.setPixmap(make_app_icon().pixmap(36, 36))
        top.addWidget(logo)
        names = QVBoxLayout()
        names.setSpacing(3)
        names.addWidget(label("历史剪贴板", "title"))
        top.addLayout(names)
        top.addStretch()
        self.record_btn = button("记录中", lambda: self.monitor.set_paused(not self.monitor.paused), "recording")
        self.record_btn.setToolTip("点击暂停或恢复剪贴板记录")
        top.addWidget(self.record_btn)
        top.addWidget(button("设置", self.open_settings, icon="settings"))
        root.addLayout(top)
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("搜索复制过的文字…")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.setMinimumHeight(44)
        self.search_edit.setAccessibleName("搜索历史文字")
        search_icon = QAction(self.search_edit)
        search_icon.setIcon(make_search_icon())
        self.search_edit.addAction(search_icon, QLineEdit.LeadingPosition)
        root.addWidget(self.search_edit)
        filters = QHBoxLayout()
        filters.setSpacing(4)
        self.filter_group = QButtonGroup(self)
        for i, name in enumerate(["全部", "文字", "图片", "置顶"]):
            btn = QPushButton(name)
            btn.setObjectName("seg")
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            self.filter_group.addButton(btn, i)
            filters.addWidget(btn)
        self.filter_group.button(0).setChecked(True)
        self.filter_group.idClicked.connect(self.reload)
        filters.addStretch()
        self.count_chip = label("0 条", "time")
        filters.addWidget(self.count_chip)
        self.manage_btn = button("多选", lambda: None)
        self.manage_btn.setCheckable(True)
        self.manage_btn.toggled.connect(self._set_manage_mode)
        filters.addWidget(self.manage_btn)
        more = button("更多", lambda: None)
        menu = QMenu(more)
        menu.addAction("清空全部历史…", self.clear_all)
        more.setMenu(menu)
        filters.addWidget(more)
        root.addLayout(filters)
        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.setChildrenCollapsible(False)
        self.list_stack = QStackedWidget()
        self.list_stack.setMinimumWidth(310)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.list_container = ListContainer()
        self.list_container.installEventFilter(self)
        self.scroll.viewport().installEventFilter(self)
        self.list_layout = QVBoxLayout(self.list_container)
        self.list_layout.setContentsMargins(0, 0, 8, 4)
        self.list_layout.setSpacing(9)
        self.list_layout.addStretch()
        self.rubber = QRubberBand(QRubberBand.Rectangle, self.list_container)
        self.rubber.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.scroll.setWidget(self.list_container)
        self.list_stack.addWidget(self.scroll)
        empty = QWidget()
        empty_lay = QVBoxLayout(empty)
        empty_lay.addStretch()
        empty_icon = QLabel()
        empty_icon.setPixmap(make_app_icon().pixmap(64, 64))
        empty_icon.setAlignment(Qt.AlignCenter)
        empty_lay.addWidget(empty_icon)
        self.empty_label = label("", "empty")
        self.empty_label.setAlignment(Qt.AlignCenter)
        self.empty_label.setWordWrap(True)
        empty_lay.addWidget(self.empty_label)
        empty_lay.addStretch()
        self.list_stack.addWidget(empty)
        self.splitter.addWidget(self.list_stack)
        self.detail = QFrame()
        self.detail.setObjectName("detail")
        self.detail.setMinimumWidth(280)
        shadow = QGraphicsDropShadowEffect(self.detail)
        shadow.setBlurRadius(22)
        shadow.setOffset(0, 4)
        shadow.setColor(QColor(77, 101, 160, 22))
        self.detail.setGraphicsEffect(shadow)
        detail_lay = QVBoxLayout(self.detail)
        detail_lay.setContentsMargins(18, 18, 18, 18)
        detail_lay.setSpacing(12)
        detail_head = QHBoxLayout()
        self.detail_title = label("内容预览", "detailtitle")
        detail_head.addWidget(self.detail_title)
        detail_head.addStretch()
        self.pin_btn = button("置顶", self._pin_active, icon="pin")
        detail_head.addWidget(self.pin_btn)
        detail_lay.addLayout(detail_head)
        self.detail_meta = label("", "time")
        self.detail_meta.setWordWrap(True)
        detail_lay.addWidget(self.detail_meta)
        self.preview_stack = QStackedWidget()
        welcome = label("选择一条记录", "previewhint")
        welcome.setAlignment(Qt.AlignCenter)
        welcome.setWordWrap(True)
        self.preview_stack.addWidget(welcome)
        self.text_preview = QTextEdit()
        self.text_preview.setReadOnly(True)
        self.text_preview.setFrameShape(QFrame.NoFrame)
        self.text_preview.setObjectName("textpreview")
        self.preview_stack.addWidget(self.text_preview)
        self.image_preview = ImagePreview()
        self.preview_stack.addWidget(self.image_preview)
        detail_lay.addWidget(self.preview_stack, 1)
        self.screen_pin_btn = button("贴到屏幕", self._pin_image_active, "glass", "screen")
        self.screen_pin_btn.setToolTip("独立浮窗：拖动移动、滚轮缩放、右键查看更多操作")
        self.screen_pin_btn.hide()
        detail_lay.addWidget(self.screen_pin_btn)
        actions = QHBoxLayout()
        self.copy_btn = button("复制", self._copy_active, icon="copy")
        self.paste_btn = button("粘贴", self._paste_active, "primary")
        self.paste_btn.setToolTip("粘贴到原窗口（Enter）")
        actions.addWidget(self.copy_btn)
        actions.addWidget(self.paste_btn, 1)
        detail_lay.addLayout(actions)
        self.splitter.addWidget(self.detail)
        self.splitter.setSizes([470, 360])
        self.splitter.setStretchFactor(0, 3)
        self.splitter.setStretchFactor(1, 2)
        root.addWidget(self.splitter, 1)
        self.batch_bar = QFrame()
        self.batch_bar.setObjectName("batchbar")
        batch = QHBoxLayout(self.batch_bar)
        self.batch_label = label("已选 0 项", "hinttext")
        batch.addWidget(self.batch_label)
        batch.addStretch()
        batch.addWidget(button("全选已加载", self.select_all))
        self.batch_delete_btn = button("删除所选", self.batch_delete, "danger")
        batch.addWidget(self.batch_delete_btn)
        batch.addWidget(button("取消选择", self.clear_selection))
        self.batch_bar.hide()
        root.addWidget(self.batch_bar)
        bottom = QHBoxLayout()
        self.feedback_label = label("", "feedback")
        bottom.addWidget(self.feedback_label, 1)
        self.foot_label = label("", "time")
        bottom.addWidget(self.foot_label)
        self.load_more_btn = button("加载更多", self.load_more)
        bottom.addWidget(self.load_more_btn)
        root.addLayout(bottom)
        self._show_preview(None)

    def _query_args(self):
        return dict(search=self.search_edit.text().strip(),
                    type_filter=FILTER_MAP[self.filter_group.checkedId()],
                    pinned_only=self.filter_group.checkedId() == 3)

    def reload(self, *args, preserve=False):
        if self._box_dragging:
            self._reload_after_drag = True
            return
        if hasattr(self, "_search_timer"):
            self._search_timer.stop()
        active = self._active_id if preserve else None
        selected = set(self._selected) if preserve else set()
        scroll_value = self.scroll.verticalScrollBar().value() if preserve else 0
        limit = max(PAGE_SIZE, self._loaded) if preserve else PAGE_SIZE
        for card in self._cards:
            self.list_layout.removeWidget(card)
            card.hide()
            card.deleteLater()
        self._cards.clear()
        query = self._query_args()
        self._total = self.storage.count(**query)
        for row in self.storage.query(0, limit, **query):
            card = CardWidget(dict(row), self)
            card.installEventFilter(self)
            self.list_layout.insertWidget(self.list_layout.count() - 1, card)
            self._cards.append(card)
        self._loaded = len(self._cards)
        self._selected = selected & {c.record["id"] for c in self._cards}
        row = next((c.record for c in self._cards if c.record["id"] == active), None)
        self._show_preview(row)
        self._refresh_selection()
        self._update_footer()
        self.list_layout.activate()
        self.scroll.verticalScrollBar().setValue(scroll_value)
        # Qt 在下一轮事件中更新滚动区域范围，等布局完成后恢复位置。
        token = object()
        self._scroll_restore_token = token
        QTimer.singleShot(0, lambda: self._restore_scroll(token, scroll_value))

    def _restore_scroll(self, token, value):
        if self._scroll_restore_token is token:
            self.scroll.verticalScrollBar().setValue(value)
            self._scroll_restore_token = None

    def _update_footer(self):
        self.list_stack.setCurrentIndex(0 if self._total else 1)
        self.count_chip.setText(f"{self._total} 条")
        self.load_more_btn.setVisible(self._loaded < self._total)
        self.foot_label.setText(f"{self._loaded} / {self._total}" if self._loaded < self._total else "")
        if self.search_edit.text().strip():
            message = "没有匹配的内容"
        elif self.filter_group.checkedId() == 3:
            message = "暂无置顶内容"
        elif self.filter_group.checkedId() != 0:
            message = "暂无记录"
        else:
            message = "复制文字或图片后会显示在这里"
        self.empty_label.setText(message)

    def load_more(self):
        for row in self.storage.query(self._loaded, PAGE_SIZE, **self._query_args()):
            card = CardWidget(dict(row), self)
            card.installEventFilter(self)
            self.list_layout.insertWidget(self.list_layout.count() - 1, card)
            self._cards.append(card)
        self._loaded = len(self._cards)
        self._refresh_selection()
        self._update_footer()

    def _on_new_record(self, record):
        if self.isVisible():
            self.reload(preserve=True)

    def activate_record(self, record):
        self._scroll_restore_token = None
        self._show_preview(record)
        self._refresh_selection()

    def _show_preview(self, record):
        self._active_id = record["id"] if record else None
        self.screen_pin_btn.setVisible(record is not None and record["type"] == "image")
        for widget in (self.copy_btn, self.paste_btn, self.pin_btn):
            widget.setEnabled(record is not None)
        if not record:
            self.detail_title.setText("内容预览")
            self.detail_meta.setText("")
            self.preview_stack.setCurrentIndex(0)
            self.text_preview.clear()
            self.image_preview.clear()
            return
        is_text = record["type"] == "text"
        self.detail_title.setText("文字预览" if is_text else "图片预览")
        if is_text:
            content = record["content"] or ""
            self.text_preview.setPlainText(content)
            meta = f"{len(content):,} 字符"
            self.preview_stack.setCurrentIndex(1)
        else:
            self.image_preview.set_source(record["image_path"])
            pix = self.image_preview.source
            meta = f"{pix.width()} × {pix.height()}" if not pix.isNull() else "文件已失效"
            self.preview_stack.setCurrentIndex(2)
        self.detail_meta.setText(meta)
        self.pin_btn.setText("取消置顶" if record["pinned"] else "置顶")

    @property
    def manage_mode(self):
        return self._manage_mode

    def _set_manage_mode(self, checked):
        self._manage_mode = checked
        self.clear_selection()
        self.batch_bar.setVisible(checked)
        self.manage_btn.setText("完成" if checked else "多选")
        if not checked:
            self._cancel_box_drag()
        self.rubber.hide()

    def toggle_select(self, record_id):
        self._selected.symmetric_difference_update({record_id})
        self._refresh_selection()

    def _refresh_selection(self, override=None):
        selected = self._selected if override is None else override
        for card in self._cards:
            card.set_selected(card.record["id"] in selected if self.manage_mode else card.record["id"] == self._active_id)
        count = len(selected)
        self.batch_label.setText(f"已选 {count} 项")
        self.batch_delete_btn.setEnabled(count > 0)

    def clear_selection(self):
        self._selected.clear()
        self._refresh_selection()

    def select_all(self):
        self._selected.update(card.record["id"] for card in self._cards)
        self._refresh_selection()

    def _on_box_drag(self, rect, final):
        if not self.manage_mode:
            return
        self.rubber.setGeometry(rect)
        self.rubber.setVisible(not final)
        inside = {c.record["id"] for c in self._cards if rect.intersects(c.geometry())}
        if final:
            self._selected = self._box_base | inside
        self._refresh_selection(self._box_base | inside)

    def eventFilter(self, watched, event):
        kind = event.type()
        if kind == QEvent.MouseButtonPress and event.button() == Qt.LeftButton:
            self._box_origin = self.list_container.mapFromGlobal(event.globalPosition().toPoint())
            self._box_pointer = event.globalPosition().toPoint()
            self._box_press_global = self._box_pointer
            self._box_base = set(self._selected) if event.modifiers() & Qt.ControlModifier else set()
            self._box_dragging = False
        elif kind == QEvent.MouseMove and self._box_origin is not None and event.buttons() & Qt.LeftButton:
            self._box_pointer = event.globalPosition().toPoint()
            if not self._box_dragging and (self._box_pointer - self._box_press_global).manhattanLength() >= QApplication.startDragDistance():
                self._box_dragging = True
                if isinstance(watched, CardWidget):
                    watched._pressed = False
                if not self.manage_mode:
                    self.manage_btn.setChecked(True)
                self._scroll_restore_token = None
                self._drag_scroll_timer.start()
            if self._box_dragging:
                self._update_box_drag()
                return True
        elif kind == QEvent.MouseButtonRelease and event.button() == Qt.LeftButton and self._box_origin is not None:
            dragged = self._box_dragging
            if dragged:
                self._box_pointer = event.globalPosition().toPoint()
                self._update_box_drag(final=True)
            self._cancel_box_drag()
            return dragged
        return super().eventFilter(watched, event)

    def _update_box_drag(self, final=False):
        point = self.list_container.mapFromGlobal(self._box_pointer)
        self._on_box_drag(QRect(self._box_origin, point).normalized(), final)
        if not final:
            self.rubber.raise_()

    def _scroll_box_drag(self):
        if not self._box_dragging:
            return
        viewport = self.scroll.viewport()
        point = viewport.mapFromGlobal(self._box_pointer)
        step = -18 if point.y() < 28 else 18 if point.y() > viewport.height() - 28 else 0
        if step:
            bar = self.scroll.verticalScrollBar()
            bar.setValue(bar.value() + step)
            self._update_box_drag()

    def _cancel_box_drag(self):
        self._box_origin = None
        self._box_dragging = False
        self._drag_scroll_timer.stop()
        self.rubber.hide()
        if self._reload_after_drag:
            self._reload_after_drag = False
            QTimer.singleShot(0, lambda: self.reload(preserve=True))

    def _pin_image_active(self):
        record = self._active_record()
        if record is not None:
            self.pin_image(record)

    def pin_image(self, record):
        if record["type"] != "image":
            return None
        if record["id"] in self._image_windows:
            window = self._image_windows[record["id"]]
            window.show()
            window.raise_()
            return window
        pixmap = QPixmap(record["image_path"] or "")
        if pixmap.isNull():
            self._feedback("图片文件已失效，无法贴图")
            return None
        return self._open_pinned_image(pixmap, record["id"])

    def pin_clipboard_image(self):
        """直接读取当前图片，不依赖历史记录或监听是否暂停。"""
        clipboard = QGuiApplication.clipboard()
        image = clipboard.image()
        if image.isNull():
            mime = clipboard.mimeData()
            if mime is not None and mime.hasUrls():
                urls = mime.urls()
                if len(urls) == 1 and urls[0].isLocalFile():
                    image = QImage(urls[0].toLocalFile())
        if image.isNull():
            message = "当前剪贴板没有图片，请先截图或复制图片。"
            if self.isVisible():
                self._feedback(message)
            elif self.tray:
                self.tray.showMessage("图片贴屏", message,
                                      QSystemTrayIcon.MessageIcon.Information, 2500)
            return None
        return self._open_pinned_image(QPixmap.fromImage(image.copy()), object(), from_clipboard=True)

    def _open_pinned_image(self, pixmap, key, from_clipboard=False):
        window = PinnedImageWindow(pixmap)
        window.copy_requested.connect(self._copy_pinned_image)
        window.closed.connect(lambda: self._image_windows.pop(key, None))
        self._image_windows[key] = window
        if from_clipboard:
            screen = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
            window.show_on_screen(screen, activate=False)
        else:
            window.show_near(self)
        return window

    def _copy_pinned_image(self, image):
        self.monitor.set_internal()
        QGuiApplication.clipboard().setImage(image)

    def close_all_images(self):
        for window in list(self._image_windows.values()):
            window.close()

    def _confirm(self, title, text):
        box = QMessageBox(QMessageBox.Question, title, text, QMessageBox.Yes | QMessageBox.Cancel, self)
        box.button(QMessageBox.Yes).setText("删除")
        box.button(QMessageBox.Cancel).setText("取消")
        box.setDefaultButton(QMessageBox.Cancel)
        return box.exec() == QMessageBox.Yes

    def batch_delete(self):
        if self._selected and self._confirm("删除所选", f"删除选中的 {len(self._selected)} 条记录？此操作无法撤销。"):
            self.storage.delete_many(self._selected)
            self.reload(preserve=True)
            self._feedback("已删除所选记录")

    def copy_only(self, record, notify=True):
        if not self.storage.get(record["id"]):
            self._feedback("这条记录已被清理，请刷新后重试")
            return False
        image = None
        if record["type"] == "image":
            image = QImage(record["image_path"] or "")
            if image.isNull():
                self._feedback("图片文件已失效，无法复制")
                return False
        self.monitor.set_internal()
        clipboard = QGuiApplication.clipboard()
        if image is None:
            clipboard.setText(record["content"] or "")
        else:
            clipboard.setImage(image)
        if notify:
            self._feedback("已复制，可在目标位置按 Ctrl+V")
        return True

    def auto_paste(self, record):
        if not self.copy_only(record, notify=False):
            return
        if not self._target_hwnd:
            self._feedback("已复制，请切换到目标窗口按 Ctrl+V")
            return
        target = self._target_hwnd
        self.hide()
        QTimer.singleShot(180, lambda: self._finish_paste(target))

    def _finish_paste(self, target):
        if not paste_to_window(target):
            self.show_and_raise()
            self._feedback("已复制；未能返回原窗口，请手动 Ctrl+V")

    def toggle_pin(self, record_id):
        pinned = self.storage.toggle_pin(record_id)
        self.reload(preserve=True)
        self._feedback("已置顶，自动清理时会保留" if pinned else "已取消置顶")

    def delete_record(self, record_id):
        if self._confirm("删除记录", "删除这条记录？此操作无法撤销。"):
            self.storage.delete(record_id)
            self.reload(preserve=True)
            self._feedback("已删除记录")

    def clear_all(self):
        if self._confirm("清空历史", "删除全部历史，包括置顶内容？此操作无法撤销。"):
            self.storage.clear_all()
            self.reload()
            self._feedback("历史已清空")

    def open_settings(self):
        if SettingsDialog(self.storage, self).exec():
            self.reload(preserve=True)
            self._feedback("设置已保存")

    def _active_record(self):
        return self.storage.get(self._active_id) if self._active_id is not None else None

    def _copy_active(self):
        if self.search_edit.hasFocus() and self.search_edit.hasSelectedText():
            self.search_edit.copy()
        elif self.text_preview.hasFocus() and self.text_preview.textCursor().hasSelection():
            self.text_preview.copy()
        elif not self.manage_mode and (record := self._active_record()) is not None:
            self.copy_only(record)

    def _paste_active(self):
        if self._search_timer.isActive():
            self.reload()
        if not self.manage_mode:
            record = self._active_record()
            if record is None and self._cards:
                record = self._cards[0].record
            if record is not None:
                self.auto_paste(record)

    def _pin_active(self):
        if self._active_id is not None:
            self.toggle_pin(self._active_id)

    def _select_all_active(self):
        if self.search_edit.hasFocus():
            self.search_edit.selectAll()
        elif self.manage_mode:
            self.select_all()
        elif self.text_preview.hasFocus():
            self.text_preview.selectAll()

    def _delete_active(self):
        if self.search_edit.hasFocus():
            self.search_edit.del_()
        elif self.manage_mode:
            self.batch_delete()
        elif self._active_id is not None:
            self.delete_record(self._active_id)

    def _navigate(self, step):
        if self._search_timer.isActive():
            self.reload()
        if not self._cards or self.manage_mode:
            return
        index = next((i for i, c in enumerate(self._cards) if c.record["id"] == self._active_id), -1)
        index = max(0, min(len(self._cards) - 1, index + step))
        card = self._cards[index]
        self.activate_record(card.record)
        self.scroll.ensureWidgetVisible(card, 0, 20)

    def _focus_search(self):
        self.search_edit.setFocus()
        self.search_edit.selectAll()

    def _escape(self):
        if self._box_dragging:
            self._cancel_box_drag()
            self._refresh_selection()
        elif self.manage_mode and self._selected:
            self.clear_selection()
        elif self.manage_mode:
            self.manage_btn.setChecked(False)
        elif self.search_edit.text():
            self.search_edit.clear()
        else:
            self.hide()

    def _feedback(self, text):
        self.feedback_label.setText(text)
        self._feedback_timer.start(4500)

    def _update_recording(self, paused):
        self.record_btn.setText("已暂停" if paused else "记录中")
        self.record_btn.setProperty("paused", paused)
        self.record_btn.style().unpolish(self.record_btn)
        self.record_btn.style().polish(self.record_btn)

    def _cleanup(self):
        self.storage.cleanup()
        if self.isVisible():
            self.reload(preserve=True)

    def show_and_raise(self):
        foreground = get_foreground_window()
        if foreground and foreground != int(self.winId()) and not self.isActiveWindow():
            self._target_hwnd = foreground
        self.show()
        self.setWindowState((self.windowState() & ~Qt.WindowMinimized) | Qt.WindowActive)
        self.raise_()
        self.activateWindow()
        self._focus_search()

    def showEvent(self, event):
        super().showEvent(event)
        self.reload(preserve=True)

    def closeEvent(self, event):
        event.ignore()
        self._cancel_box_drag()
        self._qsettings.setValue("window_geometry", self.saveGeometry())
        self._qsettings.setValue("splitter_state", self.splitter.saveState())
        self.hide()

    def hideEvent(self, event):
        self._cancel_box_drag()
        super().hideEvent(event)

    def _restore_geometry(self):
        geometry = self._qsettings.value("window_geometry")
        if geometry:
            self.restoreGeometry(geometry)
        splitter = self._qsettings.value("splitter_state")
        if splitter:
            self.splitter.restoreState(splitter)
