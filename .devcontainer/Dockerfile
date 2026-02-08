# discord.py 2.x + FFmpeg（ボイス再生用）
FROM mcr.microsoft.com/devcontainers/python:1-3.12-bookworm

# FFmpeg をインストール（ボイスチャンネル再生に必須）
RUN apt-get update && export DEBIAN_FRONTEND=noninteractive \
    && apt-get install -y --no-install-recommends \
    ffmpeg \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# 非 root で使う場合の作業ディレクトリ
WORKDIR /workspace
