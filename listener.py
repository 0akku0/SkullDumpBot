"""
SkullDump Bot - Listener
Runs in the background on your PC.
Receives every message you send to @SkullDumpBot and saves it to your Obsidian Inbox.
Notes are categorized and moved automatically in real-time using local Ollama.

Commands:
  /organize               - manually process anything left in Inbox
  /status                 - see how many items are waiting in Inbox
  /task <text>            - save directly to Tasks folder, skipping Inbox
  /approve <FolderName>   - create a new folder suggested by the organizer
  /deny <FolderName>      - skip a suggested folder (notes stay in Inbox)
"""

import os
import json
import shutil
import logging
import asyncio
import sys
import random
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from telegram import Update
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    filters, ContextTypes
)

from organizer import process_single_note, ollama_is_running

load_dotenv()

BOT_TOKEN            = os.getenv("BOT_TOKEN")
TELEGRAM_CHAT_ID     = int(os.getenv("TELEGRAM_CHAT_ID", "0"))
VAULT_PATH           = Path(os.getenv("VAULT_PATH"))
INBOX_PATH           = VAULT_PATH / "Inbox"
ATTACH_PATH          = INBOX_PATH / "attachments"
PENDING_FOLDERS_FILE = Path(__file__).parent / "pending_folders.json"
CUSTOM_FOLDERS_FILE  = Path(__file__).parent / "custom_folders.json"

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO
)
log = logging.getLogger(__name__)

GREETINGS = [
    "🧠 Skull online. Neurons firing. What shall I organise today, boss?",
    "☕ Your second brain just clocked in. Drop your chaos — I'll sort it.",
    "🤖 BEEP BOOP. SkullDump is alive. No thought too dumb, no golf tip too niche. What've you got?",
    "📬 Inbox empty. Ollama hungry. Feed me your thoughts.",
    "💀 SkullDump activated. I won't judge your notes. (I will definitely judge your notes.)",
    "🧹 Right, let's pretend to be organised. What are we dumping today?",
]


# ── helpers ────────────────────────────────────────────────────────────────────

def ts():
    return datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

def ts_display():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def write_note(filename: str, content: str) -> Path:
    INBOX_PATH.mkdir(parents=True, exist_ok=True)
    path = INBOX_PATH / filename
    path.write_text(content, encoding="utf-8")
    return path


# ── real-time categorization background task ───────────────────────────────────

async def categorize_note_bg(bot, chat_id: int, note_path: Path):
    """
    Background task: categorize a single note using Ollama and notify the user.
    Runs in a thread executor so it doesn't block the bot's event loop.
    If categorization fails, the note simply stays in Inbox — no crash.
    """
    try:
        loop = asyncio.get_event_loop()
        # process_single_note is blocking (requests call) — run in thread pool
        category, title = await loop.run_in_executor(
            None, process_single_note, note_path
        )

        if category == "Inbox":
            await bot.send_message(
                chat_id,
                "📥 Saved to *Inbox* — couldn't confidently categorize. "
                "Run /organize later or move it manually.",
                parse_mode="Markdown"
            )
        else:
            await bot.send_message(
                chat_id,
                f"📁 *{category}* / `{title}`",
                parse_mode="Markdown"
            )

    except RuntimeError as e:
        if "not running" in str(e).lower():
            await bot.send_message(
                chat_id,
                "⚠️ Ollama isn't running — note saved to Inbox. "
                "Start Ollama and run /organize to process it.",
            )
        else:
            log.error(f"Categorization RuntimeError: {e}")
            # Note stays in Inbox silently — no need to spam user with errors

    except Exception as e:
        log.error(f"Background categorization failed for {note_path.name}: {e}")
        # Note stays in Inbox — fail silently


# ── message handlers ───────────────────────────────────────────────────────────

async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    note = f"""---
type: text
date: {ts_display()}
source: telegram
status: unorganized
---

{text}
"""
    note_path = write_note(f"{ts()}_text.md", note)
    await update.message.reply_text("✅ Got it — organizing...")
    asyncio.create_task(
        categorize_note_bg(context.bot, update.message.chat_id, note_path)
    )
    log.info(f"Saved text note: {note_path.name}")


async def on_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ATTACH_PATH.mkdir(parents=True, exist_ok=True)
    stamp    = ts()
    photo    = update.message.photo[-1]
    file     = await context.bot.get_file(photo.file_id)
    img_path = ATTACH_PATH / f"{stamp}_photo.jpg"
    await file.download_to_drive(str(img_path))

    caption = update.message.caption or ""
    note = f"""---
type: photo
date: {ts_display()}
source: telegram
status: unorganized
attachment: attachments/{stamp}_photo.jpg
---

![[attachments/{stamp}_photo.jpg]]

{caption}
"""
    note_path = write_note(f"{stamp}_photo.md", note)
    await update.message.reply_text("📷 Got it — organizing...")
    asyncio.create_task(
        categorize_note_bg(context.bot, update.message.chat_id, note_path)
    )
    log.info(f"Saved photo: {img_path.name}")


