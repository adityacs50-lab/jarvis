"""Layer 4 — core loop end to end (Phase 1), NO skills. Run on your machine.

    python tests/test_4_chat_loop.py

wake word -> STT -> Claude (plain chat) -> TTS, with every skill disabled so
nothing can misroute. Say "Jarvis", then "what's two plus two". If this is
clean, your foundation is solid. Needs mic, audio out, and ANTHROPIC_API_KEY.
Ctrl+C to quit.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config  # noqa: E402
from intent_router import IntentRouter  # noqa: E402
from recorder import Recorder  # noqa: E402
from stt import Transcriber  # noqa: E402
from tts import create_tts  # noqa: E402
from wake_word import WakeWordDetector  # noqa: E402


def main():
    config.setup_logging()
    detector = WakeWordDetector()
    recorder = Recorder()
    transcriber = Transcriber()
    tts = create_tts()
    # No skills, no memory -> router can only do general_chat.
    router = IntentRouter()

    print("Plain-chat loop ready. Say the wake word. Ctrl+C to quit.\n")
    try:
        while True:
            detector.wait_for_wake_word()
            audio = recorder.record()
            if audio is None:
                continue
            text = transcriber.transcribe(audio)
            if not text:
                continue
            result = router.handle(text)
            if result and result.speech:
                tts.speak(result.speech)
    except KeyboardInterrupt:
        print("\nDone.")


if __name__ == "__main__":
    main()
