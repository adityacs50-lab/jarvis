"""Text-to-speech. Default offline engine is pyttsx3; ElevenLabs optional."""
import logging

import config

log = logging.getLogger("jarvis.tts")


def create_tts():
    """Factory: returns a TTS engine based on config."""
    if config.TTS_ENGINE == "elevenlabs" and config.ELEVENLABS_API_KEY:
        try:
            return ElevenLabsTTS()
        except Exception as e:  # pragma: no cover
            log.warning("ElevenLabs init failed (%s); falling back to pyttsx3.", e)
    return Pyttsx3TTS()


class Pyttsx3TTS:
    """Offline TTS — works out of the box, no API key."""

    def __init__(self):
        import pyttsx3

        self.engine = pyttsx3.init()
        self.engine.setProperty("rate", config.PYTTSX3_RATE)
        log.info("TTS engine: pyttsx3 (offline)")

    def speak(self, text):
        log.info("🔊 Speaking...")
        self.engine.say(text)
        self.engine.runAndWait()


class ElevenLabsTTS:
    """Higher-quality cloud TTS via ElevenLabs."""

    def __init__(self):
        from elevenlabs.client import ElevenLabs

        self.client = ElevenLabs(api_key=config.ELEVENLABS_API_KEY)
        self.voice_id = config.ELEVENLABS_VOICE_ID
        log.info("TTS engine: ElevenLabs (voice=%s)", self.voice_id)

    def speak(self, text):
        from elevenlabs import play

        log.info("🔊 Speaking...")
        audio = self.client.text_to_speech.convert(
            voice_id=self.voice_id,
            model_id="eleven_turbo_v2_5",
            text=text,
        )
        play(audio)
