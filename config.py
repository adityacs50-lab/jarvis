"""Central configuration and logging setup for Jarvis."""
import json
import logging
import os

from dotenv import load_dotenv

load_dotenv()

# --- API keys -------------------------------------------------------------
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")

# --- Audio ----------------------------------------------------------------
SAMPLE_RATE = 16000          # 16 kHz mono — required by webrtcvad & whisper
CHANNELS = 1
FRAME_MS = 30                # webrtcvad accepts 10/20/30 ms frames

# --- Wake word ------------------------------------------------------------
WAKE_WORD = os.getenv("WAKE_WORD", "jarvis")
WAKE_THRESHOLD = float(os.getenv("WAKE_THRESHOLD", "0.5"))

# --- Recording / VAD ------------------------------------------------------
VAD_AGGRESSIVENESS = int(os.getenv("VAD_AGGRESSIVENESS", "2"))  # 0-3
SILENCE_TIMEOUT_MS = int(os.getenv("SILENCE_TIMEOUT_MS", "800"))  # stop after this much silence
MAX_RECORD_SECONDS = int(os.getenv("MAX_RECORD_SECONDS", "15"))
MIN_SPEECH_MS = int(os.getenv("MIN_SPEECH_MS", "300"))  # ignore tiny blips

# --- STT (faster-whisper) -------------------------------------------------
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "base")  # tiny/base/small/medium
WHISPER_COMPUTE_TYPE = os.getenv("WHISPER_COMPUTE_TYPE", "int8")
WHISPER_DEVICE = os.getenv("WHISPER_DEVICE", "cpu")

# --- LLM ------------------------------------------------------------------
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6")
CLAUDE_MAX_TOKENS = int(os.getenv("CLAUDE_MAX_TOKENS", "200"))
# Study Mode allows longer answers when the student wants a real explanation.
STUDY_MAX_TOKENS = int(os.getenv("STUDY_MAX_TOKENS", "600"))
SYSTEM_PROMPT = (
    "You are Jarvis, a helpful voice assistant with a witty, concise personality. "
    "Your responses are spoken aloud, so keep them SHORT — typically one or two "
    "sentences, never long paragraphs. Be direct, a little clever, and never "
    "ramble. Skip markdown, bullet points, and emoji since they can't be spoken."
)

# Extra guidance injected only for the intent-routing call. Strongly biases
# toward live web lookup when there's any doubt the answer is static.
ROUTING_GUIDANCE = (
    "When deciding how to handle a request, follow this rule: if you are NOT "
    "highly confident the answer is timeless, static knowledge (math, "
    "definitions, coding help, casual chat, explaining a concept, a joke), "
    "prefer the web_lookup tool over answering from memory. Searching when you "
    "didn't strictly need to is cheap and harmless; answering with stale or "
    "uncertain info is worse. Anything involving current events, weather, news, "
    "prices, scores, 'who is the current/latest X', or any named person, "
    "company, product, place, or event you aren't sure is unchanging should use "
    "web_lookup. Still route clear music requests to music_control and clear "
    "computer/app/file requests to system_control."
)

# --- Vision (Phase 8) -----------------------------------------------------
WEBCAM_INDEX = int(os.getenv("WEBCAM_INDEX", "0"))
# Seconds to wait after the heads-up before capturing, so the user can position.
CAPTURE_DELAY_SECONDS = float(os.getenv("CAPTURE_DELAY_SECONDS", "2"))
JARVIS_TEMP_DIR = os.getenv("JARVIS_TEMP_DIR", "jarvis_temp")
CAPTURE_PATH = os.path.join(JARVIS_TEMP_DIR, "capture.jpg")
# Keep captured webcam frames on disk instead of deleting after analysis.
KEEP_CAPTURES = os.getenv("KEEP_CAPTURES", "false").lower() in ("1", "true", "yes")

# --- Memory (Phase 7) -----------------------------------------------------
MEMORY_DB_PATH = os.getenv("MEMORY_DB_PATH", "jarvis_memory.db")
# How many recent memory notes to load into the system prompt at startup.
MEMORY_NOTES_TO_LOAD = int(os.getenv("MEMORY_NOTES_TO_LOAD", "10"))
# Summarize the session into a memory note every N logged exchanges.
MEMORY_SUMMARIZE_EVERY = int(os.getenv("MEMORY_SUMMARIZE_EVERY", "6"))

# --- Spotify --------------------------------------------------------------
SPOTIPY_CLIENT_ID = os.getenv("SPOTIPY_CLIENT_ID", "")
SPOTIPY_CLIENT_SECRET = os.getenv("SPOTIPY_CLIENT_SECRET", "")
SPOTIPY_REDIRECT_URI = os.getenv("SPOTIPY_REDIRECT_URI", "http://127.0.0.1:8888/callback")
SPOTIPY_CACHE_PATH = os.getenv("SPOTIPY_CACHE_PATH", ".spotify_cache")

# --- System control (Phase 3) ---------------------------------------------
# App nickname -> executable mapping and folder shortcuts live in a JSON file
# so they can be edited without touching code (it's OS-specific).
SYSTEM_CONFIG_PATH = os.getenv("SYSTEM_CONFIG_PATH", "system_config.json")


def load_system_config():
    """Load the app/folder mapping JSON. Returns {} if the file is missing."""
    try:
        with open(SYSTEM_CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        logging.getLogger("jarvis").warning(
            "System config '%s' not found; app shortcuts unavailable.",
            SYSTEM_CONFIG_PATH,
        )
        return {"apps": {}, "folders": {}}
    return {
        "apps": data.get("apps", {}),
        "folders": data.get("folders", {}),
    }


# --- TTS ------------------------------------------------------------------
# "pyttsx3" (offline, default) or "elevenlabs" (requires ELEVENLABS_API_KEY)
TTS_ENGINE = os.getenv("TTS_ENGINE", "elevenlabs" if ELEVENLABS_API_KEY else "pyttsx3")
ELEVENLABS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "Rachel")
PYTTSX3_RATE = int(os.getenv("PYTTSX3_RATE", "175"))


def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(message)s",
        datefmt="%H:%M:%S",
    )
    # Quiet down noisy third-party loggers
    for noisy in ("faster_whisper", "openwakeword", "urllib3", "httpx"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
