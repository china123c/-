# -*- coding: utf-8 -*-
"""设置窗口：保留天数、存储上限、开机自启。"""
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QGroupBox, QHBoxLayout, QLabel, QMessageBox,
    QPushButton, QSpinBox, QVBoxLayout,
)

from win32utils import enable_dark_titlebar, set_autostart

RETENTION_CHOICES = [1, 3, 5, 7, 30, 365]


class SettingsDialog(QDialog):
    def __init__(self, storage, parent=None):
        super().__init__(parent)
        self.storage = storage
        self.setWindowTitle("设置")
        self.setFixedWidth(460)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 18, 22, 16)
        lay.setSpacing(10)

        title = QLabel("设置")
        title.setObjectName("title")
        lay.addWidget(title)

        # 存储设置
        store_box = QGroupBox("存储")
        store_lay = QVBoxLayout(store_box)
        store_lay.setSpacing(8)

        store_lay.addWidget(QLabel("历史保留天数"))
        self.days_combo = QComboBox()
        for days in RETENTION_CHOICES:
            self.days_combo.addItem(f"{days} 天", days)
        idx = self.days_combo.findData(storage.settings["retention_days"])
        self.days_combo.setCurrentIndex(idx if idx >= 0 else len(RETENTION_CHOICES) - 1)
        store_lay.addWidget(self.days_combo)

        store_lay.addSpacing(4)
        limit_label = QLabel("存储上限")
        limit_label.setToolTip("超出上限时清理最旧的非置顶内容")
        store_lay.addWidget(limit_label)
        self.limit_spin = QSpinBox()
        self.limit_spin.setRange(50, 10000)
        self.limit_spin.setValue(storage.settings["size_limit_mb"])
        self.limit_spin.setSuffix(" MB")
        store_lay.addWidget(self.limit_spin)

        used_mb = storage.total_size() / 1024 / 1024
        usage = QLabel(f"当前已使用：{used_mb:.1f} MB")
        usage.setObjectName("hinttext")
        store_lay.addWidget(usage)
        lay.addWidget(store_box)

        # 启动
        boot_box = QGroupBox("启动")
        boot_lay = QVBoxLayout(boot_box)
        self.autostart_check = QCheckBox("开机自动启动")
        self.autostart_check.setChecked(bool(storage.settings["autostart"]))
        boot_lay.addWidget(self.autostart_check)
        lay.addWidget(boot_box)

        interaction_box = QGroupBox("操作方式")
        interaction_lay = QVBoxLayout(interaction_box)
        self.quick_paste_check = QCheckBox("单击卡片直接粘贴")
        self.quick_paste_check.setChecked(bool(storage.settings.get("quick_paste", False)))
        interaction_lay.addWidget(self.quick_paste_check)
        interaction_note = QLabel("默认单击预览，双击或 Enter 粘贴；开启后单击直接返回原窗口粘贴。")
        interaction_note.setObjectName("hinttext")
        interaction_note.setWordWrap(True)
        interaction_lay.addWidget(interaction_note)
        lay.addWidget(interaction_box)

        lay.addStretch(1)

        btns = QHBoxLayout()
        btns.addStretch(1)
        cancel_btn = QPushButton("取消")
        cancel_btn.setObjectName("ghost")
        save_btn = QPushButton("保存")
        cancel_btn.clicked.connect(self.reject)
        save_btn.clicked.connect(self._save)
        btns.addWidget(cancel_btn)
        btns.addWidget(save_btn)
        lay.addLayout(btns)
        enable_dark_titlebar(int(self.winId()))

    def _save(self):
        self.storage.settings["retention_days"] = self.days_combo.currentData()
        self.storage.settings["size_limit_mb"] = self.limit_spin.value()
        self.storage.settings["autostart"] = self.autostart_check.isChecked()
        self.storage.settings["quick_paste"] = self.quick_paste_check.isChecked()
        self.storage.save_settings()
        if not set_autostart(self.storage.settings["autostart"]):
            QMessageBox.warning(self, "提示", "开机自启设置失败（可能没有注册表权限），其他设置已保存。")
        self.storage.cleanup()
        self.accept()
