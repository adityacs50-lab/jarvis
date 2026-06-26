"""Jarvis — Phase 1 voice loop.

Flow:  wake word -> record -> transcribe -> Claude -> speak -> repeat.
"""
import logging
import sys

import config
from intent_router import IntentRouter
from recorder import Recorder
from skills.spotify_skill import SpotifySkill
from stt import Transcriber
from tts import create_tts
from wake_word import WakeWordDetector

log = logging.getLogger("jarvis")


def main():
    config.setup_logging()
    log.info("=" * 50)
    log.info(" JARVIS voice assistant — Phase 2 (Spotify)")
    log.info("=" * 50)

    # Initialize components (loads models, validates API key).
    try:
        detector = WakeWordDetector()
        recorder = Recorder()
        transcriber = Transcriber()
        tts = create_tts()

        # Spotify is optional — if it isn't configured, run chat-only.
        try:
            spotify = SpotifySkill()
        except Exception as e:
            log.warning("Spotify disabled: %s", e)
            spotify = None

        router = IntentRouter(spotify_skill=spotify)
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

            # 4. Route intent (music control vs. general chat) and act
            reply = router.handle(text)
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
