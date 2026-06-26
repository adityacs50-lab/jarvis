"""Jarvis — Phase 1 voice loop.

Flow:  wake word -> record -> transcribe -> Claude -> speak -> repeat.
"""
import logging
import sys

import config
from llm import Brain
from recorder import Recorder
from stt import Transcriber
from tts import create_tts
from wake_word import WakeWordDetector

log = logging.getLogger("jarvis")


def main():
    config.setup_logging()
    log.info("=" * 50)
    log.info(" JARVIS voice assistant — Phase 1")
    log.info("=" * 50)

    # Initialize components (loads models, validates API key).
    try:
        detector = WakeWordDetector()
        recorder = Recorder()
        transcriber = Transcriber()
        brain = Brain()
        tts = create_tts()
    except Exception as e:
        log.error("Startup failed: %s", e)
        sys.exit(1)

    log.info("✅ Ready. Say '%s' to begin.", config.WAKE_WORD)

    while True:
        try:
            # 1. Wait for wake word
            detector.wait_for_wake_word()

            # 2. Record until the user stops talking
            audio = recorder.record()
            if audio is None:
                continue

            # 3. Transcribe
            text = transcriber.transcribe(audio)
            if not text:
                continue

            # 4. Ask Claude
            reply = brain.ask(text)
            if not reply:
                continue

            # 5. Speak the response, then loop back to listening
            tts.speak(reply)

        except KeyboardInterrupt:
            log.info("\n👋 Shutting down. Goodbye.")
            break
        except Exception as e:
            log.error("Error in loop: %s", e, exc_info=True)
            # Keep the assistant alive on transient errors.
            continue


if __name__ == "__main__":
    main()
