# -*- coding: utf-8 -*-
"""在独立临时数据库和离屏剪贴板中验证窗口，不触碰用户历史。"""
import os
os.environ["QT_QPA_PLATFORM"] = "offscreen"

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QBuffer, QEvent, QIODevice, QMimeData, QPoint, QPointF, QSettings, QSize, Qt, QUrl
from PySide6.QtGui import QColor, QImage, QMouseEvent, QPainter, QFont, QFontDatabase, QPixmap, QWheelEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLabel
import main_window
import win32utils
from main_window import MainWindow
from monitor import ClipboardMonitor
from quick_pin_hotkey import KBDLLHOOKSTRUCT, QuickPinHotkey, VK_Q
from settings_dialog import SettingsDialog
from pinned_image import GLOW_MARGIN, PinnedImageWindow
from storage import Storage
from theme import apply_theme
import ctypes

APP = QApplication.instance() or QApplication([])
QFontDatabase.addApplicationFont("C:/Windows/Fonts/msyh.ttc")
QFontDatabase.addApplicationFont("C:/Windows/Fonts/seguisym.ttf")
apply_theme(APP)
ARTIFACTS = Path(__file__).parent / "preview"
ARTIFACTS.mkdir(exist_ok=True)


class WindowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="clipboard_ui_")
        self.storage = Storage(self.temp.name)
        self.monitor = ClipboardMonitor(self.storage, APP.clipboard())
        self.settings_patch = patch.object(main_window, "QSettings", lambda *_: QSettings(
            str(Path(self.temp.name) / "window.ini"), QSettings.IniFormat))
        self.settings_patch.start()
        self.window = MainWindow(self.storage, self.monitor)
        self.window.show()
        self.window.activateWindow()
        APP.processEvents()

    def tearDown(self):
        self.window.close_all_images()
        self.window.hide()
        self.window.deleteLater()
        APP.processEvents()
        self.storage._conn.close()
        self.settings_patch.stop()
        self.temp.cleanup()

    def text(self, content):
        rid, _ = self.storage.add_text(content)
        return dict(self.storage.get(rid))

    def image(self):
        image = QImage(800, 480, QImage.Format_ARGB32)
        image.fill(QColor("#EEF2FF"))
        painter = QPainter(image)
        painter.setPen(QColor("#354158"))
        painter.setFont(QFont("Microsoft YaHei UI", 22))
        painter.drawText(40, 60, "每周灵感收集")
        painter.setPen(Qt.NoPen)
        for i, height in enumerate([120, 170, 145, 230, 200, 280]):
            painter.setBrush(QColor("#7C90E8" if i < 5 else "#506CDC"))
            painter.drawRoundedRect(50 + i * 115, 400 - height, 65, height, 9, 9)
        painter.end()
        buf = QBuffer()
        buf.open(QIODevice.WriteOnly)
        image.save(buf, "PNG")
        rid, _ = self.storage.add_image(bytes(buf.data()), image)
        return dict(self.storage.get(rid))

    def test_empty_search_transitions_and_literal_search(self):
        self.assertEqual(self.window.list_stack.currentIndex(), 1)
        record = self.text("  <b>100% done_file</b>\n    keep indentation\n")
        self.window._on_new_record(record)
        APP.processEvents()
        self.assertEqual(self.window.list_stack.currentIndex(), 0)
        self.assertEqual(self.storage.get(record["id"])["content"], record["content"])
        self.text("100X doneXfile")
        self.assertEqual(self.storage.count(search="%"), 1)
        self.assertEqual(self.storage.count(search="_"), 1)
        self.text(r"path C:\work")
        self.assertEqual(self.storage.count(search=r"C:\work"), 1)
        for query in ["not-found", "100%", "not-found", ""]:
            self.window.search_edit.setText(query)
            self.window.reload()
            APP.processEvents()
        self.assertEqual(self.window.list_stack.currentIndex(), 0)
        self.window.activate_record(record)
        self.assertEqual(self.window.text_preview.toPlainText(), record["content"])
        preview_label = self.window._cards[-1].findChild(QLabel, "cardtext")
        self.assertEqual(preview_label.textFormat(), Qt.PlainText)

    def test_click_keyboard_copy_and_double_click(self):
        record = self.text("    example = 42\n")
        self.window.reload()
        APP.processEvents()
        card = self.window._cards[0]
        with patch.object(self.window, "auto_paste") as paste:
            QTest.mouseClick(card, Qt.LeftButton, pos=QPoint(40, 40))
            self.assertEqual(self.window._active_id, record["id"])
            paste.assert_not_called()
            QTest.keyClick(card, Qt.Key_C, Qt.ControlModifier)
            self.assertEqual(APP.clipboard().text(), record["content"])
            QTest.keyClick(card, Qt.Key_Return)
            self.assertEqual(paste.call_count, 1)
            QTest.mouseDClick(card, Qt.LeftButton, pos=QPoint(40, 40))
            self.assertEqual(paste.call_count, 2)
        self.storage.settings["quick_paste"] = True
        with patch.object(self.window, "auto_paste") as paste:
            QTest.mouseClick(card, Qt.LeftButton, pos=QPoint(40, 40))
            paste.assert_called_once()

    def test_pin_filters_live_refresh_and_selection(self):
        pinned = self.text("常用地址")
        self.storage.toggle_pin(pinned["id"])
        other = self.text("其他内容")
        self.window.reload()
        self.window.activate_record(other)
        self.window.manage_btn.setChecked(True)
        self.window.toggle_select(other["id"])
        new = self.text("新复制的文字")
        self.window._on_new_record(new)
        self.assertEqual(self.window._cards[0].record["id"], pinned["id"])
        self.assertEqual(self.window._active_id, other["id"])
        self.assertEqual(self.window._selected, {other["id"]})
        self.window.manage_btn.setChecked(False)
        self.window.filter_group.button(3).click()
        self.assertEqual(len(self.window._cards), 1)
        self.assertEqual(self.window._cards[0].record["id"], pinned["id"])
        self.window.filter_group.button(2).click()
        self.assertEqual(self.window.list_stack.currentIndex(), 1)
        image = self.image()
        self.window._on_new_record(image)
        self.assertEqual(self.window.list_stack.currentIndex(), 0)
        self.window.activate_record(image)
        self.assertEqual(self.window.preview_stack.currentIndex(), 2)
        self.monitor.set_paused(True)
        self.assertEqual(self.window.record_btn.text(), "已暂停")

    def test_pagination_and_invalid_image_does_not_paste_old_content(self):
        for i in range(65):
            self.text(f"分页内容 {i}")
        self.window.reload()
        self.assertEqual(len(self.window._cards), 60)
        self.window.load_more()
        self.assertEqual(len(self.window._cards), 65)
        self.assertEqual(len({c.record["id"] for c in self.window._cards}), 65)
        image = self.image()
        Path(image["image_path"]).unlink()
        APP.clipboard().setText("original clipboard")
        with patch.object(main_window, "paste_to_window") as paste:
            self.window.auto_paste(image)
            APP.processEvents()
            paste.assert_not_called()
        self.assertEqual(APP.clipboard().text(), "original clipboard")
        self.assertTrue(self.window.isVisible())

    def test_render_layouts(self):
        pin = self.text("常用回复\n收到，我会在今天下午整理好资料发给你。")
        self.storage.toggle_pin(pin["id"])
        long_text = self.text("把想法留住，让工作继续。\n\n每次复制的文字和图片，都会自动收集在这里。\n\n今天的待办\n• 整理项目资料\n• 确认界面方案\n• 保存常用回复\n\n操作提示\n单击查看完整内容，双击粘贴到原窗口。\n使用 ↑ / ↓ 浏览记录，Ctrl+C 复制所选内容。\n\n代码缩进也会完整保留：\n    def hello():\n        return '你好，世界'\n")
        image = self.image()
        self.text("https://example.com/design/inspiration")
        self.text("会议笔记\n统一留白、降低视觉噪音，把常用操作放在容易找到的位置。")
        self.window.reload()
        self.window.activate_record(long_text)
        APP.processEvents()
        self.window.grab().save(str(ARTIFACTS / "text.png"))
        self.window.activate_record(image)
        APP.processEvents()
        self.window.grab().save(str(ARTIFACTS / "image.png"))
        self.window.resize(760, 580)
        APP.processEvents()
        self.window.grab().save(str(ARTIFACTS / "compact.png"))
        self.window.manage_btn.setChecked(True)
        self.window.select_all()
        APP.processEvents()
        self.window.grab().save(str(ARTIFACTS / "multiselect.png"))
        self.window.manage_btn.setChecked(False)
        self.window.search_edit.setText("no matching content")
        self.window.reload()
        APP.processEvents()
        self.window.grab().save(str(ARTIFACTS / "empty.png"))
        dialog = SettingsDialog(self.storage, self.window)
        self.assertFalse(dialog.quick_paste_check.isChecked())
        dialog.show()
        APP.processEvents()
        dialog.grab().save(str(ARTIFACTS / "settings.png"))
        dialog.reject()

    def test_pending_search_and_paste_target_guards(self):
        old = self.text("old result")
        new = self.text("new result")
        self.window.reload()
        self.window.activate_record(old)
        self.window.search_edit.setText("new result")
        with patch.object(self.window, "auto_paste") as paste:
            self.window._paste_active()
            self.assertEqual(paste.call_args.args[0]["id"], new["id"])
        with patch.object(win32utils, "user32") as api, patch.object(win32utils, "send_ctrl_v") as send:
            api.IsWindow.return_value = False
            self.assertFalse(win32utils.paste_to_window(123))
            send.assert_not_called()
            api.IsWindow.return_value = True
            api.IsIconic.return_value = False
            api.GetForegroundWindow.return_value = 456
            self.assertFalse(win32utils.paste_to_window(123))
            send.assert_not_called()
            api.GetForegroundWindow.return_value = 123
            api.GetAsyncKeyState.return_value = 0x8000
            self.assertFalse(win32utils.paste_to_window(123))
            send.assert_not_called()
            api.GetAsyncKeyState.return_value = 0
            send.return_value = True
            self.assertTrue(win32utils.paste_to_window(123))
            send.assert_called_once()

    def test_live_refresh_preserves_scroll_and_pagination(self):
        for i in range(65):
            self.text(f"滚动内容 {i}")
        self.window.reload()
        self.window.load_more()
        APP.processEvents()
        card = self.window._cards[40]
        self.window.activate_record(card.record)
        self.window.scroll.ensureWidgetVisible(card)
        APP.processEvents()
        position = self.window.scroll.verticalScrollBar().value()
        self.assertGreater(position, 0)
        self.window._on_new_record(self.text("新记录，不打断阅读"))
        APP.processEvents()
        self.assertEqual(self.window._active_id, card.record["id"])
        self.assertEqual(self.window.scroll.verticalScrollBar().value(), position)
        self.assertEqual(self.window._loaded, 65)
        self.window.load_more()
        self.assertEqual(len({c.record["id"] for c in self.window._cards}), 66)

    def drag_move(self, widget, point, modifiers=Qt.NoModifier):
        event = QMouseEvent(QEvent.MouseMove, QPointF(point),
                            QPointF(widget.mapToGlobal(point)), Qt.NoButton,
                            Qt.LeftButton, modifiers)
        QApplication.sendEvent(widget, event)

    def test_drag_from_card_without_entering_manage_mode(self):
        for i in range(5):
            self.text(f"框选记录 {i}")
        self.window.storage.settings["quick_paste"] = True
        self.window.reload()
        APP.processEvents()
        card = self.window._cards[0]
        end = card.mapFromGlobal(self.window._cards[2].mapToGlobal(QPoint(80, 45)))
        with patch.object(self.window, "auto_paste") as paste:
            QTest.mousePress(card, Qt.LeftButton, pos=QPoint(60, 35))
            self.drag_move(card, end)
            self.assertTrue(self.window.rubber.isVisible())
            self.assertTrue(self.window.manage_mode)
            QTest.mouseRelease(card, Qt.LeftButton, pos=end)
            self.assertEqual(self.window._selected, {c.record["id"] for c in self.window._cards[:3]})
            self.assertFalse(self.window.rubber.isVisible())
            paste.assert_not_called()

    def test_drag_from_blank_ctrl_add_and_reverse_replace(self):
        for i in range(5):
            self.text(f"追加框选 {i}")
        self.window.reload()
        APP.processEvents()
        self.window.manage_btn.setChecked(True)
        self.window.toggle_select(self.window._cards[4].record["id"])
        container = self.window.list_container
        start = QPoint(container.width() - 4, 5)
        end = self.window._cards[1].geometry().topLeft() + QPoint(30, 40)
        QTest.mousePress(container, Qt.LeftButton, Qt.ControlModifier, start)
        self.drag_move(container, end, Qt.ControlModifier)
        QTest.mouseRelease(container, Qt.LeftButton, Qt.ControlModifier, end)
        self.assertEqual(self.window._selected, {self.window._cards[i].record["id"] for i in (0, 1, 4)})
        card = self.window._cards[2]
        start = QPoint(90, 55)
        end = card.mapFromGlobal(self.window._cards[1].mapToGlobal(QPoint(30, 35)))
        QTest.mousePress(card, Qt.LeftButton, pos=start)
        self.drag_move(card, end)
        QTest.mouseRelease(card, Qt.LeftButton, pos=end)
        self.assertEqual(self.window._selected, {self.window._cards[i].record["id"] for i in (1, 2)})

    def test_drag_autoscroll_and_deferred_live_refresh(self):
        for i in range(30):
            self.text(f"跨屏框选 {i}")
        self.window.reload()
        APP.processEvents()
        card = self.window._cards[0]
        QTest.mousePress(card, Qt.LeftButton, pos=QPoint(40, 30))
        end = card.mapFromGlobal(self.window.scroll.viewport().mapToGlobal(QPoint(100, self.window.scroll.viewport().height() - 3)))
        self.drag_move(card, end)
        APP.processEvents()
        self.window._scroll_box_drag()
        self.assertGreater(self.window.scroll.verticalScrollBar().value(), 0)
        self.window._on_new_record(self.text("拖动时的新内容"))
        self.assertTrue(self.window._reload_after_drag)
        self.assertEqual(len(self.window._cards), 30)
        QTest.mouseRelease(card, Qt.LeftButton, pos=end)
        self.assertFalse(self.window._drag_scroll_timer.isActive())
        APP.processEvents()
        self.assertEqual(len(self.window._cards), 31)
        self.assertGreater(len(self.window._selected), 1)

    def test_pinned_images_move_zoom_topmost_and_survive_hidden_main(self):
        record = self.image()
        self.window.reload()
        self.window.activate_record(record)
        self.assertTrue(self.window.screen_pin_btn.isVisible())
        floating = self.window.pin_image(record)
        APP.processEvents()
        self.assertIsNotNone(floating)
        self.assertTrue(floating.windowFlags() & Qt.WindowStaysOnTopHint)
        self.assertEqual(len(self.window._image_windows), 1)
        self.assertIs(self.window.pin_image(record), floating)
        self.text("创建另一张贴图")
        other_record = self.image()
        other_floating = self.window.pin_image(other_record)
        APP.processEvents()
        self.assertEqual(len(self.window._image_windows), 2)
        self.window.hide()
        self.assertTrue(floating.isVisible())
        self.assertTrue(other_floating.isVisible())
        before = floating.pos()
        QTest.mousePress(floating.canvas, Qt.LeftButton, pos=QPoint(30, 30))
        self.drag_move(floating.canvas, QPoint(75, 60))
        QTest.mouseRelease(floating.canvas, Qt.LeftButton, pos=QPoint(75, 60))
        self.assertEqual(floating.pos(), before + QPoint(45, 30))
        before_zoom = floating.zoom
        wheel = QWheelEvent(QPointF(40, 40), QPointF(floating.canvas.mapToGlobal(QPoint(40, 40))),
                            QPoint(), QPoint(0, -120), Qt.NoButton, Qt.NoModifier,
                            Qt.NoScrollPhase, False)
        QApplication.sendEvent(floating.canvas, wheel)
        APP.processEvents()
        self.assertLess(floating.zoom, before_zoom)
        floating.toggle_topmost(False)
        self.assertFalse(floating.windowFlags() & Qt.WindowStaysOnTopHint)
        floating.toggle_topmost(True)
        self.assertTrue(floating.windowFlags() & Qt.WindowStaysOnTopHint)
        Path(record["image_path"]).unlink()
        floating.copy_image()
        self.assertEqual(APP.clipboard().image().size(), floating.source.size())
        self.assertIsNone(self.window.pin_image(self.text("文字不能贴图")))
        self.assertIsNone(self.window.pin_image({**record, "id": -1}))
        floating.grab().save(str(ARTIFACTS / "pinned-image.png"))
        # 将透明浮窗渲染在示例深色桌面上，预览能准确展示光晕的透明度。
        demo = QPixmap(floating.size() + QSize(96, 96))
        demo.fill(QColor("#101620"))
        painter = QPainter(demo)
        painter.drawPixmap(48, 48, floating.grab())
        painter.end()
        demo.save(str(ARTIFACTS / "pinned-demo.png"))
        floating.close()
        APP.processEvents()
        self.assertEqual(len(self.window._image_windows), 1)
        self.window.close_all_images()
        self.assertEqual(len(self.window._image_windows), 0)

    def test_borderless_pin_preserves_pixels_transparency_and_faint_glow(self):
        source = QImage(160, 100, QImage.Format_ARGB32)
        source.fill(Qt.transparent)
        painter = QPainter(source)
        painter.fillRect(40, 30, 80, 40, QColor("#5277DE"))
        painter.end()
        floating = PinnedImageWindow(QPixmap.fromImage(source))
        try:
            floating.set_zoom(1)
            floating.show()
            APP.processEvents()
            self.assertEqual(floating.canvas.size(), source.size())
            self.assertFalse(hasattr(floating, "toolbar"))
            image = floating.grab().toImage()
            margin = GLOW_MARGIN
            self.assertEqual(image.pixelColor(margin + 5, margin + 50).alpha(), 0)
            self.assertEqual(image.pixelColor(margin + 80, margin + 50), QColor("#5277DE"))
            self.assertLessEqual(image.pixelColor(0, margin + 50).alpha(), 2)
            self.assertGreater(image.pixelColor(margin - 2, margin + 50).alpha(), 0)
            self.assertLess(image.pixelColor(margin - 2, margin + 50).alpha(), 50)
            copied = []
            floating.copy_requested.connect(copied.append)
            floating.copy_image()
            self.assertEqual(len(copied), 1)
            self.assertEqual(copied[0].convertToFormat(QImage.Format_ARGB32), source)
            floating.grab().save(str(ARTIFACTS / "transparent-pin.png"))
            QTest.mouseClick(floating.close_btn, Qt.LeftButton)
            self.assertFalse(floating.isVisible())
        finally:
            floating.close()

    def test_quick_pin_reads_current_clipboard_while_hidden_and_paused(self):
        old_record = self.image()
        current = QImage(240, 140, QImage.Format_ARGB32)
        current.fill(QColor("#57AFA1"))
        APP.clipboard().setImage(current)
        self.monitor.set_paused(True)
        self.window.hide()
        before = self.storage.count()
        floating = self.window.pin_clipboard_image()
        APP.processEvents()
        self.assertIsNotNone(floating)
        self.assertFalse(self.window.isVisible())
        self.assertEqual(floating.source.size(), current.size())
        self.assertEqual(floating.source.toImage().pixelColor(20, 20), QColor("#57AFA1"))
        self.assertEqual(self.storage.count(), before)
        self.assertNotEqual(floating.source.size(), QImage(old_record["image_path"]).size())
        APP.clipboard().setText("只有文字，不应贴出历史图片")
        self.assertIsNone(self.window.pin_clipboard_image())
        self.assertEqual(len(self.window._image_windows), 1)

    def test_q_one_native_callback_queues_pin_without_main_window(self):
        image = QImage(160, 100, QImage.Format_ARGB32)
        image.fill(QColor("#A571DB"))
        APP.clipboard().setImage(image)
        self.window.hide()
        hook = QuickPinHotkey()
        hook.activated.connect(self.window.pin_clipboard_image, Qt.QueuedConnection)
        q = KBDLLHOOKSTRUCT(VK_Q, 0x10, 0, 0, 0)
        one = KBDLLHOOKSTRUCT(0x31, 0x02, 0, 0, 0)
        with patch("quick_pin_hotkey.user32.CallNextHookEx", return_value=0):
            hook._callback(0, 0x0100, ctypes.addressof(q))
            hook._callback(0, 0x0100, ctypes.addressof(one))
            self.assertEqual(len(self.window._image_windows), 0)
            APP.processEvents()
            self.assertEqual(len(self.window._image_windows), 1)
            for _ in range(5):
                hook._callback(0, 0x0100, ctypes.addressof(one))
            hook._callback(0, 0x0101, ctypes.addressof(one))
            hook._callback(0, 0x0101, ctypes.addressof(q))
            APP.processEvents()
            self.assertEqual(len(self.window._image_windows), 1)
            self.assertFalse(self.window.isVisible())

    def test_quick_pin_accepts_single_copied_image_file(self):
        record = self.image()
        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(record["image_path"])])
        APP.clipboard().setMimeData(mime)
        self.window.hide()
        floating = self.window.pin_clipboard_image()
        self.assertIsNotNone(floating)
        self.assertEqual(floating.source.size(), QImage(record["image_path"]).size())


if __name__ == "__main__":
    unittest.main(verbosity=2)