async def on_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ATTACH_PATH.mkdir(parents=True, exist_ok=True)
    stamp    = ts()
    voice    = update.message.voice
    file     = await context.bot.get_file(voice.file_id)
    ogg_path = ATTACH_PATH / f"{stamp}_voice.ogg"
    await file.download_to_drive(str(ogg_path))

    note = f"""---
type: voice
date: {ts_display()}
source: telegram
status: unorganized
duration: {voice.duration}s
attachment: attachments/{stamp}_voice.ogg
---

🎙️ Voice note ({voice.duration}s)
![[attachments/{stamp}_voice.ogg]]
"""
    note_path = write_note(f"{stamp}_voice.md", note)
    await update.message.reply_text(f"🎙️ Got it ({voice.duration}s) — organizing...")
    asyncio.create_task(
        categorize_note_bg(context.bot, update.message.chat_id, note_path)
    )
    log.info(f"Saved voice: {ogg_path.name}")


async def on_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ATTACH_PATH.mkdir(parents=True, exist_ok=True)
    stamp    = ts()
    doc      = update.message.document
    file     = await context.bot.get_file(doc.file_id)
    safe     = (doc.file_name or f"file_{stamp}").replace(" ", "_")
    doc_path = ATTACH_PATH / f"{stamp}_{safe}"
    await file.download_to_drive(str(doc_path))

    caption = update.message.caption or ""
    note = f"""---
type: document
date: {ts_display()}
source: telegram
status: unorganized
filename: {doc.file_name}
attachment: attachments/{stamp}_{safe}
---

📎 {doc.file_name}
![[attachments/{stamp}_{safe}]]

{caption}
"""
    note_path = write_note(f"{stamp}_doc.md", note)
    await update.message.reply_text("📎 Got it — organizing...")
    asyncio.create_task(
        categorize_note_bg(context.bot, update.message.chat_id, note_path)
    )
    log.info(f"Saved document: {doc_path.name}")


# ── command handlers ───────────────────────────────────────────────────────────

async def cmd_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /task <text> — saves directly to Tasks folder, no Inbox needed."""
    text = " ".join(context.args).strip()
    if not text:
        await update.message.reply_text(
            "Usage: /task <your task>\nExample: /task buy golf balls"
        )
        return

    tasks_path = VAULT_PATH / "Tasks"
    tasks_path.mkdir(parents=True, exist_ok=True)

    note = f"""---
type: task
date: {ts_display()}
source: telegram
status: pending
---

- [ ] {text}
"""
    (tasks_path / f"{ts()}_task.md").write_text(note, encoding="utf-8")
    await update.message.reply_text(f"📌 Task saved: _{text}_", parse_mode="Markdown")
    log.info(f"Saved task: {text}")


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    count = len(list(INBOX_PATH.glob("*.md"))) if INBOX_PATH.exists() else 0

    ollama_status = "🟢 Ollama running" if ollama_is_running() else "🔴 Ollama not running"

    await update.message.reply_text(
        f"📬 Inbox: *{count}* item(s) waiting.\n"
        f"{ollama_status}\n\n"
        f"Send /organize to process any remaining items.",
        parse_mode="Markdown"
    )


async def _run_organizer_bg(bot, chat_id: int):
    """Run the batch organizer as a subprocess for /organize command."""
    try:
        # Quick check before spawning subprocess
        if not ollama_is_running():
            await bot.send_message(
                chat_id,
                "❌ Ollama isn't running — can't organize.\n"
                "Start it with `ollama serve` in a terminal.",
                parse_mode="Markdown"
            )
            return

        organizer = Path(__file__).parent / "organizer.py"
        proc = await asyncio.create_subprocess_exec(
            sys.executable, str(organizer),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=300)
        except asyncio.TimeoutError:
            proc.kill()
            await bot.send_message(chat_id, "⏱️ Organizer timed out after 5 minutes.")
            return

        if proc.returncode == 0:
            output = stdout.decode("utf-8", errors="replace").strip()[-800:] if stdout else "Done."
            await bot.send_message(
                chat_id,
                f"✅ Inbox organized!\n\n```\n{output}\n```",
                parse_mode="Markdown"
            )
        else:
            err = stderr.decode("utf-8", errors="replace")[:500] if stderr else "Unknown error."
            await bot.send_message(chat_id, f"⚠️ Organizer error:\n{err}")

    except Exception as e:
        log.error(f"Background organizer failed: {e}")
        await bot.send_message(chat_id, f"❌ Organizer crashed: {e}")


async def cmd_organize(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🧠 Processing your Inbox...\n"
        "I'll message you when it's done! ☕"
    )
    asyncio.create_task(_run_organizer_bg(context.bot, update.message.chat_id))


async def cmd_approve(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Create a suggested new folder and move its pending notes into it."""
    folder_name = " ".join(context.args).strip()

    if not folder_name:
        if PENDING_FOLDERS_FILE.exists():
            try:
                pending = json.loads(PENDING_FOLDERS_FILE.read_text(encoding="utf-8"))
                if pending:
                    lines = ["📋 *Pending folder approvals:*"]
                    for f, notes in pending.items():
                        lines.append(f"  • *{f}* — {len(notes)} note(s)")
                    lines.append("\nUse `/approve FolderName` to approve.")
                    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
                    return
            except Exception:
                pass
        await update.message.reply_text("No pending folder approvals.")
        return

    if not PENDING_FOLDERS_FILE.exists():
        await update.message.reply_text("No pending folder approvals.")
        return

    pending = json.loads(PENDING_FOLDERS_FILE.read_text(encoding="utf-8"))
    matched = next((k for k in pending if k.lower() == folder_name.lower()), None)

    if not matched:
        await update.message.reply_text(
            f"❌ No pending approval for '*{folder_name}*'.\n"
            f"Use `/approve` (no name) to see the full list.",
            parse_mode="Markdown"
        )
        return

    new_folder = VAULT_PATH / matched
    new_folder.mkdir(parents=True, exist_ok=True)

    moved_count = 0
    for note_name in pending[matched]:
        src = INBOX_PATH / note_name
        if src.exists():
            shutil.move(str(src), str(new_folder / note_name))
            moved_count += 1

    existing = json.loads(CUSTOM_FOLDERS_FILE.read_text(encoding="utf-8")) if CUSTOM_FOLDERS_FILE.exists() else []
    if matched not in existing:
        existing.append(matched)
    CUSTOM_FOLDERS_FILE.write_text(json.dumps(existing, indent=2, ensure_ascii=False), encoding="utf-8")

    del pending[matched]
    if pending:
        PENDING_FOLDERS_FILE.write_text(json.dumps(pending, indent=2, ensure_ascii=False), encoding="utf-8")
    else:
        PENDING_FOLDERS_FILE.unlink()

    await update.message.reply_text(
        f"✅ Created *{matched}* folder and moved {moved_count} note(s)!\n"
        f"This folder will be remembered for all future organizes.",
        parse_mode="Markdown"
    )
    log.info(f"Approved new folder: {matched} ({moved_count} notes moved)")


