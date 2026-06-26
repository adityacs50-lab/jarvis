"""Central configuration and logging setup for Jarvis."""
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
SYSTEM_PROMPT = (
    "You are Jarvis, a helpful voice assistant with a witty, concise personality. "
    "Your responses are spoken aloud, so keep them SHORT — typically one or two "
    "sentences, never long paragraphs. Be direct, a little clever, and never "
    "ramble. Skip markdown, bullet points, and emoji since they can't be spoken."
)

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
