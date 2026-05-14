import asyncio
import json
import logging
import os
from pathlib import Path
from subprocess import PIPE

from dotenv import load_dotenv
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

load_dotenv()

logger = logging.getLogger(__name__)

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise SystemExit("TELEGRAM_BOT_TOKEN not set. Copy .env.example to .env and configure.")

OPENCODE_BIN = os.path.expanduser(
    os.getenv("OPENCODE_BIN", "~/.opencode/bin/opencode")
)
WORK_DIR = os.getenv("OPENCODE_WORK_DIR", str(Path(__file__).resolve().parent))
MODEL = os.getenv("OPENCODE_MODEL")

# Whitelist: if set, only these chat_ids can use the bot
_raw_allowed = os.getenv("ALLOWED_CHAT_IDS", "")
ALLOWED_CHAT_IDS: set[int] | None = None
if _raw_allowed.strip():
    ALLOWED_CHAT_IDS = {int(x.strip()) for x in _raw_allowed.split(",") if x.strip()}

MAX_MSG = 4096
TIMEOUT_SECONDS = 300

# Session store: chat_id → session_id
sessions: dict[int, str] = {}

# Track pending requests per chat
pending: set[int] = set()




async def run_opencode(message: str, session_id: str | None) -> tuple[str, str | None, str]:
    """Run opencode with a message. Returns (text_response, new_session_id, stderr)."""
    args = [OPENCODE_BIN, "run", "--format", "json", "--dangerously-skip-permissions"]
    if session_id:
        args.extend(["--session", session_id])
    if MODEL:
        args.extend(["-m", MODEL])
    args.append("--")
    args.append(message)

    proc = await asyncio.create_subprocess_exec(
        *args,
        stdout=PIPE,
        stderr=PIPE,
        cwd=WORK_DIR,
        env={**os.environ, "HOME": os.path.expanduser("~")},
    )

    async def _read_stdout() -> tuple[list[str], str | None]:
        """Read all stdout lines, extract text parts and session ID."""
        parts: list[str] = []
        sid: str | None = session_id
        assert proc.stdout is not None
        async for raw_line in proc.stdout:
            line = raw_line.decode().strip()
            if not line:
                continue
            try:
                event = json.loads(line)
                if event.get("type") == "text" and event.get("part", {}).get("text"):
                    parts.append(event["part"]["text"])
                # sessionID is the correct field name (camelCase) in opencode JSON output
                if event.get("sessionID"):
                    sid = event["sessionID"]
            except json.JSONDecodeError:
                pass  # skip non-JSON lines (plugin warnings, etc.)
        return parts, sid

    new_session_id: str | None = session_id
    stderr_data = ""

    try:
        # Timeout covers the ENTIRE operation: stdout reading + process exit
        output_parts, new_session_id = await asyncio.wait_for(
            _read_stdout(), timeout=TIMEOUT_SECONDS
        )
        # Now wait for process to fully terminate (should be immediate after stdout closes)
        await asyncio.wait_for(proc.wait(), timeout=10)
    except asyncio.TimeoutError:
        try:
            proc.kill()
        except ProcessLookupError:
            pass
        await proc.wait()
        return "❌ OpenCode timed out after 5 minutes.", new_session_id, stderr_data

    # Capture stderr for debugging
    if proc.stderr:
        stderr_bytes = await proc.stderr.read()
        stderr_data = stderr_bytes.decode(errors="replace").strip()

    if proc.returncode != 0:
        err_detail = f" stderr: {stderr_data[:500]}" if stderr_data else ""
        logger.warning("OpenCode failed (rc=%d):%s", proc.returncode, err_detail)
        return f"⚠️ OpenCode exited with code {proc.returncode}.{err_detail}", new_session_id, stderr_data

    text = "".join(output_parts).strip()
    return text, new_session_id, stderr_data


_SESSION_NOT_FOUND = "session not found"


async def run_opencode_with_retry(
    message: str, session_id: str | None, chat_id: int
) -> tuple[str, str | None]:
    """Run opencode, retrying without --session if session is invalid/expired."""
    text, new_session_id, stderr = await run_opencode(message, session_id)

    if session_id and _SESSION_NOT_FOUND in stderr.lower():
        logger.info(
            "Session invalid for chat %d, clearing and retrying without --session",
            chat_id,
        )
        sessions.pop(chat_id, None)
        text, new_session_id, _ = await run_opencode(message, session_id=None)

    return text, new_session_id


def split_message(text: str, max_len: int = MAX_MSG) -> list[str]:
    """Split text into chunks fitting Telegram message limit."""
    if len(text) <= max_len:
        return [text]

    chunks = []
    remaining = text

    while remaining:
        if len(remaining) <= max_len:
            chunks.append(remaining)
            break

        split_at = max_len
        last_nl = remaining.rfind("\n", 0, max_len)
        last_space = remaining.rfind(" ", 0, max_len)

        if last_nl > max_len * 0.5:
            split_at = last_nl
        elif last_space > max_len * 0.5:
            split_at = last_space

        chunks.append(remaining[:split_at].strip())
        remaining = remaining[split_at:].strip()

    return chunks


async def send_response(update: Update, text: str):
    """Send response, splitting if needed."""
    chunks = split_message(text)
    for i, chunk in enumerate(chunks):
        try:
            await update.message.reply_text(chunk, parse_mode="Markdown")
        except Exception:
            # Fallback without markdown
            await update.message.reply_text(chunk)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    sessions.pop(chat_id, None)
    await update.message.reply_text(
        "🤖 *OpenCode Bot*\n\n"
        "Send me any message and I'll process it using OpenCode AI.\n\n"
        "*Commands:*\n"
        "/reset — Clear conversation context\n"
        "/start — Show this message",
        parse_mode="Markdown",
    )


async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    sessions.pop(chat_id, None)
    await update.message.reply_text(
        "🔄 Context cleared. Starting fresh conversation."
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return
    if update.message.text.startswith("/"):
        return

    chat_id = update.effective_chat.id

    # Whitelist check
    if ALLOWED_CHAT_IDS is not None and chat_id not in ALLOWED_CHAT_IDS:
        logger.info("Blocked message from unauthorized chat_id=%d", chat_id)
        return

    if chat_id in pending:
        await update.message.reply_text(
            "⏳ Processing previous message. Please wait."
        )
        return

    pending.add(chat_id)

    # Show typing indicator
    await update.message.chat.send_action("typing")

    try:
        session_id = sessions.get(chat_id)
        text, new_session_id = await run_opencode_with_retry(
            update.message.text, session_id, chat_id
        )
        if new_session_id:
            sessions[chat_id] = new_session_id

        if not text:
            await update.message.reply_text("⚠️ No response from OpenCode.")
        else:
            await send_response(update, text)
    except Exception as e:
        logger.exception("Error for chat %d", chat_id)
        await update.message.reply_text(f"❌ Error: {e}")
    finally:
        pending.discard(chat_id)


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s"
    )
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("reset", reset))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("🤖 OpenCode Telegram bot started. Polling for messages...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