async def cmd_deny(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Skip a suggested folder — notes stay in Inbox."""
    folder_name = " ".join(context.args).strip()
    if not folder_name:
        await update.message.reply_text("Usage: /deny <FolderName>\nExample: /deny Cooking")
        return

    if not PENDING_FOLDERS_FILE.exists():
        await update.message.reply_text("No pending folder approvals.")
        return

    pending = json.loads(PENDING_FOLDERS_FILE.read_text(encoding="utf-8"))
    matched = next((k for k in pending if k.lower() == folder_name.lower()), None)

    if not matched:
        await update.message.reply_text(
            f"❌ No pending approval for '*{folder_name}*'.", parse_mode="Markdown"
        )
        return

    count = len(pending[matched])
    del pending[matched]
    if pending:
        PENDING_FOLDERS_FILE.write_text(json.dumps(pending, indent=2, ensure_ascii=False), encoding="utf-8")
    else:
        PENDING_FOLDERS_FILE.unlink()

    await update.message.reply_text(
        f"🗑️ Skipped *{matched}*. {count} note(s) will stay in Inbox.",
        parse_mode="Markdown"
    )
    log.info(f"Denied new folder: {matched}")


# ── startup greeting ───────────────────────────────────────────────────────────

async def post_init(application: Application) -> None:
    """Send a random greeting when the bot starts up."""
    if TELEGRAM_CHAT_ID:
        greeting = random.choice(GREETINGS)
        try:
            await application.bot.send_message(TELEGRAM_CHAT_ID, greeting)
        except Exception as e:
            log.warning(f"Could not send startup greeting: {e}")


# ── main ───────────────────────────────────────────────────────────────────────

def main():
    INBOX_PATH.mkdir(parents=True, exist_ok=True)
    ATTACH_PATH.mkdir(parents=True, exist_ok=True)

    if ollama_is_running():
        log.info("✅ Ollama is running — real-time categorization active.")
    else:
        log.warning("⚠️  Ollama is not running. Notes will be saved to Inbox only. Start with: ollama serve")

    app = Application.builder().token(BOT_TOKEN).post_init(post_init).build()

    app.add_handler(CommandHandler("status",   cmd_status))
    app.add_handler(CommandHandler("organize", cmd_organize))
    app.add_handler(CommandHandler("task",     cmd_task))
    app.add_handler(CommandHandler("approve",  cmd_approve))
    app.add_handler(CommandHandler("deny",     cmd_deny))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    app.add_handler(MessageHandler(filters.PHOTO,        on_photo))
    app.add_handler(MessageHandler(filters.VOICE,        on_voice))
    app.add_handler(MessageHandler(filters.Document.ALL, on_document))

    log.info("SkullDump bot is running. Press Ctrl+C to stop.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
