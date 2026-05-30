"""
SkullDump Voice Transcriber
Uses OpenAI Whisper (runs locally, free, no API key needed) to transcribe
voice notes into text so they are searchable in Obsidian.

Requires: pip install openai-whisper
Requires: ffmpeg installed  →  winget install ffmpeg
"""

import logging
from pathlib import Path

log = logging.getLogger(__name__)

_model = None  # lazy-loaded so it doesn't slow down startup


def _load_model():
    global _model
    if _model is None:
        import whisper
        log.info("Loading Whisper model (first run may take a moment)...")
        _model = whisper.load_model("base")
    return _model


def transcribe(audio_path: Path) -> str:
    """
    Transcribe an audio file and return the text.
    Returns empty string if transcription fails.
    """
    try:
        model  = _load_model()
        result = model.transcribe(str(audio_path))
        text   = result["text"].strip()
        log.info(f"Transcribed {audio_path.name}: {text[:60]}...")
        return text
    except Exception as e:
        log.error(f"Transcription failed for {audio_path.name}: {e}")
        return ""
