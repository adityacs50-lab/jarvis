"""Jarvis — voice loop.

Flow:  wake word -> record -> transcribe -> route intent -> act -> speak.
"""
import logging
import sys

import config
from intent_router import IntentRouter
from recorder import Recorder
from skills.spotify_skill import SpotifySkill
from skills.system_skill import SystemSkill
from stt import Transcriber
from tts import create_tts
from wake_word import WakeWordDetector

log = logging.getLogger("jarvis")


def main():
    config.setup_logging()
    log.info("=" * 50)
    log.info(" JARVIS voice assistant — Phase 3 (Spotify + system control)")
    log.info("=" * 50)

    # Initialize components (loads models, validates API key).
    try:
        detector = WakeWordDetector()
        recorder = Recorder()
        transcriber = Transcriber()
        tts = create_tts()

        # Spotify is optional — if it isn't configured, run without music.
        try:
            spotify = SpotifySkill()
        except Exception as e:
            log.warning("Spotify disabled: %s", e)
            spotify = None

        # System control is always available, but never let it block startup.
        try:
            system = SystemSkill()
        except Exception as e:
            log.warning("System control disabled: %s", e)
            system = None

        router = IntentRouter(spotify_skill=spotify, system_skill=system)
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

            # 4. Route intent (music / system / chat) and act
            result = router.handle(text)
            if result and result.speech:
                tts.speak(result.speech)

            # 5. If a destructive action needs confirmation, listen for yes/no
            #    right away (no wake word needed) before doing anything.
            while result and result.needs_confirmation:
                ans_audio = recorder.record()
                if ans_audio is None:
                    result = router.cancel_pending()
                else:
                    ans_text = transcriber.transcribe(ans_audio)
                    result = router.confirm(ans_text)
                if result and result.speech:
                    tts.speak(result.speech)

        except KeyboardInterrupt:
            log.info("\n👋 Shutting down. Goodbye.")
            break
        except Exception as e:
            log.error("Error in loop: %s", e, exc_info=True)
            # Keep the assistant alive on transient errors.
            continue


if __name__ == "__main__":
    main()
