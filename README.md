# atsumori
a Discord bot to emit atsumori

## 環境変数

`.env` に以下を設定（例は `.env.example` を参照）。

| 変数 | 説明 |
|------|------|
| `DISCORD_TOKEN` | Discord Developer Portal で発行した Bot トークン（必須） |
| `DEV_GUILD_ID` | 開発用サーバーのギルド ID（**開発モード**時のみ、そのサーバーにだけ Slash コマンドを即時反映） |
| `DEV_MODE` | `1` / `true` / `yes` のとき開発モード。`DEV_GUILD_ID` にだけコマンド同期。未設定時は全ギルドにグローバル同期。 |

## 開発サーバーへの招待（必要な権限）

Bot を開発用サーバーに追加するとき、以下の権限で招待する。

### 1. Developer Portal で Intents を有効化

[Discord Developer Portal](https://discord.com/developers/applications) → 対象アプリ → **Bot** の **Privileged Gateway Intents** で有効化：

- **Message Content Intent** … メッセージ内の絵文字検出に必要
- **Server Members Intent** … リアクションしたユーザーの VC 取得（`fetch_member`）に必要

### 2. 招待リンクで付与する Bot 権限

次の権限を付与した招待リンクを使う。

| 権限 | 用途 |
|------|------|
| チャンネルを見る (View Channels) | テキスト・ボイスチャンネルへのアクセス |
| 接続 (Connect) | ボイスチャンネルに参加 |
| 発言 (Speak) | ボイスチャンネルで音声再生 |
| メッセージ履歴を読む (Read Message History) | リアクション対象メッセージの取得 |
| リアクションを追加 (Add Reactions) | メッセージへの自動リアクション |

**招待リンクの作り方**

1. Developer Portal → 対象アプリ → **OAuth2** → **URL Generator**
2. **SCOPES**: `bot`, `applications.commands` にチェック
3. **BOT PERMISSIONS**: 上記 5 つにチェック（または「権限の数値」に `3204544` を指定）
4. 生成された URL で開発用サーバーに招待

権限の数値で指定する場合: `3204544`  
（View Channels + Connect + Speak + Read Message History + Add Reactions）

## 設定ファイル

音声トリガーは `config.json` で定義する。リポジトリには `config.example.json` があるので、コピーして編集する。

```bash
cp config.example.json config.json
```

Docker で動かす場合は `config.json` と `sounds/` を用意したうえでビルドする（`Dockerfile` がこれらを `COPY` する想定）。

## ビルド・実行

```bash
docker compose -f docker-compose.yml up -d --build
```

ローカルで動かす場合（要 Python + FFmpeg）:

```bash
python -m pip install -r requirements.txt
# config.json と sounds/ を用意すること
python main.py
```

## Bot の使い方

### Slash コマンド（推奨）

| コマンド | 説明 |
|----------|------|
| `/help` | コマンドの使い方を表示する（実行した本人にだけ表示） |
| `/join` | 実行者が参加中のボイスチャンネルに BOT が参加する |
| `/leave` | BOT が参加中のボイスチャンネルから退出する |
| `/atsumori` | 熱盛の音声を再生する（参加中 or 実行者の VC に自動参加して再生） |
| `/show_all_emojis` | 反応する絵文字一覧をチャットに投稿する |
| `/reaction_all_on` | 全チャンネルで絵文字→リアクションを ON にする |
| `/reaction_all_off` | 全チャンネルで絵文字→リアクションを OFF にする |
| `/reaction_channel` | 指定チャンネルでのみ絵文字→リアクションを ON（他は OFF） |
| `/upload_files` | 添付した音声（mp3/wav）を名前付きで保存する |
| `/show_files` | このサーバーでアップロードした音声一覧を表示する |
| `/set_reaction_files` | 指定したリアクションでアップロード音声を再生するように紐付ける |
| `/delete_files` | アップロードした音声を削除する |

**開発モード**（`python main.py --dev` または `DEV_MODE=1`）で起動し、`.env` に `DEV_GUILD_ID` を設定すると、Slash コマンドがそのサーバーにだけ即時反映される。通常起動時はコマンドは全ギルドにグローバル同期される。

### 絵文字リアクション

- メッセージに ♨️ やサーバー絵文字 `atsumori`、または `config.json` の `emoji_list` / `server_emoji_list` で紐付けた絵文字でリアクションすると、BOT が VC に参加（条件を満たす場合）し、対応する音声を再生する。
- アップロード音声（`/set_reaction_files` で紐付けた絵文字）にも反応する。人間・他 BOT・自 BOT のリアクションでトリガーする（自 BOT が自 BOT の投稿に付けたリアクションのみトリガーしない）。
- チャンネル単位で ON/OFF 可能（`/reaction_all_on`, `/reaction_all_off`, `/reaction_channel`）。仕様は `spec.md` を参照。

