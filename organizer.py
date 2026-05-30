"""
SkullDump Organizer
Reads .md files in your Obsidian Inbox, uses local Ollama to categorize,
and moves them to the right folder automatically.

Run manually:  python organizer.py
Or trigger it from Telegram with /organize
"""

import os
import sys
import json
import shutil
import logging
import re
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

# Fix Windows console encoding so emoji prints correctly
if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")
if sys.stderr.encoding != "utf-8":
    sys.stderr.reconfigure(encoding="utf-8")

load_dotenv()

VAULT_PATH           = Path(os.getenv("VAULT_PATH"))
INBOX_PATH           = VAULT_PATH / "Inbox"
CUSTOM_FOLDERS_FILE  = Path(__file__).parent / "custom_folders.json"
PENDING_FOLDERS_FILE = Path(__file__).parent / "pending_folders.json"

OLLAMA_URL   = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "llama3.2:latest"

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger(__name__)


# ── folder map ─────────────────────────────────────────────────────────────────

FOLDERS = {
    "Certification":     VAULT_PATH / "Certification",
    "Hackathons":        VAULT_PATH / "Hackathons",
    "Networking":        VAULT_PATH / "Networking",
    "Personal Projects": VAULT_PATH / "Personal Projects",
    "SIM":               VAULT_PATH / "SIM",
    "Tasks":             VAULT_PATH / "Tasks",
    "Travel":            VAULT_PATH / "Travel",
    "Wishlist":          VAULT_PATH / "Wishlist",
    "Golf":              VAULT_PATH / "Golf",
    "Using Claude":      VAULT_PATH / "Using Claude",
    "Inbox":             INBOX_PATH,
}

BASE_DESCRIPTIONS = {
    "Certification":     "Professional certs (AWS, CompTIA, Google, etc.), exam prep, cert study notes",
    "Hackathons":        "Hackathon ideas, team notes, project plans, competition info, prizes",
    "Networking":        "People met, contact details, networking events, LinkedIn connections, referrals",
    "Personal Projects": "Personal coding/building projects, side projects, experiments, portfolio work",
    "SIM":               "School/uni notes, modules, assignments, lecture notes, anything for SIM diploma",
    "Tasks":             "To-do items, reminders, action items, follow-ups, deadlines",
    "Travel":            "Travel plans, trip notes, places to visit, holiday budgets, itineraries",
    "Wishlist":          "Things to buy — gear, gadgets, clothes, sports equipment, tech, anything to purchase",
    "Golf":              "Golf tips, drills, swing notes, mentor advice, golf gear, course notes",
    "Using Claude":      "Ideas and experiments using Claude AI, prompts, Claude projects, AI workflows",
    "Inbox":             "Use ONLY if truly ambiguous or spans multiple categories",
}


# ── Ollama caller ───────────────────────────────────────────────────────────────

def ollama_call(prompt: str, system: str, timeout: int = 30) -> str:
    """
    Call local Ollama model. Returns the response text.
    Raises RuntimeError if Ollama is not running or request fails.
    """
    try:
        r = requests.post(
            OLLAMA_URL,
            json={
                "model":  OLLAMA_MODEL,
                "prompt": prompt,
                "system": system,
                "format": "json",   # forces valid JSON output
                "stream": False,
                "options": {
                    "temperature": 0.1,  # low = consistent categorization
                    "num_predict": 150,  # short output — just the JSON object
                }
            },
            timeout=timeout
        )
        r.raise_for_status()
        return r.json()["response"]
    except requests.exceptions.ConnectionError:
        raise RuntimeError("Ollama is not running. Start it with: ollama serve")
    except requests.exceptions.Timeout:
        raise RuntimeError(f"Ollama timed out after {timeout}s — model may be loading, try again")
    except Exception as e:
        raise RuntimeError(f"Ollama error: {e}")


def ollama_is_running() -> bool:
    """Quick health check — returns True if Ollama is reachable."""
    try:
        requests.get("http://localhost:11434", timeout=5)
        return True
    except Exception:
        return False


# ── prompts ─────────────────────────────────────────────────────────────────────

def build_system_prompt() -> str:
    folder_list = ", ".join(k for k in FOLDERS if k != "Inbox") + ", Inbox"
    lines = [
        "You are a note organizer for a student's second brain in Obsidian.",
        "Given a note's content, return a JSON object with exactly two fields:",
        '  "category": the folder name the note belongs in',
        '  "title": a short 3-5 word kebab-case filename (no extension, no spaces)',
        "",
        "Folder guide:",
    ]
    for name, desc in BASE_DESCRIPTIONS.items():
        lines.append(f"  {name}: {desc}")
    lines += [
        "",
        f"category must be exactly one of: {folder_list}",
        "",
        "Title examples: golf-swing-tips, aws-cert-study, john-tan-networking, tokyo-trip-plan",
        "",
        'Return ONLY valid JSON, nothing else. Example: {"category": "Golf", "title": "mentor-swing-tips"}',
    ]
    return "\n".join(lines)


# ── custom folder loader ────────────────────────────────────────────────────────

