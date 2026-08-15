#!/usr/bin/env bash
# Log the bot out of api.telegram.org before first Local Bot API use.
# Usage: BOT_TOKEN=123:ABC ./scripts/logout_cloud_bot_api.sh
set -euo pipefail

if [[ -z "${BOT_TOKEN:-}" ]]; then
  echo "Set BOT_TOKEN env var" >&2
  exit 1
fi

curl -sS "https://api.telegram.org/bot${BOT_TOKEN}/logOut"
echo
echo "If Telegram asks you to wait, wait ~10 minutes, then: docker compose up --build"
