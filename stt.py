"""Speech-to-text using faster-whisper (fast CPU transcription)."""
import logging

import numpy as np

import config

log = logging.getLogger("jarvis.stt")


class Transcriber:
    def __init__(self):
        from faster_whisper import WhisperModel

        log.info("Loading Whisper model '%s'...", config.WHISPER_MODEL)
        self.model = WhisperModel(
            config.WHISPER_MODEL,
            device=config.WHISPER_DEVICE,
            compute_type=config.WHISPER_COMPUTE_TYPE,
        )

    def transcribe(self, audio_int16):
        """Transcribe an int16 numpy array. Returns the recognized text."""
        log.info("📝 Transcribing...")
        # faster-whisper wants float32 in [-1, 1].
        audio = audio_int16.astype(np.float32) / 32768.0
        segments, _ = self.model.transcribe(audio, language="en", beam_size=1)
        text = " ".join(seg.text for seg in segments).strip()
        log.info("🗣️  Heard: %s", text or "(nothing)")
        return text
