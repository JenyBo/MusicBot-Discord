# Oracle Free VPS Deployment (Ubuntu)

## 1) Provision

- Create Ubuntu VM on Oracle Cloud Free Tier.
- Open outbound access (default is usually fine).
- Ensure security list allows SSH only from your IP.

## 2) Install dependencies

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3 python3-venv python3-pip ffmpeg git
```

## 3) Prepare app

```bash
mkdir -p /opt/discord_bot
cd /opt/discord_bot
# copy your code here (git clone or upload)
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env`:

```env
DISCORD_TOKEN=your_bot_token_here
```

## 4) Test manually

```bash
cd /opt/discord_bot
source .venv/bin/activate
python main.py
```

If slash commands do not appear instantly, wait a little and re-open Discord.

## 5) Create systemd service

Create `/etc/systemd/system/discord-music-bot.service`:

```ini
[Unit]
Description=Discord Music Bot
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/opt/discord_bot
EnvironmentFile=/opt/discord_bot/.env
ExecStart=/opt/discord_bot/.venv/bin/python /opt/discord_bot/main.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable discord-music-bot
sudo systemctl start discord-music-bot
sudo systemctl status discord-music-bot
```

Logs:

```bash
journalctl -u discord-music-bot -f
```
