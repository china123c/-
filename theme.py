# -*- coding: utf-8 -*-
"""深色光感主题与统一的运行时绘制图标。"""
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QColor, QIcon, QLinearGradient, QPainter, QPalette, QPen, QPixmap, QPolygonF,
)

DARK_QSS = """
* { font-family: "Microsoft YaHei UI", "Microsoft YaHei", sans-serif; font-size: 13px; color: #D4DDF0; }
QWidget { background: transparent; }
QMainWindow, QDialog { background: #101620; }
QWidget#appsurface { background: #101620; }
QLabel#title { font-size: 21px; font-weight: bold; color: #F0F4FF; }
QLabel#subtitle, QLabel#hinttext { color: #788AA7; font-size: 12px; }
QLabel#time { color: #7487A5; font-size: 11px; }
QLabel#detailtitle { font-size: 15px; font-weight: bold; color: #E1E8FB; }
QLabel#cardtext { color: #C8D3EB; font-size: 13px; }
QLabel#typebadge { color: #8E9FBE; font-size: 11px; background: #243045; border-radius: 4px; padding: 2px 6px; }
QLabel#pin { color: #DDBB7A; font-size: 11px; }
QLabel#selbadge { color: white; background: #6882DE; border-radius: 10px; }
QLabel#empty { color: #8091AE; font-size: 13px; padding: 18px; }
QLabel#previewhint { color: #617491; font-size: 13px; }
QLabel#feedback { color: #9FB7FF; font-size: 12px; }
QLineEdit { background: #141D2C; color: #DFE7F8; border: 1px solid #2A374E; border-radius: 10px; padding: 8px 12px; selection-background-color: #5C74C5; }
QLineEdit:focus { background: #182335; border-color: #647DB5; }
QPushButton { background: #5771CA; color: #F5F7FF; border: 1px solid transparent; border-radius: 7px; padding: 7px 12px; font-weight: normal; }
QPushButton:hover { background: #6781DC; }
QPushButton:pressed { background: #4760B5; }
QPushButton:disabled { color: #52637D; background: #1A2434; }
QPushButton:focus { border: 1px solid #768BC1; }
QPushButton#primary { padding: 10px 14px; font-weight: bold; background: qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #829CF2,stop:0.4 #6884DF,stop:1 #526BC3); border: 1px solid #8BA0DB; }
QPushButton#primary:hover { background: qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #97AEFA,stop:1 #6682DC); }
QPushButton#primary:pressed { background: #4C65B8; }
QPushButton#primary:disabled { background: #202B40; border-color: #2C3950; color: #64758D; }
QPushButton#glass { background: qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #273852,stop:1 #1B283E); color: #BACDFB; border: 1px solid #41577B; padding: 9px; }
QPushButton#glass:hover { background: #2D4060; border-color: #6686BE; }
QPushButton#ghost { color: #A9B9D5; background: #1A2435; border: 1px solid #2E3D56; }
QPushButton#ghost:hover { color: #D6E4FF; background: #263551; border-color: #4C638A; }
QPushButton#ghost:checked { color: #CFDEFF; background: #2A3A60; border-color: #556EA2; }
QPushButton#ghost:disabled { color: #52637D; border-color: #273348; background: #192233; }
QPushButton#seg { background: transparent; color: #8B9CBB; padding: 7px 14px; }
QPushButton#seg:hover { background: #22324B; color: #BCD0FF; }
QPushButton#seg:checked { background: #283A5B; color: #BCD0FF; font-weight: bold; }
QPushButton#recording { background: #19372F; color: #8CC7AF; border-color: #2B5547; padding: 6px 12px; font-size: 12px; }
QPushButton#recording:hover { background: #22493B; }
QPushButton#recording[paused="true"] { background: #3B3020; color: #D6B47A; border-color: #594832; }
QPushButton#danger { color: #E9A2A7; background: #2C222D; border-color: #573A48; }
QPushButton#danger:hover { background: #432C38; border-color: #81515E; }
QPushButton#danger:disabled { color: #705561; border-color: #392B35; background: #25202A; }
QPushButton::menu-indicator { image: none; width: 0; }
QFrame#card { background: qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #1A2639,stop:1 #151E2C); border: 1px solid #2C3A52; border-radius: 10px; }
QFrame#card:hover { background: #1D2C43; border-color: #526B95; }
QFrame#card[selected="true"] { background: qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #2A3D5F,stop:1 #202F4D); border: 1px solid #6382B9; }
QFrame#detail { background: qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #1A273C,stop:1 #131D2D); border: 1px solid #354761; border-radius: 12px; }
QFrame#batchbar { background: #1F2D48; border: 1px solid #3C5076; border-radius: 9px; }
QTextEdit#textpreview { background: transparent; color: #CBD7ED; font-size: 14px; selection-background-color: #5C74C5; selection-color: white; padding: 2px; }
QScrollArea, QStackedWidget { border: none; }
QSplitter::handle { background: transparent; width: 16px; }
QSplitter::handle:hover { background: #263752; border-radius: 4px; }
QScrollBar:vertical { background: transparent; width: 7px; margin: 2px 0; }
QScrollBar::handle:vertical { background: #354865; border-radius: 3px; min-height: 32px; }
QScrollBar::handle:vertical:hover { background: #536C96; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
QScrollBar:horizontal { background: transparent; height: 7px; }
QScrollBar::handle:horizontal { background: #354865; border-radius: 3px; min-width: 32px; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal { background: transparent; }
QRubberBand { background: rgba(132,169,255,45); border: 1px solid #94B4EE; }
QMenu { background: #192438; color: #CEDAF0; border: 1px solid #3B4D6B; border-radius: 8px; padding: 5px; }
QMenu::item { padding: 8px 24px 8px 12px; border-radius: 5px; }
QMenu::item:selected { background: #2C4063; color: #E1EAFF; }
QMenu::separator { height: 1px; background: #31415C; margin: 5px; }
QGroupBox { background: #172131; border: 1px solid #2D3C54; border-radius: 10px; margin-top: 16px; padding: 18px 14px 14px; }
QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 5px; color: #9BB3E2; }
QComboBox, QSpinBox { background: #121C2B; color: #D2DDF0; border: 1px solid #34445E; border-radius: 6px; padding: 7px 10px; min-height: 18px; }
QComboBox QAbstractItemView { background: #1B283D; color: #D2DDF0; selection-background-color: #31476D; selection-color: #EFF4FF; }
QComboBox::drop-down { border: none; width: 24px; }
QCheckBox { spacing: 9px; }
QCheckBox::indicator { width: 18px; height: 18px; background: #131E2D; border: 1px solid #415575; border-radius: 4px; }
QCheckBox::indicator:checked { background: #6882DE; border-color: #8EA6E9; image: url(__CHECK_ICON__); }
QToolTip { color: #D8E3FA; background: #1C2A40; border: 1px solid #465C80; padding: 6px 10px; }
QMessageBox QPushButton { min-width: 72px; }
"""


