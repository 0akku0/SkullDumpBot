# SkullDump Bot

A personal Telegram bot that acts as a second brain — capture anything (text, photos, voice notes, files) and it automatically organises everything into your Obsidian vault using local AI, in real time.

No cloud API costs. No rate limits. Runs entirely on your machine.

---

## How it works

```
You (Telegram)
      │
      ▼
listener.py  ──────►  saves note to Obsidian Inbox
      │
      ▼  [async background task]
organizer.py  ──────►  Ollama (llama3.2, local)
      │
      ▼
Correct Obsidian folder  ──────►  Telegram notification
e.g. Golf / golf-swing-tips
```

Every message is categorised immediately after it's saved — no batch processing, no waiting. The bot replies instantly, then sends a follow-up once the AI has filed it.

---

## Features

- **Real-time categorisation** — each message is processed in the background the moment it arrives
- **Multiple input types** — text, photos (with captions), voice notes, and file attachments
- **Local AI** — uses [Ollama](https://ollama.ai) running on your machine (llama3.2) — free, private, no quota
- **Voice transcription** — optional local transcription via OpenAI Whisper
- **Smart folder routing** — 10 built-in categories + user-approved custom folders that are remembered
- **Startup greeting** — bot sends a random greeting on every launch so you know it's online
- **One-click startup** — `start.bat` handles Ollama + bot launch automatically on Windows

---

## Tech Stack

| Layer | Tool |
|-------|------|
| Bot framework | python-telegram-bot 21.6 (async) |
| AI categorisation | Ollama — llama3.2:latest (local) |
| Voice transcription | OpenAI Whisper (local, optional) |
| Note storage | Obsidian vault (plain Markdown files) |
| Language | Python 3.10+ |

---

## Bot Commands

| Command | What it does |
|---------|-------------|
| `/status` | Shows inbox count and Ollama health |
| `/organize` | Manually process anything left in Inbox |
| `/task <text>` | Save directly to Tasks folder, skip Inbox |
| `/approve <Folder>` | Create a new folder suggested by the AI |
| `/deny <Folder>` | Skip a suggested folder |

---

## Obsidian Folder Structure

| Folder | What goes there |
|--------|----------------|
| Certification | Exam prep, cert study notes |
| Hackathons | Ideas, team notes, competition info |
| Networking | Contacts, events, LinkedIn connections |
| Personal Projects | Side projects, experiments, portfolio work |
| SIM | University notes, assignments |
| Tasks | To-dos, reminders, deadlines |
| Travel | Trip plans, itineraries, budgets |
| Wishlist | Things to buy |
| Golf | Tips, drills, swing notes, gear |
| Using Claude | AI workflows, prompts, experiments |
| Inbox | Anything unclear — review manually |

Custom folders can be suggested by the AI and approved via `/approve FolderName`. Once approved, they're saved permanently and used in all future categorisations.

---

## Setup

### Prerequisites

- Python 3.10+
- [Ollama](https://ollama.ai) installed and `llama3.2` pulled:
  ```bash
  ollama pull llama3.2
  ```
- A Telegram bot token from [@BotFather](https://t.me/BotFather)
- An Obsidian vault folder
- Your Telegram chat ID (get it from [@userinfobot](https://t.me/userinfobot))

### Installation

1. **Clone the repo**
   ```bash
   git clone https://github.com/0akku0/SkullDumpBot.git
   cd SkullDumpBot
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure environment**
   ```bash
   cp .env.example .env
   ```
   Then open `.env` and fill in your values:
   ```
   BOT_TOKEN=your_telegram_bot_token
   VAULT_PATH=C:\path\to\your\ObsidianVault
   TELEGRAM_CHAT_ID=your_chat_id
   ```

4. **Start the bot**

   **Windows (recommended):** Double-click `start.bat` — it checks if Ollama is running, starts it if not, then launches the bot.

   **Manual:**
   ```bash
   ollama serve          # in one terminal
   python listener.py    # in another terminal
   ```

5. **Message your bot on Telegram** — you'll get a greeting confirming it's online.

### Optional: Voice Transcription

Voice notes are saved as `.ogg` files. To also get a text transcription, install Whisper:

```bash
pip install openai-whisper
```

Transcriptions are appended to the note automatically when `/organize` is run.

---

## Why local AI instead of a cloud API?

The original version used Google Gemini. A single burst of 21 photos exhausted the free daily quota in seconds, causing the organiser to retry for hours with no way to abort. Switching to Ollama eliminated the problem entirely — llama3.2 runs locally, processes notes in under 2 seconds each, and has no rate limits or costs.

---

## Project Structure

```
SkullDumpBot/
├── listener.py          # Telegram bot — handles all message types and commands
├── organizer.py         # AI categorisation — Ollama call, folder routing, batch /organize
├── transcriber.py       # Local Whisper transcription for voice notes
├── start.bat            # Windows one-click launcher
├── requirements.txt     # Python dependencies
├── .env.example         # Environment variable template
└── .gitignore
```

---

## License

MIT
