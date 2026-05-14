# OpenCode Telegram Bot

Telegram bot that uses [opencode](https://github.com/opencode-ai/opencode) CLI as AI backend. Each Telegram chat gets its own isolated conversation session.

## Features

- Per-user conversation context (session persistence per chat_id)
- `/start` — Welcome message
- `/reset` — Clear conversation context
- Automatic message splitting for long responses (4096 char limit)
- Typing indicator while processing
- Systemd service for auto-start
- Optional chat ID whitelist for access control

## Prerequisites

- Python >= 3.12
- opencode CLI installed (`~/.opencode/bin/opencode`)
- opencode configured (`~/.config/opencode/opencode.jsonc`)
- Telegram Bot Token (get from [@BotFather](https://t.me/BotFather))

## Installation

```bash
cd /home/matheus/Projetos/opencode_telegram

# Create virtual environment (recommended)
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env and add your TELEGRAM_BOT_TOKEN
```

## Running

### Direct

```bash
python3 src/bot.py
# or with venv activated:
python src/bot.py
```

### Systemd (production)

```bash
# Edit service file to match your paths if needed
# IMPORTANT: ExecStart points to the venv python — adjust if your venv path differs
sudo cp systemd/opencode-telegram.service /etc/systemd/system/

# Reload systemd
sudo systemctl daemon-reload

# Enable and start
sudo systemctl enable --now opencode-telegram.service

# Check status
sudo systemctl status opencode-telegram.service

# View logs
sudo journalctl -u opencode-telegram.service -f
```

## Configuration

| Variable | Description | Default |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | Telegram bot token (required) | — |
| `ALLOWED_CHAT_IDS` | Comma-separated list of allowed chat IDs. If set, all other chats are ignored. | unset (all allowed) |
| `OPENCODE_BIN` | Path to opencode binary | `~/.opencode/bin/opencode` |
| `OPENCODE_WORK_DIR` | Working directory for opencode | Project dir |
| `OPENCODE_MODEL` | Model override (provider/model) | Uses opencode config |

## How It Works

1. Bot receives message from Telegram user
2. Looks up session ID for that `chat_id`
3. Runs `opencode run --format json --dangerously-skip-permissions [--session <id>] -- <message>`
4. Parses JSON event stream, extracts text responses
5. Stores new session ID for conversation continuity
6. Sends response back to Telegram (splitting if > 4096 chars)

## Security Note

The bot passes `--dangerously-skip-permissions` to opencode to avoid interactive permission prompts that would hang the subprocess. This means opencode can read/write files and execute tools without confirmation. Only use this bot in trusted environments with controlled prompts.

Set `ALLOWED_CHAT_IDS` in `.env` to restrict which Telegram chats can interact with the bot.
