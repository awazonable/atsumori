# atsumori
a Discord bot to emit atsumori

## 環境変数

`.env` に以下を設定（例は `.env.example` を参照）。

| 変数 | 説明 |
|------|------|
| `DISCORD_TOKEN` | Discord Developer Portal で発行した Bot トークン（必須） |
| `DEV_GUILD_ID` | 開発用サーバーのギルド ID（指定時は Slash コマンドをそのサーバーに即時反映） |

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
| `/join` | 実行者が参加中のボイスチャンネルに BOT が参加する |
| `/leave` | BOT が参加中のボイスチャンネルから退出する |
| `/atsumori` | 熱盛の音声を再生する（参加中 or 実行者の VC に自動参加して再生） |

開発用サーバーに登録している場合は、`.env` に `DEV_GUILD_ID` を設定すると Slash コマンドがそのサーバーに即時反映される。

### 絵文字リアクション

- メッセージに ♨️ やサーバー絵文字 `atsumori` などでリアクションすると、BOT が VC に参加（条件を満たす場合）し、熱盛を再生する。
- `config.json` の `emoji_list` / `server_emoji_list` で、絵文字と再生する音声ファイルを紐付けられる。仕様は `spec.md` を参照。

