#!/usr/bin/env sh
set -eu

cd "$(dirname "$0")"

if ! command -v uv >/dev/null 2>&1; then
    echo "未找到 uv。请先安装：https://docs.astral.sh/uv/getting-started/installation/" >&2
    exit 1
fi

uv sync --locked

if [ "${RELOAD:-0}" = "1" ]; then
    exec uv run uvicorn docmark.main:app --host "${HOST:-127.0.0.1}" --port "${PORT:-8000}" --reload
fi

exec uv run uvicorn docmark.main:app --host "${HOST:-127.0.0.1}" --port "${PORT:-8000}"