def _draw_check_png(path):
    """绘制白色对勾，供样式表中的复选框指示器使用。"""
    pm = QPixmap(16, 16)
    pm.fill(Qt.transparent)
    painter = QPainter(pm)
    painter.setRenderHint(QPainter.Antialiasing, True)
    pen = QPen(QColor("#FFFFFF"))
    pen.setWidthF(2.6)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    painter.setPen(pen)
    painter.drawPolyline(QPolygonF([QPointF(3.5, 8.5), QPointF(6.8, 11.8), QPointF(12.8, 4.6)]))
    painter.end()
    pm.save(str(path), "PNG")


def themed_qss():
    """返回填充了运行时绘制资源路径的完整样式表。"""
    from storage import app_dir  # 延迟导入，避免打包路径问题
    check_path = Path(app_dir()) / "data" / "check.png"
    check_path.parent.mkdir(parents=True, exist_ok=True)
    if not check_path.exists():
        _draw_check_png(check_path)
    return DARK_QSS.replace("__CHECK_ICON__", check_path.as_posix())


def apply_theme(app):
    """同时设置原生控件调色板和样式表，避免深色界面出现浅色弹窗。"""
    app.setStyle("Fusion")
    palette = QPalette()
    for role, color in [
        (QPalette.Window, "#101620"), (QPalette.WindowText, "#D4DDF0"),
        (QPalette.Base, "#141D2C"), (QPalette.AlternateBase, "#1A2639"),
        (QPalette.Text, "#D4DDF0"), (QPalette.Button, "#1A2435"),
        (QPalette.ButtonText, "#D4DDF0"), (QPalette.PlaceholderText, "#687C9E"),
        (QPalette.Highlight, "#5C74C5"), (QPalette.HighlightedText, "#FFFFFF"),
        (QPalette.Light, "#425577"), (QPalette.Dark, "#0B111B"),
        (QPalette.Mid, "#2A3952"), (QPalette.ToolTipBase, "#1C2A40"),
        (QPalette.ToolTipText, "#D8E3FA"),
    ]:
        palette.setColor(role, QColor(color))
    for role in (QPalette.Text, QPalette.WindowText, QPalette.ButtonText):
        palette.setColor(QPalette.Disabled, role, QColor("#60728F"))
    app.setPalette(palette)
    app.setStyleSheet(themed_qss())