def load_custom_folders():
    if not CUSTOM_FOLDERS_FILE.exists():
        return
    try:
        names = json.loads(CUSTOM_FOLDERS_FILE.read_text(encoding="utf-8"))
        for name in names:
            if name not in FOLDERS:
                FOLDERS[name] = VAULT_PATH / name
                BASE_DESCRIPTIONS[name] = f"Notes about {name}"
    except Exception as e:
        log.warning(f"Could not load custom folders: {e}")


# ── voice transcription ─────────────────────────────────────────────────────────

def maybe_transcribe_voice(note_file: Path, content: str) -> str:
    if "type: voice" not in content:
        return content

    audio_path = None
    for line in content.splitlines():
        if line.startswith("attachment:"):
            rel = line.split("attachment:", 1)[1].strip()
            candidate = INBOX_PATH / rel
            if candidate.exists() and candidate.suffix.lower() in {".ogg", ".mp3", ".m4a", ".wav"}:
                audio_path = candidate
                break

    if not audio_path or "## Transcription" in content:
        return content

    try:
        from transcriber import transcribe
        text = transcribe(audio_path)
        if text:
            updated = content.rstrip() + f"\n\n## Transcription\n\n{text}\n"
            note_file.write_text(updated, encoding="utf-8")
            log.info(f"Transcribed voice note: {audio_path.name}")
            return updated
    except ImportError:
        log.warning("Whisper not installed — skipping transcription.")
    except Exception as e:
        log.warning(f"Transcription skipped: {e}")

    return content


# ── parse Ollama JSON response ──────────────────────────────────────────────────

def parse_response(raw: str, filename: str) -> tuple[str, str]:
    """Parse the JSON response from Ollama into (category, title)."""
    raw = raw.strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)

    try:
        data     = json.loads(raw)
        category = str(data.get("category", "Inbox")).strip()
        title    = str(data.get("title", "untitled")).strip().lower()
    except (json.JSONDecodeError, KeyError, AttributeError):
        log.warning(f"Could not parse Ollama JSON for {filename}: {raw!r}")
        return "Inbox", "untitled"

    if category not in FOLDERS:
        log.warning(f"Unknown category '{category}' for {filename} — sending to Inbox")
        category = "Inbox"

    title = re.sub(r'[<>:"/\\|?*\s]', '-', title).replace(".md", "")
    title = re.sub(r'-+', '-', title).strip('-')
    title = title[:60] if title else "untitled"

    return category, title


# ── core: process a single note ─────────────────────────────────────────────────

def process_single_note(note_path: Path) -> tuple[str, str]:
    """
    Categorize and move one note file.

    Returns (category, title).
    - If category is 'Inbox', the file is left in place.
    - Otherwise the file is moved to the correct folder.
    Raises RuntimeError if Ollama is unreachable.
    """
    load_custom_folders()

    content = note_path.read_text(encoding="utf-8")
    content = maybe_transcribe_voice(note_path, content)

    # llama3.2 is text-only — use filename + text content only
    # (photos: caption and metadata are enough for categorization)
    prompt = f"File: {note_path.name}\n\n{content[:1500]}"

    raw      = ollama_call(prompt, build_system_prompt())
    category, title = parse_response(raw, note_path.name)

    if category == "Inbox":
        return "Inbox", title

    # Move to correct folder
    dest_dir = FOLDERS[category]
    dest_dir.mkdir(parents=True, exist_ok=True)
    new_name = f"{title}.md"
    dest     = dest_dir / new_name

    if dest.exists():
        dest = dest_dir / f"{title}_dup.md"

    shutil.move(str(note_path), str(dest))
    log.info(f"Moved: {note_path.name} → {category}/{dest.name}")

    return category, title


# ── batch organizer (used by /organize command) ─────────────────────────────────

def organize_inbox():
    load_custom_folders()

    files = sorted(INBOX_PATH.glob("*.md")) if INBOX_PATH.exists() else []

    if not files:
        print("✅ Inbox is empty — nothing to organize.")
        return

    # Health check before starting — fail fast instead of wasting time
    if not ollama_is_running():
        print("❌ Ollama is not running. Start it with: ollama serve")
        print("   Then try /organize again.")
        return

    print(f"🧠 Found {len(files)} item(s) to organize...\n")
    moved  = {}
    errors = []

    for note in files:
        try:
            category, title = process_single_note(note)

            if category == "Inbox":
                print(f"  📥  {note.name}  →  Inbox (kept, unclear)")
            else:
                new_name = f"{title}.md"
                moved.setdefault(category, []).append(new_name)
                print(f"  ✅  {note.name}  →  {category} / {new_name}")

        except RuntimeError as e:
            # Ollama went down mid-run — abort immediately, don't waste time
            print(f"\n❌ Stopping: {e}")
            print(f"   {len(errors)} error(s) so far. Remaining files left in Inbox.")
            break
        except Exception as e:
            errors.append(note.name)
            log.error(f"Error on {note.name}: {e}")
            print(f"  ❌  {note.name}  →  Error: {e}")

    total = sum(len(v) for v in moved.values())
    print(f"\n📊 Done — moved {total} item(s).")
    for folder, names in moved.items():
        print(f"     {folder}: {len(names)}")
    if errors:
        print(f"     ⚠️  Errors: {len(errors)}")


if __name__ == "__main__":
    organize_inbox()
