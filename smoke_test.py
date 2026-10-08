# -*- coding: utf-8 -*-
"""开发自测脚本（无界面运行），验证存储与清理逻辑。"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import shutil
import tempfile
import time
from pathlib import Path

from PySide6.QtCore import QBuffer, QIODevice
from PySide6.QtGui import QColor, QGuiApplication, QImage

from storage import Storage

app = QGuiApplication(sys.argv)  # noqa: F841


def main():
    base = Path(tempfile.mkdtemp(prefix="clip_test_"))
    s = Storage(base_dir=base)

    # 文字：新增 + 去重
    rid, created = s.add_text("hello 世界")
    assert created is True
    rid2, created2 = s.add_text("hello 世界")
    assert created2 is False and rid2 == rid

    # 图片
    img = QImage(400, 300, QImage.Format_ARGB32)
    img.fill(QColor("#4A9FE8"))
    buf = QBuffer()
    buf.open(QIODevice.WriteOnly)
    img.save(buf, "PNG")
    rid3, created3 = s.add_image(bytes(buf.data()), img)
    assert created3 is True

    # 查询 / 搜索 / 筛选
    assert s.count() == 2
    assert len(s.query(0, 100)) == 2
    assert len(s.query(0, 100, search="hello")) == 1
    assert len(s.query(0, 100, type_filter="image")) == 1

    # 置顶排最前
    assert s.toggle_pin(rid3) == 1
    assert s.query(0, 100)[0]["id"] == rid3

    # 过期清理：普通内容删除，置顶保留
    s._conn.execute("UPDATE records SET created_at=? WHERE id=?", (time.time() - 400 * 86400, rid))
    s._conn.commit()
    s.cleanup()
    assert s.get(rid) is None
    assert s.get(rid3) is not None

    # 容量清理 + 删除
    s.settings["size_limit_mb"] = 1
    s.cleanup()
    s.delete(rid3)
    assert s.get(rid3) is None

    # 批量删除
    r1, _ = s.add_text("批量删除测试 A")
    r2, _ = s.add_text("批量删除测试 B")
    r3, _ = s.add_text("批量删除测试 C")
    s.delete_many([r1, r3])
    assert s.count() == 1
    assert s.get(r2)["content"] == "批量删除测试 B"

    s._conn.close()
    shutil.rmtree(base, ignore_errors=True)
    print("自测全部通过")


if __name__ == "__main__":
    main()
