"""Layer 1 — TTS. Run on your machine (needs audio output).

    python tests/test_1_tts.py

Confirms your TTS engine (pyttsx3 by default, or ElevenLabs if configured)
actually produces sound before testing anything else.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config  # noqa: E402
from tts import create_tts  # noqa: E402


def main():
    config.setup_logging()
    print(f"TTS_ENGINE = {config.TTS_ENGINE}")
    tts = create_tts()
    line = "Testing, one two three. If you can hear this, text to speech works."
    print(f"Speaking: {line!r}")
    tts.speak(line)
    print("Done. Did you hear it? If silent on Linux, install espeak.")


if __name__ == "__main__":
    main()
