# -*- coding: utf-8 -*-
"""数据存储：SQLite 记录历史，图片以文件形式保存，负责过期与容量自动清理。"""
import hashlib
import json
import os
import sqlite3
import sys
import time
from pathlib import Path

from PySide6.QtCore import Qt

DEFAULT_SETTINGS = {
    "retention_days": 365,   # 历史保留天数
    "size_limit_mb": 800,    # 存储上限（MB）
    "autostart": True,       # 开机自启
    "hint_dismissed": False, # 新手提示是否已关闭
    "quick_paste": False,    # 单击直接粘贴；默认先预览，避免误操作
}

MAX_TEXT_LEN = 100_000       # 单条文字最多保存的字符数
THUMB_WIDTH = 360            # 图片缩略图最大宽度


def app_dir() -> Path:
    """程序所在目录：exe 所在目录（打包后）或项目目录（源码运行）。"""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).parent


class Storage:
    def __init__(self, base_dir=None):
        self.base = Path(base_dir) if base_dir else app_dir() / "data"
        self.img_dir = self.base / "images"
        self.thumb_dir = self.base / "thumbs"
        for d in (self.img_dir, self.thumb_dir):
            d.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.base / "history.db"))
        self._conn.row_factory = sqlite3.Row
        self._init_db()
        self.settings = self._load_settings()

    def _init_db(self):
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                type TEXT NOT NULL,
                content TEXT,
                image_path TEXT,
                thumb_path TEXT,
                size INTEGER DEFAULT 0,
                hash TEXT,
                pinned INTEGER DEFAULT 0,
                created_at REAL
            )
            """
        )
        self._conn.commit()

    # ---------- 设置 ----------
    def _load_settings(self):
        path = self.base / "settings.json"
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                return {**DEFAULT_SETTINGS, **data}
            except Exception:
                pass
        return dict(DEFAULT_SETTINGS)

    def save_settings(self):
        (self.base / "settings.json").write_text(
            json.dumps(self.settings, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    # ---------- 记录 ----------
    def add_text(self, text):
        """保存一条文字。返回 (id, 是否新记录)；相同内容重复复制会更新原记录时间。"""
        content = text[:MAX_TEXT_LEN]
        if not content.strip():
            return None
        latest = self.get_latest()
        if latest and latest["type"] == "text" and latest["content"] == content:
            self._touch(latest["id"])
            return (latest["id"], False)
        cur = self._conn.execute(
            "INSERT INTO records (type, content, size, pinned, created_at) VALUES (?,?,?,0,?)",
            ("text", content, len(content.encode("utf-8")), time.time()),
        )
        self._conn.commit()
        return (cur.lastrowid, True)

    def add_image(self, png_bytes, qimage):
        """保存一张图片。返回 (id, 是否新记录)。"""
        digest = hashlib.md5(png_bytes).hexdigest()
        latest = self.get_latest()
        if latest and latest["type"] == "image" and latest["hash"] == digest:
            self._touch(latest["id"])
            return (latest["id"], False)
        rid = self._conn.execute(
            "INSERT INTO records (type, image_path, thumb_path, size, hash, pinned, created_at) "
            "VALUES ('image','','',?,?,0,?)",
            (len(png_bytes), digest, time.time()),
        ).lastrowid
        img_path = self.img_dir / f"{rid}.png"
        thumb_path = self.thumb_dir / f"{rid}.png"
        img_path.write_bytes(png_bytes)
        thumb = (
            qimage.scaledToWidth(THUMB_WIDTH, Qt.SmoothTransformation)
            if qimage.width() > THUMB_WIDTH
            else qimage
        )
        thumb.save(str(thumb_path), "PNG")
        self._conn.execute(
            "UPDATE records SET image_path=?, thumb_path=? WHERE id=?",
            (str(img_path), str(thumb_path), rid),
        )
        self._conn.commit()
        return (rid, True)

    def _touch(self, record_id):
        self._conn.execute("UPDATE records SET created_at=? WHERE id=?", (time.time(), record_id))
        self._conn.commit()

    def get(self, record_id):
        return self._conn.execute("SELECT * FROM records WHERE id=?", (record_id,)).fetchone()

    def get_latest(self):
        return self._conn.execute("SELECT * FROM records ORDER BY id DESC LIMIT 1").fetchone()

    def count(self, search="", type_filter=None, pinned_only=False):
        sql, params = self._build_where(search, type_filter, prefix="SELECT COUNT(*) AS n", pinned_only=pinned_only)
        return self._conn.execute(sql, params).fetchone()["n"]

    def query(self, offset=0, limit=100, search="", type_filter=None, pinned_only=False):
        sql, params = self._build_where(search, type_filter, prefix="SELECT *", pinned_only=pinned_only)
        sql += " ORDER BY pinned DESC, created_at DESC LIMIT ? OFFSET ?"
        return self._conn.execute(sql, params + [limit, offset]).fetchall()

    def _build_where(self, search, type_filter, prefix, pinned_only=False):
        sql, conds, params = prefix + " FROM records", [], []
        if search:
            conds.append("type='text'")
            conds.append("content LIKE ? ESCAPE '\\'")
            literal = search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            params.append(f"%{literal}%")
        if type_filter:
            conds.append("type=?")
            params.append(type_filter)
        if pinned_only:
            conds.append("pinned=1")
        if conds:
            sql += " WHERE " + " AND ".join(conds)
        return sql, params

    # ---------- 管理 ----------
    def toggle_pin(self, record_id):
        row = self.get(record_id)
        if not row:
            return None
        new_value = 0 if row["pinned"] else 1
        self._conn.execute("UPDATE records SET pinned=? WHERE id=?", (new_value, record_id))
        self._conn.commit()
        return new_value

    def delete(self, record_id):
        row = self.get(record_id)
        if row:
            self._delete_files(row)
            self._conn.execute("DELETE FROM records WHERE id=?", (record_id,))
            self._conn.commit()

    def delete_many(self, ids):
        """批量删除多条记录（单事务，含图片文件清理）。"""
        ids = list(ids)
        if not ids:
            return
        marks = ",".join("?" * len(ids))
        rows = self._conn.execute(
            f"SELECT * FROM records WHERE id IN ({marks})", ids
        ).fetchall()
        for row in rows:
            self._delete_files(row)
        self._conn.execute(f"DELETE FROM records WHERE id IN ({marks})", ids)
        self._conn.commit()

    def clear_all(self):
        self._conn.execute("DELETE FROM records")
        self._conn.commit()
        for d in (self.img_dir, self.thumb_dir):
            for f in d.glob("*"):
                try:
                    f.unlink()
                except OSError:
                    pass

    def total_size(self):
        return self._conn.execute(
            "SELECT COALESCE(SUM(size), 0) AS s FROM records"
        ).fetchone()["s"]

    def cleanup(self):
        """自动清理：删除过期内容（置顶除外），并保证总量不超过存储上限。"""
        cutoff = time.time() - self.settings["retention_days"] * 86400
        old_rows = self._conn.execute(
            "SELECT * FROM records WHERE pinned=0 AND created_at < ?", (cutoff,)
        ).fetchall()
        for row in old_rows:
            self._delete_files(row)
        self._conn.execute("DELETE FROM records WHERE pinned=0 AND created_at < ?", (cutoff,))

        cap = self.settings["size_limit_mb"] * 1024 * 1024
        total = self.total_size()
        while total > cap:
            row = self._conn.execute(
                "SELECT * FROM records WHERE pinned=0 ORDER BY created_at ASC LIMIT 1"
            ).fetchone()
            if not row:
                break
            total -= row["size"] or 0
            self._delete_files(row)
            self._conn.execute("DELETE FROM records WHERE id=?", (row["id"],))
        self._conn.commit()

    def _delete_files(self, row):
        for path in (row["image_path"], row["thumb_path"]):
            if path and os.path.exists(path):
                try:
                    os.remove(path)
                except OSError:
                    pass
