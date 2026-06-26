"""Layer 3 — wake word + VAD + recording. Run on your machine (needs mic).

    python tests/test_3_listen.py

The trickiest layer. This runs the real wake-word -> record -> transcribe
pipeline but STOPS before the LLM — it just prints what it heard. Say "Jarvis"
several times and confirm it triggers reliably and doesn't cut you off.
Ctrl+C to quit.

Tuning knobs (set in .env): WAKE_THRESHOLD (lower = more sensitive),
VAD_AGGRESSIVENESS (0-3), SILENCE_TIMEOUT_MS (pause length that ends recording).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config  # noqa: E402
from recorder import Recorder  # noqa: E402
from stt import Transcriber  # noqa: E402
from wake_word import WakeWordDetector  # noqa: E402


def main():
    config.setup_logging()
    detector = WakeWordDetector()
    recorder = Recorder()
    transcriber = Transcriber()
    print("Listening. Say the wake word, then a sentence. Ctrl+C to quit.\n")
    try:
        while True:
            detector.wait_for_wake_word()
            audio = recorder.record()
            if audio is None:
                print("  (no speech captured — try speaking sooner/louder)\n")
                continue
            text = transcriber.transcribe(audio)
            print(f"  >>> HEARD: {text!r}\n")
    except KeyboardInterrupt:
        print("\nDone.")


if __name__ == "__main__":
    main()
