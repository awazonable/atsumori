# coding: utf-8
"""絵文字チャット時のリアクションをチャンネル単位で ON/OFF する設定の永続化（SQLite）"""

import logging
import sqlite3
from pathlib import Path

logger = logging.getLogger(__name__)

# コンテナでも永続化できるようカレントディレクトリに配置（ボリュームマウントで保持可能）
DB_PATH = Path("reaction_settings.db")
_ALL_OFF = 0  # channel_id=0 の行 = その guild は「すべて OFF」


def _conn():
    return sqlite3.connect(DB_PATH)


def init():
    """テーブルが無ければ作成する。"""
    with _conn() as c:
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS reaction_channel (
                guild_id INTEGER NOT NULL,
                channel_id INTEGER NOT NULL,
                PRIMARY KEY (guild_id, channel_id)
            )
            """
        )
    logger.debug("reaction_db init done")


def is_reaction_enabled(guild_id: int, channel_id: int) -> bool:
    """
    その guild のそのチャンネルで「絵文字チャット→リアクション」が有効か。
    ・guild にレコードが無い → 全チャンネル ON（従来どおり）
    ・(guild_id, 0) が存在 → 全チャンネル OFF
    ・(guild_id, channel_id) が存在 → そのチャンネルのみ ON
    ・上以外で (guild_id, * ) が存在 → 指定チャンネルのみ ON モードなので、この ch は OFF
    """
    with _conn() as c:
        cur = c.execute(
            "SELECT 1 FROM reaction_channel WHERE guild_id = ? AND channel_id = ?",
            (guild_id, _ALL_OFF),
        )
        if cur.fetchone():
            return False
        cur = c.execute(
            "SELECT 1 FROM reaction_channel WHERE guild_id = ? AND channel_id = ?",
            (guild_id, channel_id),
        )
        if cur.fetchone():
            return True
        cur = c.execute(
            "SELECT 1 FROM reaction_channel WHERE guild_id = ? AND channel_id != ?",
            (guild_id, _ALL_OFF),
        )
        if cur.fetchone():
            return False
    return True


def set_all_off(guild_id: int) -> None:
    """その guild の全チャンネルでリアクション OFF。"""
    with _conn() as c:
        c.execute("DELETE FROM reaction_channel WHERE guild_id = ?", (guild_id,))
        c.execute(
            "INSERT OR REPLACE INTO reaction_channel (guild_id, channel_id) VALUES (?, ?)",
            (guild_id, _ALL_OFF),
        )
    logger.info("[reaction_db] set_all_off guild_id=%s", guild_id)


def set_all_on(guild_id: int) -> None:
    """その guild の全チャンネルでリアクション ON（設定を削除してデフォルトに戻す）。"""
    with _conn() as c:
        c.execute("DELETE FROM reaction_channel WHERE guild_id = ?", (guild_id,))
    logger.info("[reaction_db] set_all_on guild_id=%s", guild_id)


def set_channel_on(guild_id: int, channel_id: int) -> None:
    """その guild で指定チャンネルをリアクション ON に追加（全 OFF を解除）。複数回で複数チャンネル指定可能。"""
    with _conn() as c:
        c.execute("DELETE FROM reaction_channel WHERE guild_id = ? AND channel_id = ?", (guild_id, _ALL_OFF))
        c.execute(
            "INSERT OR REPLACE INTO reaction_channel (guild_id, channel_id) VALUES (?, ?)",
            (guild_id, channel_id),
        )
    logger.info("[reaction_db] set_channel_on guild_id=%s channel_id=%s", guild_id, channel_id)


def get_enabled_channels(guild_id: int) -> list[int] | None:
    """
    その guild で「ON のチャンネル一覧」を返す。
    全 ON のときは None、全 OFF のときは []、指定のみのときは channel_id のリスト。
    """
    with _conn() as c:
        cur = c.execute(
            "SELECT channel_id FROM reaction_channel WHERE guild_id = ? ORDER BY channel_id",
            (guild_id,),
        )
        rows = cur.fetchall()
    if not rows:
        return None
    if len(rows) == 1 and rows[0][0] == _ALL_OFF:
        return []
    return [r[0] for r in rows if r[0] != _ALL_OFF]
