# ربات دانلود تلگرام / Telegram Download Bot

API-centric modular bot: **Django 5 + DRF + Celery + Redis + MySQL** core, separate **aiogram 3** bot that only talks HTTP to the API, and **Local Bot API** for uploads up to **2GB**.

## Architecture

| Layer | Responsibility |
|-------|----------------|
| `bot/` | Telegram UX (handlers, polling, Local Bot API upload). **No yt-dlp.** |
| `backend/apps/jobs` | Models, REST API, Celery tasks |
| `backend/apps/downloads` | yt-dlp + httpx downloaders. **No Telegram/aiogram.** |
| `telegram-bot-api` | Local Bot API (`TELEGRAM_LOCAL=1`) |

```
User → aiogram bot → Django REST → Celery worker → media volume
                         ↑                ↓
                    MySQL / Redis    Local Bot API → Telegram
```

## Quick start

### 1. Environment

```bash
cp .env.example .env
```

Fill at least:

| Variable | Where to get it |
|----------|-----------------|
| `BOT_TOKEN` | [@BotFather](https://t.me/BotFather) |
| `TELEGRAM_API_ID` / `TELEGRAM_API_HASH` | [my.telegram.org/apps](https://my.telegram.org/apps) |
| `INTERNAL_API_TOKEN` | Long random string (shared by bot + API) |
| `DJANGO_SECRET_KEY` | Random secret |
| `ALLOWED_TELEGRAM_IDS` | Your Telegram user id(s), comma-separated (empty = open for dev) |

### 2. Important: logout from cloud Bot API (Local Bot API)

If this bot token was previously used with the official `api.telegram.org`, call **logout** once before Local Bot API, otherwise local sessions can conflict:

```bash
curl "https://api.telegram.org/bot<BOT_TOKEN>/logOut"
```

Wait ~10 minutes if Telegram asks you to, then start the stack.

### 3. Run

```bash
docker compose up --build
```

Services: `mysql`, `redis`, `api`, `worker`, `bot`, `telegram-bot-api`.

API health (no auth): `http://localhost:8000/api/v1/health/`

### 4. Test in Telegram

1. `/start`
2. Send a YouTube link → choose **بهترین کیفیت** or **فقط صوت**
3. Send a small direct `.mp4` URL

## API (internal)

All endpoints except health require:

`Authorization: Bearer <INTERNAL_API_TOKEN>`

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/health/` | Liveness |
| POST | `/api/v1/jobs/` | Create job `{url, telegram_user_id, chat_id, preferred_format?}` |
| GET | `/api/v1/jobs/{id}/` | Job status |
| POST | `/api/v1/jobs/{id}/ack/` | After successful upload (triggers file cleanup) |

Statuses: `pending` → `downloading` → `ready` | `failed` → `acked`

## Local development (without full Telegram)

```bash
# Structure / import checks (no secrets)
python scripts/validate.py

# Optional: unit tests for URL router
cd backend && pip install -r requirements.txt
DJANGO_SETTINGS_MODULE=config.settings python -m pytest apps/downloads/tests -q
```

Compose validation:

```bash
docker compose config
```

## Project layout

```text
super/
  docker-compose.yml
  .env.example
  README.md
  backend/                 # Django API + Celery
    apps/accounts/         # TelegramUser
    apps/jobs/             # DownloadJob + DRF + tasks
    apps/downloads/        # yt-dlp / httpx (no telegram)
  bot/                     # aiogram 3 client only
  media/                   # shared volume mount point
  scripts/validate.py
```

## Limits

- Max file size: **2GB** (`MAX_FILE_SIZE_BYTES`)
- Concurrent jobs per user: `MAX_CONCURRENT_JOBS_PER_USER` (default 2)
- Access control: `ALLOWED_TELEGRAM_IDS` (empty = allow all in development)

## MVP notes

- Quality buttons: best / audio (yt-dlp)
- Direct HTTP downloads via httpx (filename + Content-Type)
- Persian bot messages
- Out of scope: payments, multi-bot, S3, heavy admin UI
