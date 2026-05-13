# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

B站稍后再看管理器 — a Bilibili "Watch Later" list manager with two interfaces: CLI (typer) and desktop GUI (Eel + HTML). Supports QR code login, custom tag categorization, tag-based filtering, and video deletion after watching.

## Commands

```powershell
# Activate venv and set encoding
.\.venv\Scripts\activate
$env:PYTHONIOENCODING = "utf-8"

# CLI
python main.py login              # QR scan login
python main.py sync               # Sync watch later list from Bilibili
python main.py list               # Browse videos (--tag, --page, --sort, --refresh)
python main.py search <keyword>   # Search by title/author
python main.py info <bvid>        # Video details
python main.py watch <bvid>       # Open in browser, prompt to delete
python main.py delete <bvid>      # Delete without watching
python main.py tag add <name>     # Create tag
python main.py tag assign <bvid> <tag> [tag...]  # Assign tags
python main.py --help

# GUI
python app.py                     # Launch desktop app (Chrome/Edge window, 1280x820)
```

## Architecture

```
┌─────────────────────────────────────────────┐
│                 UI Layer                     │
│  main.py (CLI/typer)    app.py (GUI/Eel)    │
│       │                      │               │
│  cli/auth_commands.py    web/index.html     │
│  cli/list_commands.py   (Eel JS bridge)     │
│  cli/tag_commands.py                        │
│  cli/watch_commands.py                      │
└──────────────┬──────────────────────────────┘
               │  (all sync calls — asyncio.run handled internally)
┌──────────────▼──────────────────────────────┐
│           Business Logic                     │
│  auth.py    api.py    tags.py               │
│  (QR login, (Bilibili (tag validation)      │
│   credential API wrappers)                   │
│   mgmt)                                     │
└──────────────┬──────────────────────────────┘
               │
┌──────────────▼──────────────────────────────┐
│              Data Layer                      │
│  db.py (SQLite, 4 tables, all CRUD)         │
│  Path: %APPDATA%/bilibili-watchlater/data.db│
└─────────────────────────────────────────────┘
```

## Key design decisions

- **All Bilibili API calls are async** (bilibili-api-python v17), but every function in `auth.py` and `api.py` wraps them in `asyncio.run()` — callers treat them as plain sync functions.
- **DB connection per call**: each `@eel.expose` function in `app.py` opens its own `db.get_db()` connection and closes it. SQLite connections are not thread-safe, and Eel may call from any thread.
- **Credential storage**: key-value table (`credential_store`) rather than a user table — single-user tool. Fields: `sessdata`, `bili_jct`, `buvid3`, `dedeuserid`.
- **Soft delete**: `videos.is_watched = 1` instead of DELETE — preserves watch history. Filtered out in list/search queries (`WHERE is_watched = 0`).
- **QR login differs between CLI and GUI**: `auth.py` uses `QrCodeLogin.get_qrcode_terminal()` (ASCII art for terminal), `app.py` reads `QrCodeLogin.get_qrcode_picture().url` (local PNG file) and base64-encodes it for the web frontend.
- **db.py uses `dict` rows**: `conn.row_factory = sqlite3.Row`, and all query results are converted to plain dicts before returning.

## Data model (SQLite, `%APPDATA%/bilibili-watchlater/data.db`)

| Table | Key columns | Notes |
|-------|-------------|-------|
| `videos` | `aid` PK, `bvid`, `title`, `cover_url`, `duration`, `author_name`, `author_mid`, `added_at`, `is_watched` | Cached from Bilibili API |
| `tags` | `id` PK, `name` UNIQUE, `color`, `created_at` | User-defined custom tags |
| `video_tags` | `video_aid` + `tag_id` PK (many-to-many) | JOIN through tags table |
| `credential_store` | `key` PK, `value` | KV store for sessdata/bili_jct/buvid3/dedeuserid |
