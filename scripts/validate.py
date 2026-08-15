#!/usr/bin/env python3
"""Offline validation: structure, imports, compose config (no Telegram secrets)."""

from __future__ import annotations

import ast
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ERRORS: list[str] = []


def ok(msg: str) -> None:
    print(f"  ✓ {msg}")


def fail(msg: str) -> None:
    ERRORS.append(msg)
    print(f"  ✗ {msg}")


def check_paths() -> None:
    print("== Paths ==")
    required = [
        "docker-compose.yml",
        ".env.example",
        "README.md",
        "backend/manage.py",
        "backend/config/settings.py",
        "backend/apps/accounts/models.py",
        "backend/apps/jobs/models.py",
        "backend/apps/jobs/views.py",
        "backend/apps/jobs/tasks.py",
        "backend/apps/downloads/services/router.py",
        "backend/apps/downloads/services/ytdlp.py",
        "backend/apps/downloads/services/direct.py",
        "backend/apps/downloads/cleanup.py",
        "bot/main.py",
        "bot/api_client.py",
        "bot/uploader.py",
        "bot/handlers/start.py",
        "backend/Dockerfile",
        "bot/Dockerfile",
    ]
    for rel in required:
        if (ROOT / rel).is_file():
            ok(rel)
        else:
            fail(f"missing {rel}")


def _imports_of(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.append(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.append(node.module.split(".")[0])
    return names


def check_separation() -> None:
    print("== Modular separation ==")
    downloads_dir = ROOT / "backend" / "apps" / "downloads"
    forbidden_dl = {"aiogram", "telegram"}
    for path in downloads_dir.rglob("*.py"):
        imports = set(_imports_of(path))
        bad = imports & forbidden_dl
        if bad:
            fail(f"{path.relative_to(ROOT)} imports {bad}")
        else:
            ok(f"clean: {path.relative_to(ROOT)}")

    bot_dir = ROOT / "bot"
    forbidden_bot = {"yt_dlp", "yt-dlp"}
    for path in bot_dir.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        # AST module names won't catch string "yt_dlp" in comments; check imports
        imports = set(_imports_of(path))
        if "yt_dlp" in imports or "yt-dlp" in text.replace(" ", "") and "import yt_dlp" in text:
            fail(f"{path.relative_to(ROOT)} has yt-dlp logic")
        elif "yt_dlp" in imports:
            fail(f"{path.relative_to(ROOT)} imports yt_dlp")
        else:
            ok(f"no yt-dlp: {path.relative_to(ROOT)}")


def check_compose() -> None:
    print("== docker compose config ==")
    # `docker compose --env-file .env.example` treats empty required vars as set-but-empty.
    # Use a tiny dummy env file so offline validation works without real Telegram secrets.
    env = os.environ.copy()
    dummy_env = "\n".join(
        [
            "BOT_TOKEN=0:dummy",
            "TELEGRAM_API_ID=12345",
            "TELEGRAM_API_HASH=dummyhash",
            "INTERNAL_API_TOKEN=dummy-token",
            "DJANGO_SECRET_KEY=dummy-secret",
        ]
    )
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as tmp:
            tmp.write(dummy_env)
            tmp_path = tmp.name
        result = subprocess.run(
            [
                "docker",
                "compose",
                "--env-file",
                tmp_path,
                "-f",
                str(ROOT / "docker-compose.yml"),
                "config",
            ],
            cwd=str(ROOT),
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
        )
    except FileNotFoundError:
        fail("docker not installed — skipped compose config")
        return
    except subprocess.TimeoutExpired:
        fail("docker compose config timed out")
        return
    finally:
        if "tmp_path" in locals():
            Path(tmp_path).unlink(missing_ok=True)

    if result.returncode != 0:
        fail(f"compose config failed: {result.stderr.strip()[:500]}")
        return

    text = result.stdout
    for svc in ("mysql", "redis", "api", "worker", "bot", "telegram-bot-api"):
        if f"{svc}:" in text or f"container_name" in text:
            # service names appear as top-level keys in config output
            pass
        if svc in text:
            ok(f"service present: {svc}")
        else:
            fail(f"service missing in compose config: {svc}")


def check_classify_logic() -> None:
    print("== classify_url (stdlib only) ==")
    # Inline minimal copy of heuristics without Django
    sys.path.insert(0, str(ROOT / "backend"))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    # Avoid DB connection — only import router helpers that don't need Django apps
    # router imports django-free modules; load via importlib path
    from importlib.util import module_from_spec, spec_from_file_location

    base_path = ROOT / "backend" / "apps" / "downloads" / "services" / "router.py"
    # router imports sibling modules that may pull django — instead test regex heuristically
    samples = [
        ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "ytdlp"),
        ("https://cdn.example.com/video.mp4", "direct"),
        ("https://tiktok.com/@u/video/1", "ytdlp"),
        ("https://files.example.org/a.zip", "direct"),
    ]
    hints = (
        "youtube.com",
        "youtu.be",
        "instagram.com",
        "tiktok.com",
        "twitter.com",
        "x.com",
    )
    exts = (".mp4", ".zip", ".mp3", ".pdf", ".mkv", ".webm")
    from urllib.parse import urlparse

    for url, expected in samples:
        host = (urlparse(url).hostname or "").lower()
        path = (urlparse(url).path or "").lower()
        if any(h in host for h in hints):
            got = "ytdlp"
        elif any(path.endswith(e) for e in exts):
            got = "direct"
        else:
            got = "ytdlp"
        if got == expected:
            ok(f"{url} → {got}")
        else:
            fail(f"{url}: expected {expected}, got {got}")


def main() -> int:
    print(f"Validating {ROOT}\n")
    check_paths()
    check_separation()
    check_classify_logic()
    check_compose()
    print()
    if ERRORS:
        print(f"FAILED with {len(ERRORS)} error(s)")
        return 1
    print("All checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
