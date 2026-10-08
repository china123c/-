# -*- coding: utf-8 -*-
"""剪贴板监听：检测复制行为，自动记录文字和图片。"""
from PySide6.QtCore import QBuffer, QIODevice, QObject, QTimer, Signal


class ClipboardMonitor(QObject):
    new_record = Signal(dict)      # 新增记录
    record_touched = Signal(int)   # 重复复制，原记录时间被更新
    paused_changed = Signal(bool)

    def __init__(self, storage, clipboard):
        super().__init__()
        self.storage = storage
        self.clipboard = clipboard
        self.paused = False
        self._internal = False
        self._reset_timer = QTimer(self)
        self._reset_timer.setSingleShot(True)
        self._reset_timer.timeout.connect(self._clear_internal)

    def start(self):
        self.clipboard.dataChanged.connect(self._on_change)

    def set_paused(self, paused):
        self.paused = bool(paused)
        self.paused_changed.emit(self.paused)

    def set_internal(self):
        """程序自己写回剪贴板时调用，避免把旧记录当成新复制。"""
        self._internal = True
        self._reset_timer.start(200)

    def _clear_internal(self):
        self._internal = False

    def _on_change(self):
        if self.paused or self._internal:
            return
        md = self.clipboard.mimeData()
        if md.hasImage():
            img = self.clipboard.image()
            if not img.isNull():
                buf = QBuffer()
                buf.open(QIODevice.WriteOnly)
                img.save(buf, "PNG")
                self._report(self.storage.add_image(bytes(buf.data()), img))
                return
        if md.hasText():
            text = md.text()
            if text.strip():
                self._report(self.storage.add_text(text))

    def _report(self, result):
        if not result:
            return
        record_id, created = result
        if created:
            self.new_record.emit(dict(self.storage.get(record_id)))
        else:
            self.record_touched.emit(record_id)
