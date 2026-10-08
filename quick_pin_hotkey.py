# -*- coding: utf-8 -*-
"""全局 Q+1：Q 作为组合前缀，未组合时回放正常输入。"""
import ctypes
import threading
from ctypes import wintypes

from PySide6.QtCore import QObject, Signal

from win32utils import INPUT, INPUT_KEYBOARD, KEYEVENTF_KEYUP, user32

VK_Q = 0x51
ONE_KEYS = {0x31, 0x61}  # 主键盘 1 和小键盘 1
MODIFIER_KEYS = {0x10, 0x11, 0x12, 0x5B, 0x5C, 0xA0, 0xA1, 0xA2, 0xA3, 0xA4, 0xA5}
LLKHF_INJECTED = 0x10
LLKHF_EXTENDED = 0x01
WH_KEYBOARD_LL = 13
KEY_MESSAGES = {0x0100: True, 0x0101: False, 0x0104: True, 0x0105: False}


class QOneChord:
    """独立的组合状态机；不在键盘回调里读取剪贴板或创建窗口。"""

    def __init__(self, trigger, replay, q_forwarded=False, ones_down=()):
        self.trigger = trigger
        self.replay = replay
        self.q_forwarded = q_forwarded
        self.ones_down = set(ones_down)
        self.q_held = False
        self.fired = False
        self.pending = []
        self.swallowed_ones = set()

    def handle(self, vk, scan, flags, down, modifiers=False):
        if flags & LLKHF_INJECTED:
            return False
        packet = (vk, scan, bool(flags & LLKHF_EXTENDED), not down)
        repeated_one = vk in self.ones_down
        if vk in ONE_KEYS:
            if down:
                self.ones_down.add(vk)
            else:
                self.ones_down.discard(vk)
        if vk in self.swallowed_ones:
            if not down:
                self.swallowed_ones.discard(vk)
            return True

        if vk == VK_Q:
            if down:
                if self.q_forwarded:
                    return False
                if self.q_held:
                    if not self.fired:
                        self.pending.append(packet)
                    return True
                if modifiers:
                    self.q_forwarded = True
                    return False
                self.q_held = True
                self.fired = False
                self.pending = [packet]
                return True
            if self.q_forwarded:
                self.q_forwarded = False
                return False
            if self.q_held:
                pending = self.pending
                fired = self.fired
                self.q_held = False
                self.pending = []
                self.fired = False
                if not fired:
                    self.replay(pending + [packet])
                return True
            return False

        if self.q_held:
            if self.fired and down and vk in ONE_KEYS and not modifiers:
                self.swallowed_ones.add(vk)
                return True
            if down and vk in ONE_KEYS and not repeated_one and not modifiers and not self.fired:
                self.pending = []
                self.fired = True
                self.swallowed_ones.add(vk)
                self.trigger()
                return True
            if not self.fired:
                # 同一批回放 Q 和后续事件，保持快速输入时的字符顺序。
                pending = self.pending
                self.pending = []
                self.q_held = False
                self.q_forwarded = True
                return bool(self.replay(pending + [packet]))
        return False

    def finish(self):
        if self.pending:
            last = self.pending[-1]
            self.replay(self.pending + [(last[0], last[1], last[2], True)])
        self.pending = []
        self.q_held = False
        self.fired = False
        self.swallowed_ones.clear()


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode", wintypes.DWORD), ("scanCode", wintypes.DWORD),
        ("flags", wintypes.DWORD), ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


HOOKPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
user32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC, wintypes.HINSTANCE, wintypes.DWORD]
user32.SetWindowsHookExW.restype = ctypes.c_void_p
user32.UnhookWindowsHookEx.argtypes = [ctypes.c_void_p]
user32.UnhookWindowsHookEx.restype = wintypes.BOOL
user32.CallNextHookEx.argtypes = [ctypes.c_void_p, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
user32.CallNextHookEx.restype = ctypes.c_ssize_t
user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
user32.GetAsyncKeyState.restype = ctypes.c_short
kernel32 = ctypes.windll.kernel32
kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
kernel32.GetModuleHandleW.restype = wintypes.HMODULE
kernel32.GetCurrentThreadId.restype = wintypes.DWORD
user32.PeekMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT, wintypes.UINT]
user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
user32.GetMessageW.restype = ctypes.c_int
user32.PostThreadMessageW.argtypes = [wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.PostThreadMessageW.restype = wintypes.BOOL


class QuickPinHotkey(QObject):
    activated = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._hook = None
        self._thread = None
        self._thread_id = 0
        self._ready = threading.Event()
        self._callback_ref = HOOKPROC(self._callback)
        self._modifiers = set()
        self.state = QOneChord(self.activated.emit, self._replay)

    def start(self):
        if self._hook:
            return True
        self._ready.clear()
        self._thread = threading.Thread(target=self._run, name="QOneHotkey", daemon=True)
        self._thread.start()
        if not self._ready.wait(2):
            self.stop()
            return False
        return bool(self._hook)

    def _run(self):
        # 独立消息循环，避免图片解码或 SQLite 操作阻塞键盘钩子。
        self._thread_id = kernel32.GetCurrentThreadId()
        message = wintypes.MSG()
        user32.PeekMessageW(ctypes.byref(message), None, 0, 0, 0)
        self._modifiers = {key for key in MODIFIER_KEYS if user32.GetAsyncKeyState(key) & 0x8000}
        self.state = QOneChord(
            self.activated.emit, self._replay,
            q_forwarded=bool(user32.GetAsyncKeyState(VK_Q) & 0x8000),
            ones_down={key for key in ONE_KEYS if user32.GetAsyncKeyState(key) & 0x8000},
        )
        self._hook = user32.SetWindowsHookExW(
            WH_KEYBOARD_LL, self._callback_ref, kernel32.GetModuleHandleW(None), 0)
        self._ready.set()
        try:
            if self._hook:
                while user32.GetMessageW(ctypes.byref(message), None, 0, 0) > 0:
                    pass
        finally:
            if self._hook:
                user32.UnhookWindowsHookEx(self._hook)
                self._hook = None
            self.state.finish()
            self._modifiers.clear()

    def stop(self):
        if self._thread and self._thread.is_alive():
            user32.PostThreadMessageW(self._thread_id, 0x0012, 0, 0)  # WM_QUIT
            self._thread.join(timeout=2)

    def _callback(self, code, message, address):
        if code >= 0 and message in KEY_MESSAGES:
            key = KBDLLHOOKSTRUCT.from_address(address)
            if not key.flags & LLKHF_INJECTED:
                down = KEY_MESSAGES[message]
                if key.vkCode in MODIFIER_KEYS:
                    if down:
                        self._modifiers.add(key.vkCode)
                    else:
                        self._modifiers.discard(key.vkCode)
                if self.state.handle(key.vkCode, key.scanCode, key.flags, down, bool(self._modifiers)):
                    return 1
        return user32.CallNextHookEx(self._hook, code, message, address)

    def _replay(self, packets):
        if not packets:
            return True
        events = (INPUT * len(packets))()
        for event, (vk, scan, extended, up) in zip(events, packets):
            event.type = INPUT_KEYBOARD
            event.ki.wVk = vk
            event.ki.wScan = scan
            event.ki.dwFlags = (1 if extended else 0) | (KEYEVENTF_KEYUP if up else 0)
        return user32.SendInput(len(events), events, ctypes.sizeof(INPUT)) == len(events)
