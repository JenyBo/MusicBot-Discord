# Discord YouTube Music Bot (Personal Server)

A lightweight personal Discord bot for one/few-user servers:

- YouTube-only playback (`yt-dlp` + `FFmpeg`)
- Core commands: play, skip, stop, queue
- Per-user personal playlists stored in SQLite
- Optional Oracle Free VPS deployment with `systemd`

## Requirements

- Python 3.11+
- FFmpeg installed and available in PATH
- Discord bot token

## Install

```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# Linux/macOS:
# source .venv/bin/activate

pip install -r requirements.txt
copy .env.example .env
```

Set `DISCORD_TOKEN` in `.env`.

## Run

```bash
python main.py
```

## Slash commands

### Core playback

- `/play <query_or_url>`
- `/skip`
- `/stop`
- `/queue`

### Personal playlists

- `/plist create <name>`
- `/plist add <name> <query_or_url>`
- `/plist remove <name> <index>`
- `/plist show <name>`
- `/plist play <name>`
- `/plist list`
- `/plist delete <name>`

## Data storage

- SQLite file path: `data/musicbot.db`
- Schema includes:
  - `users`
  - `playlists`
  - `playlist_tracks`

## Notes

- This project is intended for personal testing on a private server.
- YouTube and Discord platform policies can change; make sure your usage remains compliant.
