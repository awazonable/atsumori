# Discord DAVE（E2EE 音声・動画）対応 是正計画

## 1. 背景

- **2026年3月2日以降**、Discord の音声・動画通話は **DAVE（Discord Audio & Video End-to-End Encryption）** が必須となる。
- 古い暗号化方式のまま接続すると、サーバーから **Close Code 4017** が返され、接続が即座に切断される。
- 参考: [End-to-End Encryption for Audio and Video](https://support.discord.com/hc/en-us/articles/25968222946071-End-to-End-Encryption-for-Audio-and-Video)  
  および [Bringing DAVE to All Discord Platforms](https://discord.com/blog/bringing-dave-to-all-discord-platforms)

## 2. 影響範囲

| 項目 | 内容 |
|------|------|
| 対象機能 | ボイスチャンネルへの参加・音声再生（`/join`, `/leave`, `/atsumori`, 絵文字リアクション駆動再生） |
| 依存 | `discord.py[voice]` の音声接続実装 |
| 症状 | VC 参加直後に 4017 で切断され、BOT が音声を再生できない |

## 3. 是正方針

- **discord.py を DAVE 対応がマージされたバージョンにアップグレードする。**
- discord.py では 2026年1月に PR [#10300](https://github.com/Rapptz/discord.py/pull/10300) がマージされ、DAVE プロトコル対応が追加されている。**含まれるリリース番号は [Releases](https://github.com/Rapptz/discord.py/releases) または [Changelog](https://discordpy.readthedocs.io/en/stable/whats_new.html) で確認し、そのバージョン以上を指定する。**

## 4. 是正タスク

- [ ] **4.1** `requirements.txt` の `discord.py[voice]` を DAVE 対応リリースに更新する。  
  - [discord.py Releases](https://github.com/Rapptz/discord.py/releases) / [Changelog](https://discordpy.readthedocs.io/en/stable/whats_new.html) で DAVE（PR #10300）が含まれるバージョンを確認し、そのバージョン以上（例: `>=2.5.0` など）を指定する。
- [ ] **4.2** アップグレード後、既存のボイス接続・再生フロー（`voice.py`）がそのまま動作するか確認する。  
  - 必要に応じて `voice_state_update` で Close Code 4017 のログ出力を追加し、切断原因の切り分けをしやすくする。
- [ ] **4.3** 開発環境・本番環境で以下を手動または自動でテストする。  
  - `/join` → BOT が VC に参加し、切断されないこと。  
  - `/atsumori` および絵文字リアクションで音声が再生されること。  
  - `/leave` で正常に退出すること。

## 5. 検証方法

1. **依存更新**  
   `python -m pip install -r requirements.txt -U` で discord.py を更新し、`python -m pip show discord.py` でバージョン確認。
2. **動作確認**  
   - テスト用 Guild でボイスチャンネルを作成し、BOT を `/join` で参加させる。  
   - 数秒待っても 4017 で切断されないこと、`/atsumori` で音声が流れることを確認。  
   - ログに `voice_disconnected` が 4017 系で出ていないことを確認（必要なら close_code をログに含める）。

## 6. ロールバック

- 問題が発生した場合は、`requirements.txt` を変更前のバージョンに戻し、再度 `pip install -r requirements.txt` で復旧。  
- 3月2日以降は旧クライアントは接続不可のため、ロールバックは「DAVE 対応版の別バージョンへ切り替え」に限定する。

## 7. 参考リンク

- [End-to-End Encryption for Audio and Video (Discord Support)](https://support.discord.com/hc/en-us/articles/25968222946071-End-to-End-Encryption-for-Audio-and-Video)
- [Bringing DAVE to All Discord Platforms](https://discord.com/blog/bringing-dave-to-all-discord-platforms)
- [discord.py - Add support for DAVE (Issue #9948)](https://github.com/Rapptz/discord.py/issues/9948)
- [discord.py - DAVE support PR #10300](https://github.com/Rapptz/discord.py/pull/10300)
- [Discord DAVE Protocol (GitHub)](https://github.com/discord/dave-protocol)

---

**ブランチ:** `feature/dave-voice-e2ee`  
**作成日:** 2026-03-03
