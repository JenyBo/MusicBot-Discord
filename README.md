# Discord YouTube Music Bot (Personal Server)

A lightweight personal Discord bot for one/few-user servers:

- YouTube-only playback (`yt-dlp` + `FFmpeg`)
- Core commands: play, skip, stop, queue
- Per-user personal playlists stored in SQLite
- Optional Oracle Free VPS deployment with `systemd`

## Requirements

- Python 3.11+
- FFmpeg installed and available in PATH
- **Node.js or Deno on PATH** — PyPI `yt-dlp` needs a JS runtime to solve YouTube’s player challenges (`requirements.txt` uses `yt-dlp[default]` which includes `yt-dlp-ejs`). The bot enables both `deno` and `node` runtimes by default.
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

### Help

- `/help`

### Core playback

- `/play <query_or_url>`
- `/skip`
- `/stop`
- `/queue`

### Personal playlists

- `/plist create <name>`
- `/plist add <name> <query_or_url>` (supports up to 5 items separated by commas; auto-creates playlist if missing)
- `/plist remove <name> <index>` (supports up to 5 indices separated by commas; posts updated playlist in chat)
- `/plist rename <old_name> <new_name>`
- `/plist show <name>`
- `/plist play <name>`
- `/plist list`
- `/plist delete <name>`

### Music trending

- `/trendingvn`

## Data storage

- SQLite file path: `data/musicbot.db`
- Schema includes:
  - `users`
  - `playlists`
  - `playlist_tracks`

## Voice WebSocket `4006` (“Session no longer valid”)

Discord may close the **voice control** WebSocket with code **4006**; `discord.py` will usually **reconnect automatically** (you may see a short gap or log noise). This is not the same as YouTube/FFmpeg failing.

If it happens often:

- Run `pip install -U "discord.py>=2.7.1" "davey>=0.1.5" "PyNaCl>=1.5.0"` in the same venv as the bot (DAVE/E2EE voice depends on `davey`).
- Avoid running **two processes** with the same bot token (duplicate sessions confuse voice).
- Check VPN/firewall rules for **UDP** to Discord voice endpoints.
- The bot connects with a **120s** voice handshake timeout to reduce flaky joins on slow networks.

## Notes

- This project is intended for personal testing on a private server.
- YouTube and Discord platform policies can change; make sure your usage remains compliant.
- Update dev_guild_id if you want to dev this more

## Deploy on Render

Use a **Web Service** (not Background Worker): Render injects `PORT`; the bot starts an aiohttp server on that port so the instance stays “healthy” while `discord.py` runs.

1. Push this repo to GitHub (do **not** commit `.env`, `cookies.txt`, or secrets).
2. In Render: **New → Web Service**, connect the repo, choose **Docker** (uses the root `Dockerfile`).
3. Set **environment variables** (at minimum):

   | Variable | Required | Notes |
   |----------|----------|--------|
   | `DISCORD_TOKEN` | Yes | Bot token from the Discord Developer Portal. |
   | `YTDLP_COOKIE_B64` | Strongly recommended on cloud IPs | Base64 of your Netscape `cookies.txt` (same file you use locally). Avoid committing the raw file. |
   | `YOUTUBE_API_KEY` | No | Only if you use `/trendingvn` / `/newmusicvn`. |
   | `DEV_GUILD_ID` | No | Optional: guild id for **instant** slash-command sync while testing; remove or leave unset for production global sync. |

 Optional: `YTDLP_JS_RUNTIMES=node` — the Docker image includes **Node**; default `deno,node` is fine.

4. **Health check**: `GET /` or `GET /health` returns `ok` when `PORT` is set.
5. **SQLite (`data/musicbot.db`)**: On Render the filesystem is **ephemeral** unless you add a **persistent disk** and point `db_path` at it (would require a small code/env change). Playlists reset on each redeploy otherwise.
6. **Free tier**: The service **spins down** when idle; the bot will disconnect until the next request wakes it (not ideal for 24/7 music). A paid instance or another host is better for always-on voice.

## Hosting notes (yt-dlp YouTube verification)

Some cloud hosts (Render/Railway/VPS IP ranges) may trigger YouTube "confirm you're not a bot".
If that happens, export a YouTube cookies.txt and provide it to yt-dlp using **one** of:

- `YTDLP_COOKIEFILE`: path to `cookies.txt` inside the container (e.g. if you mount a secret file)
- `YTDLP_COOKIE_B64`: base64 contents of `cookies.txt` (the bot will write it to `/tmp/yt_cookies.txt`) — **preferred on Render**
