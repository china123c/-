# -*- coding: utf-8 -*-
"""历史剪贴板 —— 程序入口。

负责：单实例、托盘图标、全局热键、开机自启、组装各个模块。
"""
import sys

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QAction, QGuiApplication
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from main_window import MainWindow
from monitor import ClipboardMonitor
from quick_pin_hotkey import QuickPinHotkey
from storage import Storage
from theme import apply_theme, make_app_icon
from win32utils import (
    HotkeyFilter, register_hotkey, set_autostart, show_message, unregister_hotkey,
)

IPC_NAME = "HistoryClipboard_IPC"


class SingleInstance(QObject):
    """单实例：第二个实例启动时通知已运行的实例打开窗口，然后自己退出。"""

    show_requested = Signal()

    def __init__(self):
        super().__init__()
        self.server = QLocalServer(self)

    def try_primary(self):
        sock = QLocalSocket()
        sock.connectToServer(IPC_NAME)
        if sock.waitForConnected(400):
            sock.write(b"show")
            sock.flush()
            sock.waitForBytesWritten(400)
            sock.disconnectFromServer()
            return "signaled"
        QLocalServer.removeServer(IPC_NAME)
        if self.server.listen(IPC_NAME):
            self.server.newConnection.connect(self._on_new_connection)
            return "primary"
        return "failed"

    def _on_new_connection(self):
        conn = self.server.nextPendingConnection()
        conn.readyRead.connect(lambda: self._on_data(conn))

    def _on_data(self, conn):
        if b"show" in bytes(conn.readAll().data()):
            self.show_requested.emit()
        conn.disconnectFromServer()


def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setApplicationName("历史剪贴板")
    apply_theme(app)
    icon = make_app_icon()
    app.setWindowIcon(icon)

    single = SingleInstance()
    result = single.try_primary()
    if result == "signaled":
        return 0  # 已有实例在运行，已通知它打开窗口
    if result == "failed":
        show_message("历史剪贴板", "软件已经在运行啦！\n请点击屏幕右下角的托盘图标打开。")
        return 0

    storage = Storage()
    storage.cleanup()

    # 打包成 exe 后，每次启动同步“开机自启”设置
    if getattr(sys, "frozen", False):
        set_autostart(storage.settings["autostart"])

    monitor = ClipboardMonitor(storage, QGuiApplication.clipboard())
    window = MainWindow(storage, monitor)
    app.aboutToQuit.connect(window.close_all_images)
    single.show_requested.connect(window.show_and_raise)

    # ---- 系统托盘 ----
    tray = QSystemTrayIcon(icon, app)
    tray.setToolTip("历史剪贴板（记录中）\nQ+1 贴图 · Ctrl+Alt+V 打开历史")
    menu = QMenu()
    act_open = QAction("打开历史", menu)
    act_open.triggered.connect(window.show_and_raise)
    act_settings = QAction("设置…", menu)
    act_settings.triggered.connect(window.open_settings)
    act_pin = QAction("贴屏当前图片（Q+1）", menu)
    act_pin.triggered.connect(window.pin_clipboard_image)
    act_pause = QAction("暂停记录", menu)
    act_pause.setCheckable(True)

    def on_pause(checked):
        monitor.set_paused(checked)

    def sync_pause(checked):
        act_pause.setChecked(checked)
        tray.setToolTip(("历史剪贴板（已暂停）" if checked else "历史剪贴板（记录中）")
                        + "\nQ+1 贴图 · Ctrl+Alt+V 打开历史")

    monitor.paused_changed.connect(sync_pause)
    act_pause.triggered.connect(on_pause)
    act_quit = QAction("退出", menu)
    act_quit.triggered.connect(app.quit)
    menu.addAction(act_open)
    menu.addAction(act_pin)
    menu.addAction(act_settings)
    menu.addSeparator()
    menu.addAction(act_pause)
    menu.addSeparator()
    menu.addAction(act_quit)
    tray.setContextMenu(menu)
    tray.activated.connect(
        lambda reason: window.show_and_raise()
        if reason == QSystemTrayIcon.ActivationReason.Trigger
        else None
    )
    tray.show()
    window.tray = tray
    tray.menu = menu  # 防止菜单被垃圾回收

    monitor.start()

    # ---- 全局热键 Ctrl+Alt+V ----
    hotkey_filter = HotkeyFilter(window.show_and_raise)
    app.installNativeEventFilter(hotkey_filter)
    hwnd = int(window.winId())
    if not register_hotkey(hwnd):
        tray.showMessage(
            "历史剪贴板", "全局快捷键 Ctrl+Alt+V 注册失败（可能被其他软件占用）",
            QSystemTrayIcon.MessageIcon.Warning, 5000,
        )
    app.aboutToQuit.connect(lambda: unregister_hotkey(hwnd))

    # Q 是普通字符，使用独立组合键钩子；耗时操作排到 Qt 事件循环。
    quick_pin = QuickPinHotkey(app)
    quick_pin.activated.connect(window.pin_clipboard_image, Qt.QueuedConnection)
    if not quick_pin.start():
        tray.showMessage("历史剪贴板", "Q+1 快捷键启用失败，仍可从历史或托盘菜单贴图。",
                         QSystemTrayIcon.MessageIcon.Warning, 5000)
    app.aboutToQuit.connect(quick_pin.stop)

    # ---- 启动方式：开机自启时静默，手动打开时显示窗口 ----
    if "--hidden" in sys.argv:
        tray.showMessage(
            "历史剪贴板", "已在后台运行，开始记录剪贴板。\n按 Ctrl+Alt+V 呼出历史窗口。",
            QSystemTrayIcon.MessageIcon.Information, 3000,
        )
    else:
        window.show_and_raise()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
