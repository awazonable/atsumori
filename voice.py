# coding: utf-8
"""Voice Cog: 接続管理・再生キュー・絵文字→音声解決・イベントハンドリング（SPEC §9.3）"""

import asyncio
import json
import logging
import os
import random
import re
import time
from datetime import datetime, timezone

from emoji import demojize, emojize

import discord
from discord import app_commands
from discord.ext import commands

import reaction_db
import upload_store

CONFIG_PATH = "config.json"
SOUNDS_BASE_DEFAULT = "/app"  # Docker の WORKDIR 想定

logger = logging.getLogger(__name__)


def _load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


class Voice(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        config = _load_config()
        self._emoji_list = config.get("emoji_list", {})
        self._server_emoji_list = config.get("server_emoji_list", {})
        raw_base = config.get("sounds_base", os.environ.get("SOUNDS_BASE", SOUNDS_BASE_DEFAULT))
        self._sounds_base = os.path.abspath(raw_base) if raw_base in (".", "") else raw_base
        # 再生キューは guild 単位で管理（SPEC §5.1, §9.2）
        self._queue: dict[int, list[str]] = {}
        # 429 対策: message_id → (Message, 取得時刻). TTL 30s, 最大 100 件
        self._message_cache: dict[tuple[int, int], tuple[discord.Message, float]] = {}
        self._message_cache_ttl = 30.0
        self._message_cache_max = 100
        reaction_db.init()
        upload_store.init()

    def _resolve_path(self, path: str) -> str:
        if os.path.isabs(path):
            return path
        return os.path.join(self._sounds_base, path)

    # --- Voice 接続管理（SPEC §4） ---

    def get_guild_vc(self, guild: discord.Guild):
        """同一 guild 内で接続中の VC を 1 つ返す。なければ None。"""
        for vc in self.bot.voice_clients:
            if vc.guild and vc.guild.id == guild.id:
                return vc
        return None

    def get_vc(self, voice_channel: discord.VoiceChannel):
        for vc in self.bot.voice_clients:
            if vc.channel == voice_channel:
                return vc
        return None

    async def _connect(self, voice_channel: discord.VoiceChannel | None):
        if not voice_channel:
            return None
        vc = self.get_vc(voice_channel)
        if not vc:
            logger.info("[op] connect | begin guild_id=%s channel_id=%s", voice_channel.guild.id, voice_channel.id)
            vc = await voice_channel.connect(reconnect=False)
            self._queue[vc.guild.id] = []
            await asyncio.sleep(0.8)
            logger.info("[op] connect | done guild_id=%s channel_id=%s at=%.3f", vc.guild.id, vc.channel.id if vc.channel else None, time.monotonic())
        return vc

    def _clear_queue_for_guild(self, guild_id: int) -> None:
        if guild_id in self._queue:
            del self._queue[guild_id]

    # --- 再生キュー管理（SPEC §5.1） ---

    def _dequeue(self, guild_id: int) -> str | None:
        if guild_id not in self._queue or not self._queue[guild_id]:
            return None
        return self._queue[guild_id].pop(0)

    def _enqueue_and_play(self, vc: discord.VoiceClient, path: str) -> None:
        guild_id = vc.guild.id
        if guild_id not in self._queue:
            self._queue[guild_id] = []
        self._queue[guild_id].append(path)
        if not vc.is_playing():
            # 再生開始は handshake 直後より少し遅らせる（UDP/speaking/SSRC の安定待ち）
            self.bot.loop.create_task(self._delayed_play(vc))

    async def _delayed_play(self, vc: discord.VoiceClient) -> None:
        await asyncio.sleep(0.3)
        if vc.is_connected() and not vc.is_playing():
            self._vc_play(vc)

    def _vc_play(self, vc: discord.VoiceClient) -> None:
        if not vc.is_connected():
            logger.debug("[op] _vc_play skipped (not connected) guild_id=%s", vc.guild.id if vc.guild else None)
            return
        path = self._dequeue(vc.guild.id)
        if not path:
            return
        resolved = self._resolve_path(path)
        if not os.path.isfile(resolved):
            logger.warning("[op] play | file not found guild_id=%s path=%s", vc.guild.id, resolved)
            self._vc_play(vc)
            return

        logger.info("[op] play | guild_id=%s file=%s at=%.3f", vc.guild.id, os.path.basename(path), time.monotonic())

        def after(err):
            if err:
                logger.warning("[op] after | Playback error: %s | guild_id=%s", err, vc.guild.id)
                self._clear_queue_for_guild(vc.guild.id)
                return
            if vc.is_connected():
                self._vc_play(vc)
            else:
                logger.info("[op] after | skipped next (VC disconnected) guild_id=%s", vc.guild.id)

        source = discord.FFmpegPCMAudio(resolved, stderr=False)
        vc.play(source, after=after)

    # --- 絵文字 → 音声解決（SPEC §6, §7） ---

    def _pick_source_from_list(self, entries: list[dict]) -> str:
        if not entries:
            raise ValueError("entries empty")
        if len(entries) == 1:
            return entries[0]["source"]
        total = sum(e.get("freq", 100) for e in entries)
        r = random.randint(1, total)
        for e in entries:
            r -= e.get("freq", 100)
            if r <= 0:
                return e["source"]
        return entries[-1]["source"]

    def _atsumori_sequence(self) -> list[str]:
        """SPEC §7: 熱盛の連続再生用シーケンス（通常・ロング・特殊の確率バリエーション）"""
        base = self._sounds_base
        sounds_dir = os.path.join(base, "sounds")
        std = os.path.join(sounds_dir, "atsumori_std.wav")
        long_ = os.path.join(sounds_dir, "atsumori_long.wav")
        normal = os.path.join(sounds_dir, "apologize.wav")
        normal_p = os.path.join(sounds_dir, "apologize_1.wav")
        normal_s = os.path.join(sounds_dir, "apologize_3.wav")
        kudos = os.path.join(sounds_dir, "situreisimasita.wav")
        kudos_p = os.path.join(sounds_dir, "situreisimasita_1.wav")
        kudos_s = os.path.join(sounds_dir, "situreisimasita_3.wav")
        ussr = os.path.join(sounds_dir, "ussr.wav")

        ls = [std]
        if random.randint(1, 100) <= 20:
            ls = [long_]
        if random.randint(1, 100) <= 5:
            return [ussr]
        r = random.randint(1, 100)
        if r <= 10:
            ls = [kudos_p] + ls + [kudos_s]
        elif r <= 20:
            ls = [normal_p] + ls + [normal_s]
        elif r <= 60:
            ls.append(kudos)
        else:
            ls.append(normal)
        return ls

    def play_atsumori(self, vc: discord.VoiceClient) -> None:
        seq = self._atsumori_sequence()
        logger.info("[op] play_atsumori | guild_id=%s files=%s", vc.guild.id, [os.path.basename(p) for p in seq])
        for path in seq:
            self._enqueue_and_play(vc, path)

    def play_single(self, vc: discord.VoiceClient, path: str) -> None:
        self._enqueue_and_play(vc, self._resolve_path(path))

    # --- 429 対策: メッセージキャッシュ（fetch_message 回数削減） ---

    def _message_cache_cleanup(self) -> None:
        now = time.monotonic()
        expired = [k for k, (_, t) in self._message_cache.items() if now - t > self._message_cache_ttl]
        for k in expired:
            del self._message_cache[k]
        while len(self._message_cache) > self._message_cache_max:
            oldest = min(self._message_cache.items(), key=lambda x: x[1][1])
            del self._message_cache[oldest[0]]

    async def _get_message_cached(self, channel: discord.TextChannel, message_id: int) -> discord.Message | None:
        self._message_cache_cleanup()
        key = (channel.id, message_id)
        now = time.monotonic()
        if key in self._message_cache:
            msg, t = self._message_cache[key]
            if now - t <= self._message_cache_ttl:
                logger.debug("Message cache HIT channel_id=%s message_id=%s", channel.id, message_id)
                return msg
        try:
            msg = await channel.fetch_message(message_id)
            self._message_cache[key] = (msg, now)
            logger.debug("Message cache MISS (fetched) channel_id=%s message_id=%s", channel.id, message_id)
            return msg
        except Exception as e:
            logger.warning("fetch_message failed channel_id=%s message_id=%s: %s", channel.id, message_id, e)
            return None

    # --- Slash コマンド（SPEC §3.1） ---

    @app_commands.command(name="join", description="実行者が参加中のボイスチャンネルに BOT が参加する")
    async def slash_join(self, interaction: discord.Interaction):
        logger.info("[op] slash_join | begin user_id=%s guild_id=%s", interaction.user.id, interaction.guild_id)
        if not interaction.user.voice or not interaction.user.voice.channel:
            await interaction.response.send_message("ボイスチャンネルに参加してから実行してください。", ephemeral=True)
            return
        await interaction.response.send_message("接続しています…", ephemeral=True)
        vc = await self._connect(interaction.user.voice.channel)
        if vc:
            await interaction.edit_original_response(content=f"「{vc.channel.name}」に参加しました。")
            logger.info("[op] slash_join | done guild_id=%s channel_id=%s", vc.guild.id, vc.channel.id)
        else:
            await interaction.edit_original_response(content="参加できませんでした。")
            logger.warning("[op] slash_join | failed guild_id=%s", interaction.guild_id)

    @app_commands.command(name="leave", description="BOT が現在参加しているボイスチャンネルから退出する")
    async def slash_leave(self, interaction: discord.Interaction):
        logger.info("[op] slash_leave | begin user_id=%s guild_id=%s", interaction.user.id, interaction.guild_id)
        vc = self.get_guild_vc(interaction.guild)
        if not vc:
            await interaction.response.send_message("ボイスチャンネルに参加していません。", ephemeral=True)
            return
        await interaction.response.send_message("退出しています…", ephemeral=True)
        self._clear_queue_for_guild(vc.guild.id)
        await vc.disconnect()
        await interaction.edit_original_response(content="退出しました。")
        logger.info("[op] slash_leave | done guild_id=%s", interaction.guild_id)

    @app_commands.command(name="atsumori", description="熱盛の音声を再生する（参加中 or 自動参加後）")
    async def slash_atsumori(self, interaction: discord.Interaction):
        logger.info("[op] slash_atsumori | begin user_id=%s guild_id=%s", interaction.user.id, interaction.guild_id)
        vc = self.get_guild_vc(interaction.guild)
        if not vc and not (interaction.user.voice and interaction.user.voice.channel):
            await interaction.response.send_message(
                "ボイスチャンネルに参加してから `/join` するか、先に `/join` してから実行してください。",
                ephemeral=True,
            )
            return
        if not vc:
            await interaction.response.send_message("接続して熱盛！", ephemeral=True)
            vc = await self._connect(interaction.user.voice.channel)
            if not vc:
                await interaction.edit_original_response(
                    content="ボイスチャンネルに参加できませんでした。"
                )
                logger.warning("[op] slash_atsumori | connect failed guild_id=%s", interaction.guild_id)
                return
            logger.info("[op] slash_atsumori | play_atsumori (after connect) guild_id=%s", vc.guild.id)
            self.play_atsumori(vc)
            await interaction.edit_original_response(content="熱盛！")
        else:
            await interaction.response.send_message("熱盛！", ephemeral=True)
            logger.info("[op] slash_atsumori | play_atsumori (existing vc) guild_id=%s", vc.guild.id)
            self.play_atsumori(vc)

    @app_commands.command(name="help", description="コマンドの使い方を表示する（実行した本人にだけ表示）")
    async def slash_help(self, interaction: discord.Interaction):
        lines = [
            "**Slash コマンド一覧**",
            "",
            "`/join` — 実行者が参加中のボイスチャンネルに BOT が参加する",
            "`/leave` — BOT が参加中のボイスチャンネルから退出する",
            "`/atsumori` — 熱盛の音声を再生する（参加中 or 実行者の VC に自動参加して再生）",
            "`/show_all_emojis` — 反応する絵文字一覧をチャットに投稿する",
            "`/reaction_all_on` — 全チャンネルで絵文字→リアクションを ON にする",
            "`/reaction_all_off` — 全チャンネルで絵文字→リアクションを OFF にする",
            "`/reaction_channel` — 指定チャンネルでのみ絵文字→リアクションを ON（他は OFF）",
            "`/show_reaction_channels` — リアクション ON のチャンネル一覧を表示する",
            "`/upload_files` — 添付した音声（mp3/wav）を名前付きで保存する",
            "`/show_files` — このサーバーでアップロードした音声一覧を表示する",
            "`/set_reaction_files` — 指定したリアクションでアップロード音声を再生するように紐付ける",
            "`/delete_files` — アップロードした音声を削除する",
            "",
            "絵文字でリアクションすると対応する音声を VC で再生します。チャンネル単位で ON/OFF 可能。",
        ]
        text = "\n".join(lines)
        if len(text) > 2000:
            text = text[:1997] + "..."
        await interaction.response.send_message(text, ephemeral=True)

    def _format_reaction_key_display(self, reaction_key: str, guild: discord.Guild | None) -> str:
        """リアクションキーを一覧表示用に整形（絵文字 + `:key:` など）。"""
        if not reaction_key.isascii() and len(reaction_key) <= 2:
            return f"{reaction_key} `{reaction_key}`"
        try:
            char = emojize(f":{reaction_key}:", language="alias")
            if char and char != f":{reaction_key}:":
                return f"{char} `:{reaction_key}:`"
        except Exception:
            pass
        if guild:
            for em in guild.emojis:
                if em.name == reaction_key:
                    return f"{em} `:{reaction_key}:`"
        return f"`:{reaction_key}:`"

    @app_commands.command(name="show_all_emojis", description="反応する絵文字をすべてチャットに投稿する")
    async def slash_show_all_emojis(self, interaction: discord.Interaction):
        lines = ["**反応する絵文字一覧**", ""]
        # 熱盛（固定）
        lines.append("**熱盛**")
        lines.append("♨️ `♨` / サーバー絵文字 `atsumori`")
        lines.append("")
        # emoji_list（Unicode）
        lines.append("**Unicode（config: emoji_list）**")
        if not self._emoji_list:
            lines.append("（なし）")
        else:
            for key in sorted(self._emoji_list.keys()):
                try:
                    char = emojize(f":{key}:")
                except Exception:
                    char = "?"
                lines.append(f"{char} `:{key}:`")
        lines.append("")
        # server_emoji_list
        lines.append("**サーバー絵文字（config: server_emoji_list）**")
        if not self._server_emoji_list:
            lines.append("（なし）")
        else:
            for name in sorted(self._server_emoji_list.keys()):
                custom = None
                if interaction.guild:
                    custom = next((e for e in interaction.guild.emojis if e.name == name), None)
                if custom:
                    lines.append(f"{str(custom)} `:{name}:`")
                else:
                    lines.append(f"`:{name}:`（このサーバーに未登録）")
        lines.append("")
        lines.append("**アップロード音声（独自）**")
        if interaction.guild:
            custom_pairs = upload_store.list_all_reaction_uploads(interaction.guild_id)
            if not custom_pairs:
                lines.append("（なし）")
            else:
                for rk, upload_name in sorted(custom_pairs, key=lambda x: (x[0], x[1])):
                    disp = self._format_reaction_key_display(rk, interaction.guild)
                    lines.append(f"{disp} → `{upload_name}`")
        else:
            lines.append("（なし）")
        text = "\n".join(lines)
        if len(text) > 2000:
            text = text[:1997] + "..."
        await interaction.response.send_message(text)

    @app_commands.command(name="reaction_all_on", description="すべての見えるテキストチャンネルで絵文字→リアクションを ON にする")
    async def slash_reaction_all_on(self, interaction: discord.Interaction):
        if not interaction.guild:
            await interaction.response.send_message("サーバー内で実行してください。", ephemeral=True)
            return
        reaction_db.set_all_on(interaction.guild_id)
        await interaction.response.send_message("このサーバーの全チャンネルで絵文字リアクションを ON にしました。", ephemeral=True)

    @app_commands.command(name="reaction_all_off", description="すべてのチャンネルで絵文字→リアクションを OFF にする")
    async def slash_reaction_all_off(self, interaction: discord.Interaction):
        if not interaction.guild:
            await interaction.response.send_message("サーバー内で実行してください。", ephemeral=True)
            return
        reaction_db.set_all_off(interaction.guild_id)
        await interaction.response.send_message("このサーバーの全チャンネルで絵文字リアクションを OFF にしました。", ephemeral=True)

    @app_commands.command(name="reaction_channel", description="指定チャンネルでのみ絵文字→リアクションを ON にする（他は OFF）")
    @app_commands.describe(channel="リアクションを有効にするチャンネル（省略時はこのチャンネル）")
    async def slash_reaction_channel(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel | None = None,
    ):
        if not interaction.guild:
            await interaction.response.send_message("サーバー内で実行してください。", ephemeral=True)
            return
        ch = channel or interaction.channel
        if not isinstance(ch, discord.TextChannel):
            await interaction.response.send_message("テキストチャンネルを指定してください。", ephemeral=True)
            return
        reaction_db.set_channel_on(interaction.guild_id, ch.id)
        await interaction.response.send_message(f"「#{ch.name}」で絵文字リアクションを ON にしました。（他チャンネルは OFF）", ephemeral=True)

    @app_commands.command(name="show_reaction_channels", description="リアクション ON のチャンネル一覧を表示する")
    async def slash_show_reaction_channels(self, interaction: discord.Interaction):
        if not interaction.guild:
            await interaction.response.send_message("サーバー内で実行してください。", ephemeral=True)
            return
        channels = reaction_db.get_enabled_channels(interaction.guild_id)
        if channels is None:
            await interaction.response.send_message("**リアクション ON のチャンネル**\n全チャンネルで ON です。", ephemeral=True)
            return
        if not channels:
            await interaction.response.send_message("**リアクション ON のチャンネル**\n全チャンネルで OFF です。", ephemeral=True)
            return
        lines = ["**リアクション ON のチャンネル**", ""]
        for cid in channels:
            ch = interaction.guild.get_channel(cid)
            name = f"#{ch.name}" if ch else f"（ID: {cid}）"
            lines.append(f"・{name}")
        await interaction.response.send_message("\n".join(lines), ephemeral=True)

    # --- ユーザーアップロード音声（実験） ---

    @app_commands.command(name="upload_files", description="添付した音声ファイルを name で保存する（mp3/wav）")
    @app_commands.describe(name="保存する名前（英数字・アンダースコア推奨）")
    async def slash_upload(
        self,
        interaction: discord.Interaction,
        name: str,
        file: discord.Attachment,
    ):
        if not interaction.guild:
            await interaction.response.send_message("サーバー内で実行してください。", ephemeral=True)
            return
        ext = (file.filename or "").split(".")[-1].lower()
        if ext not in upload_store.ALLOWED_EXT:
            await interaction.response.send_message(
                f"音声ファイル（.mp3 または .wav）を添付してください。現在: {file.filename or 'なし'}",
                ephemeral=True,
            )
            return
        await interaction.response.defer(ephemeral=True)
        try:
            content = await file.read()
        except Exception as e:
            await interaction.followup.send(f"ファイルの取得に失敗しました: {e}", ephemeral=True)
            return
        try:
            safe_name = upload_store.save_upload(
                interaction.guild_id, name, content, ext, uploaded_by=interaction.user.id
            )
            await interaction.followup.send(f"音声を `{safe_name}` として保存しました。", ephemeral=True)
        except ValueError as e:
            await interaction.followup.send(str(e), ephemeral=True)

    async def _upload_name_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> list[app_commands.Choice[str]]:
        if not interaction.guild_id:
            return []
        names = upload_store.list_uploads(interaction.guild_id)
        if not current:
            return [app_commands.Choice(name=n, value=n) for n in names[:25]]
        cur = current.lower()
        return [app_commands.Choice(name=n, value=n) for n in names if cur in n.lower()][:25]

    @app_commands.command(name="set_reaction_files", description="指定したリアクションでアップロード音声を再生する")
    @app_commands.describe(
        name="アップロードした音声の名前",
        reaction="リアクション（絵文字または :name: 形式）",
    )
    @app_commands.autocomplete(name=_upload_name_autocomplete)
    async def slash_set_reaction(
        self,
        interaction: discord.Interaction,
        name: str,
        reaction: str,
    ):
        if not interaction.guild:
            await interaction.response.send_message("サーバー内で実行してください。", ephemeral=True)
            return
        path = upload_store.get_upload_path(interaction.guild_id, name)
        if not path or not path.is_file():
            await interaction.response.send_message(f"`{name}` という音声が見つかりません。`/show_files` で一覧を確認してください。", ephemeral=True)
            return
        reaction_key = reaction.strip()
        if reaction_key.startswith(":") and reaction_key.endswith(":"):
            reaction_key = reaction_key[1:-1]
        if not reaction_key:
            await interaction.response.send_message("リアクションを指定してください（絵文字または :name:）。", ephemeral=True)
            return
        if len(reaction_key) > 1 and not reaction_key.isascii():
            reaction_key = demojize(reaction_key, delimiters=("", "")).strip(":")
        upload_store.set_reaction_upload(interaction.guild_id, reaction_key, name)
        await interaction.response.send_message(f"リアクション `{reaction_key}` で `{name}` が再生されるように設定しました。", ephemeral=True)

    @app_commands.command(name="show_files", description="このサーバーでアップロードした音声一覧を表示する")
    async def slash_show_files(self, interaction: discord.Interaction):
        if not interaction.guild:
            await interaction.response.send_message("サーバー内で実行してください。", ephemeral=True)
            return
        rows = upload_store.list_uploads_with_meta(interaction.guild_id)
        if not rows:
            await interaction.response.send_message("アップロードされた音声はありません。`/upload_files` で追加できます。", ephemeral=True)
            return
        lines = ["**アップロード音声一覧**"]
        for name, user_id, uploaded_at in rows:
            uploader = "不明"
            if user_id:
                member = interaction.guild.get_member(user_id)
                uploader = member.display_name if member else str(user_id)
            date_str = "不明"
            if uploaded_at:
                dt = datetime.fromtimestamp(uploaded_at, tz=timezone.utc)
                date_str = dt.strftime("%Y/%m/%d %H:%M")
            reaction_keys = upload_store.list_reaction_keys_for_upload(interaction.guild_id, name)
            emoji_parts = []
            for rk in reaction_keys:
                if not rk.isascii() and len(rk) <= 2:
                    emoji_parts.append(rk)
                else:
                    try:
                        ch = emojize(f":{rk}:", language="alias")
                        if ch and ch != f":{rk}:":
                            emoji_parts.append(ch)
                        else:
                            emoji_parts.append(f"`:{rk}:`")
                    except Exception:
                        emoji_parts.append(f"`:{rk}:`")
                    if interaction.guild:
                        for em in interaction.guild.emojis:
                            if em.name == rk:
                                emoji_parts[-1] = str(em)
                                break
            reaction_str = " ".join(emoji_parts) if emoji_parts else "—"
            lines.append(f"・`{name}` — {uploader}（{date_str}) {reaction_str}")
        text = "\n".join(lines)
        if len(text) > 2000:
            text = text[:1997] + "..."
        await interaction.response.send_message(text)

    @app_commands.command(name="delete_files", description="アップロードした音声を削除する")
    @app_commands.describe(name="削除する音声の名前")
    @app_commands.autocomplete(name=_upload_name_autocomplete)
    async def slash_delete_files(self, interaction: discord.Interaction, name: str):
        if not interaction.guild:
            await interaction.response.send_message("サーバー内で実行してください。", ephemeral=True)
            return
        try:
            upload_store.delete_upload(interaction.guild_id, name)
            await interaction.response.send_message(f"`{name}` を削除しました。", ephemeral=True)
        except ValueError as e:
            await interaction.response.send_message(str(e), ephemeral=True)

    # --- 従来のプレフィックスコマンド（互換のため残す） ---

    @commands.command()
    async def join(self, ctx: commands.Context):
        if ctx.author.voice:
            vc = await self._connect(ctx.author.voice.channel)
            if vc:
                await ctx.send(f"「{vc.channel.name}」に参加しました。")
                return
        await ctx.message.add_reaction("🥺")

    @commands.command()
    async def leave(self, ctx: commands.Context):
        vc = self.get_guild_vc(ctx.guild)
        if vc:
            self._clear_queue_for_guild(vc.guild.id)
            await vc.disconnect()
            await ctx.send("退出しました。")

    # --- イベントハンドリング（SPEC §5.2, §8） ---

    @commands.Cog.listener(name="on_ready")
    async def on_ready_method(self):
        await self.bot.change_presence(activity=discord.Game("/join"))

    @commands.Cog.listener(name="on_message")
    async def on_message_atsumori(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return
        if not reaction_db.is_reaction_enabled(message.guild.id, message.channel.id):
            return
        try:
            text = demojize(message.content or "", delimiters=("<:", ":>"))
            res = re.findall(r"<:([^<>]+?):[0-9]*?>", text)
            for x in res:
                if x in self._emoji_list or x == "hot_springs":
                    await message.add_reaction(emojize(":" + x + ":"))
                if x in self._server_emoji_list or x == "atsumori":
                    for em in message.guild.emojis:
                        if em.name == x:
                            await message.add_reaction(em)
                # アップロード音声に設定されたサーバー絵文字が本文に含まれる場合もリアクション
                if upload_store.get_reaction_upload(message.guild.id, x):
                    for em in message.guild.emojis:
                        if em.name == x:
                            await message.add_reaction(em)
                            break
            if random.randint(1, 100) <= 10:
                atsumori_emoji = "♨️"
                for em in message.guild.emojis:
                    if em.name == "atsumori":
                        atsumori_emoji = em
                        break
                await message.add_reaction(atsumori_emoji)
            content_raw = message.content or ""
            content_lower = content_raw.lower().strip()
            # アップロード名が本文に単語として含まれるとき、紐付いたリアクションを付ける（例: "cat" → 🐱）
            for upload_name in upload_store.list_uploads(message.guild.id):
                pattern = r"\b" + re.escape(upload_name) + r"\b"
                if not re.search(pattern, content_lower, re.IGNORECASE) and content_lower != upload_name.lower():
                    continue
                for rk in upload_store.list_reaction_keys_for_upload(message.guild.id, upload_name):
                    try:
                        if not rk.isascii() and len(rk) <= 2:
                            await message.add_reaction(rk)
                            break
                        emoji_char = emojize(":" + rk + ":", language="alias")
                        if emoji_char and emoji_char != ":" + rk + ":":
                            await message.add_reaction(emoji_char)
                            break
                        for em in message.guild.emojis:
                            if em.name == rk:
                                await message.add_reaction(em)
                                break
                    except (discord.HTTPException, ValueError):
                        pass
            # 本文にアップロード設定の絵文字（Unicode や :name:）が含まれるときもリアクションを付ける
            for rk, _ in upload_store.list_all_reaction_uploads(message.guild.id):
                try:
                    if not rk.isascii() and len(rk) <= 2:
                        if rk in content_raw:
                            await message.add_reaction(rk)
                    else:
                        colon_name = ":" + rk + ":"
                        if colon_name in content_raw:
                            try:
                                ch = emojize(colon_name, language="alias")
                                if ch and ch != colon_name:
                                    await message.add_reaction(ch)
                            except Exception:
                                pass
                            for em in message.guild.emojis:
                                if em.name == rk:
                                    await message.add_reaction(em)
                                    break
                except (discord.HTTPException, ValueError):
                    pass
        except Exception as e:
            logger.exception("on_message: %s", e)

    async def _reaction_get_vc(self, message: discord.Message, user_id: int):
        member = await message.guild.fetch_member(user_id)
        if not member.voice:
            member = await message.guild.fetch_member(message.author.id)
        if not member.voice:
            return None
        return await self._connect(member.voice.channel)

    def _is_atsumori_emoji(self, emoji: discord.PartialEmoji | discord.Emoji) -> bool:
        """atsumori/熱盛トリガーか。emoji ライブラリで正規化して判定する。"""
        name = getattr(emoji, "name", None) or str(emoji)
        if name in ("atsumori", "♨", "♨️", "hot_springs"):
            return True
        # ♨️ は str(emoji) が "♨️" のままなので demojize で :hot_springs: に正規化
        key = demojize(str(emoji), delimiters=("", "")).strip(":").lower()
        return key == "hot_springs"

    async def _on_reaction_trigger(self, message: discord.Message, user_id: int, emoji: discord.PartialEmoji | discord.Emoji):
        emoji_name = getattr(emoji, "name", str(emoji))
        logger.info("[op] reaction_trigger | begin user_id=%s guild_id=%s emoji=%s message_id=%s", user_id, message.guild.id if message.guild else None, emoji_name, message.id)
        vc = await self._reaction_get_vc(message, user_id)
        if vc is None:
            logger.debug("[op] reaction_trigger | no vc, skip")
            return
        if self._is_atsumori_emoji(emoji):
            logger.info("[op] reaction | emoji=%s → atsumori (sequence) guild_id=%s", emoji_name, vc.guild.id)
            self.play_atsumori(vc)
            return
        key_unicode = demojize(str(emoji), delimiters=("", "")).strip(":")
        # ユーザーアップロード音声（/set_reaction_files で紐付けたもの）を優先
        for rk in (key_unicode, emoji_name):
            upload_name = upload_store.get_reaction_upload(vc.guild.id, rk)
            if upload_name:
                path = upload_store.get_upload_path(vc.guild.id, upload_name)
                if path and path.is_file():
                    logger.info("[op] reaction | emoji=%s → upload=%s guild_id=%s", emoji_name, upload_name, vc.guild.id)
                    self.play_single(vc, str(path))
                    return
        if key_unicode in self._emoji_list:
            path = self._pick_source_from_list(self._emoji_list[key_unicode])
            logger.info("[op] reaction | emoji=%s → file=%s guild_id=%s", emoji_name or key_unicode, path, vc.guild.id)
            self.play_single(vc, path)
            return
        if emoji_name in self._server_emoji_list:
            path = self._pick_source_from_list(self._server_emoji_list[emoji_name])
            logger.info("[op] reaction | emoji=%s → file=%s guild_id=%s", emoji_name, path, vc.guild.id)
            self.play_single(vc, path)

    @commands.Cog.listener(name="on_raw_reaction_add")
    async def on_reaction_add(self, payload: discord.RawReactionActionEvent):
        try:
            channel = self.bot.get_channel(payload.channel_id)
            if not channel or not isinstance(channel, discord.TextChannel):
                return
            message = await self._get_message_cached(channel, payload.message_id)
            if not message:
                return
            # このBotが自分の投稿（show_all_emojis／show_files 等）にリアクションしたときだけトリガーしない
            if payload.user_id == self.bot.user.id and message.author.id == self.bot.user.id:
                return
            logger.info("[op] reaction_add | message_id=%s user_id=%s channel_id=%s", payload.message_id, payload.user_id, payload.channel_id)
            await self._on_reaction_trigger(message, payload.user_id, payload.emoji)
        except Exception as e:
            logger.exception("[op] reaction_add | error: %s", e)

    @commands.Cog.listener(name="on_raw_reaction_remove")
    async def on_reaction_remove(self, payload: discord.RawReactionActionEvent):
        try:
            channel = self.bot.get_channel(payload.channel_id)
            if not channel or not isinstance(channel, discord.TextChannel):
                return
            message = await self._get_message_cached(channel, payload.message_id)
            if not message:
                return
            if payload.user_id == self.bot.user.id and message.author.id == self.bot.user.id:
                return
            logger.info("[op] reaction_remove | message_id=%s user_id=%s channel_id=%s", payload.message_id, payload.user_id, payload.channel_id)
            await self._on_reaction_trigger(message, payload.user_id, payload.emoji)
        except Exception as e:
            logger.exception("[op] reaction_remove | error: %s", e)

    @commands.Cog.listener(name="on_voice_state_update")
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ):
        # BOT 自身が VC から外れたとき（4006 等）をログで追えるようにする
        if member.id != self.bot.user.id:
            return
        if before.channel and not after.channel:
            logger.info(
                "[op] voice_disconnected | guild_id=%s channel_id=%s at=%.3f",
                member.guild.id,
                before.channel.id,
                time.monotonic(),
            )


async def setup(bot: commands.Bot):
    await bot.add_cog(Voice(bot))


async def teardown(bot: commands.Bot):
    pass
