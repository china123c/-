# -*- coding: utf-8 -*-
"""Windows 相关功能：全局热键、模拟 Ctrl+V、开机自启、提示框。"""
import ctypes
import os
import sys
import winreg
from ctypes import wintypes

from PySide6.QtCore import QAbstractNativeEventFilter

user32 = ctypes.windll.user32

# ---------- 全局热键 Ctrl+Alt+V ----------
WM_HOTKEY = 0x0312
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
VK_V = 0x56
HOTKEY_ID = 1


class HotkeyFilter(QAbstractNativeEventFilter):
    """捕获 WM_HOTKEY 消息，触发回调（切换主窗口显示）。"""

    def __init__(self, callback):
        super().__init__()
        self.callback = callback

    def nativeEventFilter(self, event_type, message):
        msg = wintypes.MSG.from_address(int(message))
        if msg.message == WM_HOTKEY and msg.wParam == HOTKEY_ID:
            self.callback()
        return False, 0


user32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_uint, ctypes.c_uint]
user32.RegisterHotKey.restype = wintypes.BOOL
user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]


def register_hotkey(hwnd):
    return bool(user32.RegisterHotKey(hwnd, HOTKEY_ID, MOD_CONTROL | MOD_ALT, VK_V))


def unregister_hotkey(hwnd):
    try:
        user32.UnregisterHotKey(hwnd, HOTKEY_ID)
    except Exception:
        pass


# ---------- 模拟按键 Ctrl+V（自动粘贴） ----------
INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
VK_CONTROL = 0x11


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD),
    ]


class _INPUTUNION(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [("type", wintypes.DWORD), ("u", _INPUTUNION)]


user32.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int]
user32.SendInput.restype = wintypes.UINT


def send_ctrl_v():
    """向当前前台窗口发送 Ctrl+V。"""
    events = (INPUT * 4)()
    events[0].type = INPUT_KEYBOARD
    events[0].ki.wVk = VK_CONTROL
    events[1].type = INPUT_KEYBOARD
    events[1].ki.wVk = VK_V
    events[2].type = INPUT_KEYBOARD
    events[2].ki.wVk = VK_V
    events[2].ki.dwFlags = KEYEVENTF_KEYUP
    events[3].type = INPUT_KEYBOARD
    events[3].ki.wVk = VK_CONTROL
    events[3].ki.dwFlags = KEYEVENTF_KEYUP
    return user32.SendInput(4, events, ctypes.sizeof(INPUT)) == 4


user32.GetForegroundWindow.restype = wintypes.HWND
user32.SetForegroundWindow.argtypes = [wintypes.HWND]
user32.SetForegroundWindow.restype = wintypes.BOOL
user32.IsWindow.argtypes = [wintypes.HWND]
user32.IsWindow.restype = wintypes.BOOL
user32.IsIconic.argtypes = [wintypes.HWND]
user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]


def get_foreground_window():
    """记录打开历史前的目标窗口，排除本程序自己的窗口。"""
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return None
    process_id = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(process_id))
    return hwnd if process_id.value != os.getpid() else None


def paste_to_window(hwnd):
    """只有目标仍有效、已切到前台且修饰键已松开时才发送粘贴。"""
    if not hwnd or not user32.IsWindow(hwnd):
        return False
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, 9)  # SW_RESTORE
    user32.SetForegroundWindow(hwnd)
    if user32.GetForegroundWindow() != hwnd:
        return False
    # 避免 Ctrl+Alt+V 热键尚未释放时发送带 Alt 的组合键。
    if any(user32.GetAsyncKeyState(key) & 0x8000 for key in (0x10, 0x11, 0x12, 0x5B, 0x5C)):
        return False
    return send_ctrl_v()


# ---------- 开机自启 ----------
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
APP_NAME = "历史剪贴板"


def startup_command():
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}" --hidden'
    return f'"{sys.executable}" "{os.path.abspath(sys.argv[0])}" --hidden'


def set_autostart(enabled):
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE)
    except OSError:
        return False
    try:
        if enabled:
            winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, startup_command())
        else:
            try:
                winreg.DeleteValue(key, APP_NAME)
            except FileNotFoundError:
                pass
        return True
    finally:
        winreg.CloseKey(key)


# ---------- 消息框 ----------
user32.MessageBoxW.argtypes = [wintypes.HWND, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.UINT]
user32.MessageBoxW.restype = ctypes.c_int


def show_message(title, text):
    user32.MessageBoxW(None, text, title, 0x40)  # MB_ICONINFORMATION


def enable_dark_titlebar(hwnd):
    """使 Windows 标题栏与应用的深色主题一致，不修改系统主题。"""
    try:
        setter = ctypes.windll.dwmapi.DwmSetWindowAttribute
        setter.argtypes = [wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]
        setter.restype = ctypes.c_long
        enabled = wintypes.BOOL(True)
        result = setter(hwnd, 20, ctypes.byref(enabled), ctypes.sizeof(enabled))
        if result != 0:
            result = setter(hwnd, 19, ctypes.byref(enabled), ctypes.sizeof(enabled))
        return result == 0
    except (AttributeError, OSError):
        return False
