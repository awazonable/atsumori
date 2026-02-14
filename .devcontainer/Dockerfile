# discord.py 2.x + FFmpeg（ボイス再生用）
FROM mcr.microsoft.com/devcontainers/python:1-3.12-bookworm

# ベースイメージの壊れた Yarn リポジトリを無効化してから apt 実行
RUN for f in /etc/apt/sources.list.d/*.list; do [ -f "$f" ] && grep -ql yarn "$f" && mv "$f" "$f.bak"; done 2>/dev/null || true

# FFmpeg をインストール（ボイスチャンネル再生に必須）
RUN apt-get update && export DEBIAN_FRONTEND=noninteractive \
    && apt-get install -y --no-install-recommends \
    ffmpeg \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# 非 root で使う場合の作業ディレクトリ
WORKDIR /workspace
