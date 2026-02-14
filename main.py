#!/usr/bin/env python3
import logging
import os
import sys

import discord
from discord.ext import commands

DISCORD_TOKEN = os.environ.get('DISCORD_TOKEN')
DEV_GUILD_ID = os.environ.get('DEV_GUILD_ID')

# 開発モード: --dev または DEV_MODE=1 のときだけ、DEV_GUILD_ID にだけコマンドを同期（即時反映）。未指定時はグローバル同期（全ギルドに適用）。
def _is_dev_mode() -> bool:
    if '--dev' in sys.argv:
        return True
    return os.environ.get('DEV_MODE', '').lower() in ('1', 'true', 'yes')


class SuppressDiscordPlayerWriteError(logging.Filter):
    """FFmpeg 正常終了(return code 0)直後の discord.py のレースで出る Write error をログから落とす。"""
    def filter(self, record: logging.LogRecord) -> bool:
        if record.name != "discord.player":
            return True
        try:
            msg = record.getMessage()
        except Exception:
            msg = str(record.msg)
        if "Write error" not in msg:
            return True
        return False
COMMAND_PREFIX = '$'


class Bot(commands.Bot):
    def __init__(self, *, dev_mode: bool = False):
        self._dev_mode = dev_mode
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True  # リアクションしたユーザーの VC 取得（fetch_member）に必要
        super().__init__(command_prefix=COMMAND_PREFIX, intents=intents)

    async def setup_hook(self):
        await self.load_extension('voice')

        if self._dev_mode and DEV_GUILD_ID:
            guild = discord.Object(id=int(DEV_GUILD_ID))
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
            print(f"Synced commands to dev guild {DEV_GUILD_ID} (dev mode)")
        else:
            await self.tree.sync()
            print("Synced commands globally (all guilds)")
        print("Successfully synced commands")
        print(f"Logged onto {self.user}")

if __name__ == '__main__':
    # INFO を docker logs（stderr）に出す。指定しないとデフォルト WARNING で [op] が表示されない
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-8s %(name)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    # discord が自前ハンドラを持っていると同じログが2行出るので、root に集約する
    for _logger in ("discord", "discord.client", "discord.gateway", "discord.voice_state", "discord.player"):
        log = logging.getLogger(_logger)
        log.handlers.clear()
        log.propagate = True
    # 再生終了直後の discord.player "Write error" (dest=bool のレース) をログから除外
    for h in logging.root.handlers[:]:
        h.addFilter(SuppressDiscordPlayerWriteError())
    logging.getLogger("discord.player").addFilter(SuppressDiscordPlayerWriteError())

    bot = Bot(dev_mode=_is_dev_mode())
    bot.run(DISCORD_TOKEN)