def make_search_icon():
    """绘制放大镜图标，用于搜索输入框。"""
    pm = QPixmap(40, 40)
    pm.fill(Qt.transparent)
    painter = QPainter(pm)
    painter.setRenderHint(QPainter.Antialiasing, True)
    pen = QPen(QColor("#8CA3B8"))
    pen.setWidthF(3.5)
    pen.setCapStyle(Qt.RoundCap)
    painter.setPen(pen)
    painter.drawEllipse(QRectF(12, 12, 13, 13))
    painter.drawLine(QPointF(23.5, 23.5), QPointF(29, 29))
    painter.end()
    return QIcon(pm)


def make_app_icon():
    """用代码绘制淡蓝色剪贴板图标，返回多尺寸 QIcon。"""
    base = QPixmap(256, 256)
    base.fill(Qt.transparent)
    painter = QPainter(base)
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.setPen(Qt.NoPen)
    gradient = QLinearGradient(0, 0, 0, 256)
    gradient.setColorAt(0, QColor("#7D91EC"))
    gradient.setColorAt(1, QColor("#536ED8"))
    painter.setBrush(gradient)
    painter.drawRoundedRect(QRectF(30, 54, 196, 164), 26, 26)
    painter.drawRoundedRect(QRectF(92, 30, 72, 40), 18, 18)
    pen = QPen(QColor("#FFFFFF"))
    pen.setWidth(13)
    pen.setCapStyle(Qt.RoundCap)
    painter.setPen(pen)
    for y in (112, 150, 188):
        painter.drawLine(68, y, 188, y)
    painter.end()

    icon = QIcon()
    for size in (16, 24, 32, 48, 64, 128, 256):
        icon.addPixmap(base.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation))
    return icon


def make_ui_icon(kind):
    """绘制统一的线条图标，避免依赖字体符号。"""
    pm = QPixmap(40, 40)
    pm.fill(Qt.transparent)
    painter = QPainter(pm)
    painter.setRenderHint(QPainter.Antialiasing)
    pen = QPen(QColor("#FFFFFF" if kind == "check" else "#A7BADD"), 2.6)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.NoBrush)
    if kind == "check":
        painter.drawPolyline(QPolygonF([QPointF(10, 20), QPointF(17, 27), QPointF(30, 12)]))
    elif kind == "copy":
        painter.drawRoundedRect(QRectF(14, 14, 17, 20), 3, 3)
        painter.drawLine(9, 26, 9, 9)
        painter.drawLine(9, 9, 24, 9)
    elif kind == "pin":
        painter.drawPolygon(QPolygonF([QPointF(14, 8), QPointF(27, 8),
            QPointF(25, 20), QPointF(30, 25), QPointF(11, 25), QPointF(16, 20)]))
        painter.drawLine(20, 25, 20, 34)
    elif kind == "screen":
        painter.drawRoundedRect(QRectF(6, 7, 28, 21), 3, 3)
        painter.drawLine(20, 28, 20, 34)
        painter.drawLine(13, 34, 27, 34)
    elif kind == "close":
        painter.drawLine(12, 12, 28, 28)
        painter.drawLine(28, 12, 12, 28)
    elif kind in ("minus", "plus"):
        painter.drawLine(10, 20, 30, 20)
        if kind == "plus":
            painter.drawLine(20, 10, 20, 30)
    else:
        painter.drawEllipse(QRectF(8, 8, 24, 24))
        painter.drawEllipse(QRectF(15, 15, 10, 10))
        for start, end in [((20, 4), (20, 8)), ((20, 32), (20, 36)),
                           ((4, 20), (8, 20)), ((32, 20), (36, 20))]:
            painter.drawLine(*start, *end)
    painter.end()
    return QIcon(pm)
