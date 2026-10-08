# -*- coding: utf-8 -*-
"""生成 icon.png，打包 exe 时用作程序图标（运行一次即可）。"""
import sys

from PySide6.QtWidgets import QApplication

from theme import make_app_icon


def main():
    app = QApplication(sys.argv)
    pixmap = make_app_icon().pixmap(256, 256)
    if pixmap.save("icon.png", "PNG"):
        print("icon.png 已生成")
        return 0
    print("icon.png 生成失败")
    return 1


if __name__ == "__main__":
    sys.exit(main())
