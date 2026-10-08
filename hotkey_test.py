# -*- coding: utf-8 -*-
"""Q+1 组合键回归；回放输入使用假实现，不向用户窗口发送按键。"""
import ctypes
import unittest
from unittest.mock import patch

from quick_pin_hotkey import KBDLLHOOKSTRUCT, LLKHF_INJECTED, QOneChord, QuickPinHotkey, VK_Q


class ChordTests(unittest.TestCase):
    def setUp(self):
        self.triggered = []
        self.replayed = []
        self.chord = QOneChord(lambda: self.triggered.append(True), self.replay)

    def replay(self, packets):
        self.replayed.extend(packets)
        return True

    def key(self, vk, down=True, flags=0, modifiers=False):
        return self.chord.handle(vk, 0x10 if vk == VK_Q else 0x02, flags, down, modifiers)

    def test_chord_suppresses_both_keys_and_autorepeat(self):
        self.assertTrue(self.key(VK_Q))
        self.assertTrue(self.key(0x31))
        for _ in range(10):
            self.assertTrue(self.key(0x31))
            self.assertTrue(self.key(VK_Q))
        self.assertTrue(self.key(VK_Q, False))
        self.assertTrue(self.key(0x31))  # 先松 Q 时，仍吞掉 1 的长按重复。
        self.assertTrue(self.key(0x31, False))
        self.assertEqual(self.triggered, [True])
        self.assertEqual(self.replayed, [])

    def test_tapping_one_again_while_q_is_held_does_not_type_one(self):
        self.key(VK_Q)
        for vk in (0x31, 0x31, 0x61):
            self.assertTrue(self.key(vk))
            self.assertTrue(self.key(vk, False))
        self.assertTrue(self.key(VK_Q, False))
        self.assertEqual(self.triggered, [True])
        self.assertEqual(self.replayed, [])

    def test_q_alone_and_repeats_are_replayed(self):
        self.assertTrue(self.key(VK_Q))
        self.assertTrue(self.key(VK_Q))
        self.assertTrue(self.key(VK_Q, False))
        self.assertEqual([p[0] for p in self.replayed], [VK_Q, VK_Q, VK_Q])
        self.assertEqual([p[3] for p in self.replayed], [False, False, True])
        self.assertEqual(self.triggered, [])

    def test_fast_typing_keeps_q_then_other_key_order(self):
        self.key(VK_Q)
        self.assertTrue(self.key(0x55))
        self.assertEqual([p[0] for p in self.replayed], [VK_Q, 0x55])
        self.assertFalse(self.key(VK_Q))  # 已回放 Q 的后续重复正常放行。
        self.assertFalse(self.key(VK_Q, False))
        self.assertFalse(self.key(0x55, False))
        self.assertEqual(self.triggered, [])

    def test_modifier_shortcuts_and_injected_events_are_unchanged(self):
        self.assertFalse(self.key(VK_Q, modifiers=True))
        self.assertFalse(self.key(0x31, modifiers=True))
        self.assertFalse(self.key(VK_Q, False, modifiers=True))
        self.assertFalse(self.key(VK_Q, flags=LLKHF_INJECTED))
        self.assertEqual(self.triggered, [])
        self.assertEqual(self.replayed, [])

    def test_modifier_pressed_after_q_cancels_candidate(self):
        self.key(VK_Q)
        self.assertTrue(self.key(0xA2, modifiers=True))
        self.assertFalse(self.key(0x31, modifiers=True))
        self.assertEqual([p[0] for p in self.replayed], [VK_Q, 0xA2])
        self.assertEqual(self.triggered, [])

    def test_one_pressed_first_does_not_form_chord(self):
        self.assertFalse(self.key(0x31))
        self.key(VK_Q)
        self.assertTrue(self.key(0x31))  # 旧的 1 长按：回放 Q 和当前事件。
        self.assertEqual(self.triggered, [])
        self.assertEqual([p[0] for p in self.replayed], [VK_Q, 0x31])

    def test_numpad_and_new_gesture_can_trigger_again(self):
        for vk in (0x61, 0x31):
            self.key(VK_Q)
            self.assertTrue(self.key(vk))
            self.key(vk, False)
            self.key(VK_Q, False)
        self.assertEqual(len(self.triggered), 2)
        self.assertEqual(self.replayed, [])

    def test_shutdown_replays_pending_q_and_releases_it(self):
        self.key(VK_Q)
        self.chord.finish()
        self.assertEqual([p[3] for p in self.replayed], [False, True])
        self.assertFalse(self.chord.q_held)

    def test_native_callback_forwards_plain_keys_and_signals_chord(self):
        hook = QuickPinHotkey()
        fired = []
        hook.activated.connect(lambda: fired.append(True))
        with patch("quick_pin_hotkey.user32.CallNextHookEx", return_value=77):
            plain = KBDLLHOOKSTRUCT(0x41, 0x1E, 0, 0, 0)
            self.assertEqual(hook._callback(0, 0x0100, ctypes.addressof(plain)), 77)
            q = KBDLLHOOKSTRUCT(VK_Q, 0x10, 0, 0, 0)
            one = KBDLLHOOKSTRUCT(0x31, 0x02, 0, 0, 0)
            self.assertEqual(hook._callback(0, 0x0100, ctypes.addressof(q)), 1)
            self.assertEqual(hook._callback(0, 0x0100, ctypes.addressof(one)), 1)
            self.assertEqual(fired, [True])
            self.assertEqual(hook._callback(0, 0x0101, ctypes.addressof(one)), 1)
            self.assertEqual(hook._callback(0, 0x0101, ctypes.addressof(q)), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
