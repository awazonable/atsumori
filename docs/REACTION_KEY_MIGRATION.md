# reaction_upload の reaction_key を Unicode 絵文字に統一する移行手順

DB 内の `reaction_key` が一部だけ alias（例: `coffin`）で保存されている場合、本文照合で反応しなくなるため、Unicode 絵文字に統一する移行を行います。

---

## 1. 状況確認（実行前に必ず実施）

コンテナ内で以下を実行し、現在の `reaction_upload` の内容を確認します。

```sh
sqlite3 /app/data/uploads.db "SELECT guild_id, reaction_key, upload_name FROM reaction_upload ORDER BY guild_id, reaction_key;"
```

- `reaction_key` が ASCII の行（例: `coffin`）が移行対象です。
- Unicode 絵文字（例: `🌊`, `🐱`）の行はそのままで問題ありません。

---

## 2. バックアップ付き移行スクリプト（手動実行）

コンテナのシェルで以下を**そのままコピー＆ペースト**して実行します。  
`/app/data/uploads.db.bak.YYYYMMDDHHMMSS` を作成したうえで、ASCII の `reaction_key` を `emoji.emojize()` で Unicode に変換します。

```sh
python3 - <<'PY'
import os
import shutil
import sqlite3
from datetime import datetime

DB_PATH = "/app/data/uploads.db"
if not os.path.isfile(DB_PATH):
    print("DB not found:", DB_PATH)
    exit(1)

# バックアップ
bak = DB_PATH + ".bak." + datetime.utcnow().strftime("%Y%m%d%H%M%S")
shutil.copy2(DB_PATH, bak)
print("Backup:", bak)

try:
    from emoji import emojize
except ImportError:
    print("emoji package not found. pip install emoji")
    exit(1)

conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row
cur = conn.execute(
    "SELECT guild_id, reaction_key, upload_name FROM reaction_upload ORDER BY guild_id, reaction_key"
)
rows = cur.fetchall()
conn.close()

# ASCII のみ対象（Unicode はそのまま）
updates = []
for r in rows:
    rk = r["reaction_key"]
    if not rk or not rk.isascii():
        continue
    unicode_char = emojize(f":{rk}:", language="alias")
    if unicode_char and unicode_char != f":{rk}:":
        updates.append((unicode_char, r["guild_id"], rk, r["upload_name"]))

if not updates:
    print("No rows to update (no ASCII alias reaction_key).")
    exit(0)

print("Rows to update (guild_id, old_key -> new_unicode, upload_name):")
for new_rk, gid, old_rk, name in updates:
    print(f"  guild_id={gid}  {old_rk!r} -> {new_rk!r}  upload_name={name}")

conn = sqlite3.connect(DB_PATH)
done = 0
for new_rk, gid, old_rk, name in updates:
    cur = conn.execute(
        "SELECT upload_name FROM reaction_upload WHERE guild_id = ? AND reaction_key = ?",
        (gid, new_rk),
    )
    existing = cur.fetchone()
    if existing:
        if existing[0] == name:
            conn.execute(
                "DELETE FROM reaction_upload WHERE guild_id = ? AND reaction_key = ? AND upload_name = ?",
                (gid, old_rk, name),
            )
            done += 1
        else:
            print("  Skip (unicode key already exists):", gid, new_rk, "->", existing[0])
    else:
        conn.execute(
            "UPDATE reaction_upload SET reaction_key = ? WHERE guild_id = ? AND reaction_key = ? AND upload_name = ?",
            (new_rk, gid, old_rk, name),
        )
        done += 1
conn.commit()
conn.close()
print("Done. Updated", done, "row(s).")
PY
```

---

## 3. 実行後の確認

移行後、同じ SELECT で内容を確認します。

```sh
sqlite3 /app/data/uploads.db "SELECT guild_id, reaction_key, upload_name FROM reaction_upload ORDER BY guild_id, reaction_key;"
```

- 以前 `coffin` だった行が `⚰️` など Unicode になっていれば成功です。
- 問題があればバックアップから復元できます（例: `cp /app/data/uploads.db.bak.20260303120000 /app/data/uploads.db`）。

---

## 注意

- スクリプトは**冪等**です。すでに Unicode の行は変更されず、ASCII alias の行だけが変換されます。
- 同じ `(guild_id, upload_name)` に複数 `reaction_key` が紐づいている場合、ASCII のものだけが 1 行ずつ Unicode に更新されます。
- `emoji` パッケージで変換できない alias はスキップされ、その行は更新されません。
