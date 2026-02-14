# coding: utf-8
"""ユーザーアップロード音声の保存とリアクション紐付け（SQLite + ファイル）"""

import logging
import os
import re
import sqlite3
import time
from pathlib import Path

logger = logging.getLogger(__name__)

# 永続化用の親ディレクトリ（Docker では /app/data をボリュームマウントして使用）
_STORE_BASE = Path(os.environ.get("UPLOAD_STORE_DIR", "."))
UPLOAD_DIR = _STORE_BASE / "uploads"
DB_PATH = _STORE_BASE / "uploads.db"
NAME_MAX_LEN = 64
ALLOWED_EXT = frozenset({"mp3", "wav"})


def _conn():
    return sqlite3.connect(DB_PATH)


def _sanitize_name(name: str) -> str:
    """ファイル名に使えるようにサニタイズ（英数字・アンダースコア・ハイフンのみ）。"""
    s = re.sub(r"[^a-zA-Z0-9_-]", "_", name)
    return s[:NAME_MAX_LEN] if s else "unnamed"


def init():
    """テーブルが無ければ作成する。"""
    UPLOAD_DIR.mkdir(exist_ok=True)
    with _conn() as c:
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS uploads (
                guild_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                file_path TEXT NOT NULL,
                PRIMARY KEY (guild_id, name)
            )
            """
        )
        for col in ("uploaded_by", "uploaded_at"):
            try:
                c.execute(f"ALTER TABLE uploads ADD COLUMN {col} INTEGER")
            except sqlite3.OperationalError as e:
                if "duplicate column" not in str(e).lower():
                    raise
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS reaction_upload (
                guild_id INTEGER NOT NULL,
                reaction_key TEXT NOT NULL,
                upload_name TEXT NOT NULL,
                PRIMARY KEY (guild_id, reaction_key),
                FOREIGN KEY (guild_id, upload_name) REFERENCES uploads (guild_id, name)
            )
            """
        )
    logger.debug("upload_store init done")


def _guild_dir(guild_id: int) -> Path:
    d = UPLOAD_DIR / str(guild_id)
    d.mkdir(parents=True, exist_ok=True)
    return d


def save_upload(
    guild_id: int,
    name: str,
    content: bytes,
    ext: str,
    uploaded_by: int | None = None,
) -> str:
    """
    アップロードを保存する。name はサニタイズされる。
    ext は mp3 または wav。uploaded_by は Discord の user_id。返り値はサニタイズ後の name。
    """
    ext = ext.lower()
    if ext not in ALLOWED_EXT:
        raise ValueError(f"拡張子は {ALLOWED_EXT} のいずれかにしてください")
    safe_name = _sanitize_name(name)
    if not safe_name:
        raise ValueError("名前が空になりました")
    path = _guild_dir(guild_id) / f"{safe_name}.{ext}"
    path.write_bytes(content)
    uploaded_at = int(time.time())
    with _conn() as c:
        c.execute(
            "INSERT OR REPLACE INTO uploads (guild_id, name, file_path, uploaded_by, uploaded_at) VALUES (?, ?, ?, ?, ?)",
            (guild_id, safe_name, str(path), uploaded_by, uploaded_at),
        )
    logger.info("[upload_store] save guild_id=%s name=%s path=%s by=%s", guild_id, safe_name, path, uploaded_by)
    return safe_name


def get_upload_path(guild_id: int, name: str) -> Path | None:
    """登録済みのアップロードの絶対パス。無ければ None。"""
    with _conn() as c:
        cur = c.execute(
            "SELECT file_path FROM uploads WHERE guild_id = ? AND name = ?",
            (guild_id, name),
        )
        row = cur.fetchone()
    if not row:
        return None
    p = Path(row[0])
    return p if p.is_absolute() else Path.cwd() / p


def list_uploads(guild_id: int) -> list[str]:
    """その guild のアップロード名一覧（昇順）。"""
    with _conn() as c:
        cur = c.execute(
            "SELECT name FROM uploads WHERE guild_id = ? ORDER BY name",
            (guild_id,),
        )
        return [r[0] for r in cur.fetchall()]


def list_uploads_with_meta(guild_id: int) -> list[tuple[str, int | None, int | None]]:
    """その guild のアップロード一覧（name, uploaded_by user_id, uploaded_at unix ts）。昇順。"""
    with _conn() as c:
        cur = c.execute(
            "SELECT name, uploaded_by, uploaded_at FROM uploads WHERE guild_id = ? ORDER BY name",
            (guild_id,),
        )
        return [(r[0], r[1], r[2]) for r in cur.fetchall()]


def set_reaction_upload(guild_id: int, reaction_key: str, upload_name: str) -> None:
    """リアクション reaction_key で upload_name を再生するように設定。"""
    with _conn() as c:
        c.execute(
            "INSERT OR REPLACE INTO reaction_upload (guild_id, reaction_key, upload_name) VALUES (?, ?, ?)",
            (guild_id, reaction_key, upload_name),
        )
    logger.info("[upload_store] set_reaction guild_id=%s reaction_key=%s upload_name=%s", guild_id, reaction_key, upload_name)


def get_reaction_upload(guild_id: int, reaction_key: str) -> str | None:
    """その guild で reaction_key に紐付いたアップロード名。無ければ None。"""
    with _conn() as c:
        cur = c.execute(
            "SELECT upload_name FROM reaction_upload WHERE guild_id = ? AND reaction_key = ?",
            (guild_id, reaction_key),
        )
        row = cur.fetchone()
    return row[0] if row else None


def list_reaction_keys_for_upload(guild_id: int, upload_name: str) -> list[str]:
    """その guild で upload_name に紐付いている reaction_key の一覧（投稿時にリアクションを付けるため）。"""
    with _conn() as c:
        cur = c.execute(
            "SELECT reaction_key FROM reaction_upload WHERE guild_id = ? AND upload_name = ?",
            (guild_id, upload_name),
        )
        return [r[0] for r in cur.fetchall()]


def list_all_reaction_uploads(guild_id: int) -> list[tuple[str, str]]:
    """その guild の「リアクション → アップロード」紐付け一覧。(reaction_key, upload_name) の昇順。"""
    with _conn() as c:
        cur = c.execute(
            "SELECT reaction_key, upload_name FROM reaction_upload WHERE guild_id = ? ORDER BY reaction_key, upload_name",
            (guild_id,),
        )
        return list(cur.fetchall())


def delete_upload(guild_id: int, name: str) -> bool:
    """
    アップロードを削除する。ファイル削除・reaction_upload の該当行削除・uploads の行削除。
    存在しない name の場合は ValueError。返り値は True。
    """
    path = get_upload_path(guild_id, name)
    if not path:
        raise ValueError(f"`{name}` というアップロードは見つかりません。")
    with _conn() as c:
        c.execute(
            "DELETE FROM reaction_upload WHERE guild_id = ? AND upload_name = ?",
            (guild_id, name),
        )
        c.execute("DELETE FROM uploads WHERE guild_id = ? AND name = ?", (guild_id, name))
    try:
        path.unlink(missing_ok=True)
    except OSError as e:
        logger.warning("[upload_store] delete: could not unlink %s: %s", path, e)
    logger.info("[upload_store] delete guild_id=%s name=%s", guild_id, name)
    return True
