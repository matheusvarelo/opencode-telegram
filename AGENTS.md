# AGENTS.md — opencode-telegram

## Repo Overview
- Single-file Python 3.12+ Telegram bot: `src/bot.py`
- No tests, no linter/formatter, no CI, no build step. Do not invent any.
- Entrypoint: `python src/bot.py` (activate `.venv` first if present)

## Hard Dependencies
- **`opencode` CLI** at `~/.opencode/bin/opencode` — bot cannot run without it.
- Config at `~/.config/opencode/opencode.jsonc` must exist and be valid.
- Python deps in `requirements.txt`: `python-telegram-bot==21.10`, `python-dotenv==1.0.1`

## Environment (`.env`, copy from `.env.example`)
| Variable | Required | Purpose |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | Yes | Telegram Bot API token |
| `ALLOWED_CHAT_IDS` | No | Comma-separated chat IDs; empty = allow all |
| `OPENCODE_BIN` | No | Override opencode binary path |
| `OPENCODE_WORK_DIR` | No | Override working directory for opencode |
| `OPENCODE_MODEL` | No | Default model (passed as `-m`) |

## How the Bot Works
- Receives Telegram text → spawns `opencode run --format json --dangerously-skip-permissions [--session <id>] [-m <model>] -- <message>` as subprocess.
- Parses JSON event stream from stdout. Session ID field is **`sessionID`** (camelCase).
- Subprocess timeout: **300 s** (`TIMEOUT_SECONDS`).
- **Session retry**: if stderr contains `"session not found"`, retries without `--session`.
- Responses split at **4096 chars** (Telegram limit); prefers newline then space boundaries.
- Markdown fallback in `send_response`: tries Markdown parse mode first, falls back to plain on failure — do not remove.
- `pending` set prevents concurrent opencode calls per chat — do not remove or replace with naive lock.

## Systemd
- Service file: `systemd/opencode-telegram.service`
- Hardcoded paths for user `matheus`, venv at `/home/matheus/Projetos/opencode_telegram/.venv/bin/python`
- `ProtectSystem=full` with `ReadWritePaths` allowing opencode config/data dirs.

## Editing Rules
- Do not add tests, linting, CI, or build tooling unless explicitly asked.
- Keep changes minimal; bot is intentionally single-file.
- Preserve env-var names, subprocess flags, timeout value, and split logic.
- `sessionID` is camelCase — do not "fix" to snake_case.
- When modifying the subprocess command, keep `--format json` and `--dangerously-skip-permissions`.
