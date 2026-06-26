"""Wake word detection using openWakeWord.

Listens on the microphone for the wake word ("jarvis" by default) and blocks
until it is detected.
"""
import logging

import numpy as np
import sounddevice as sd

import config

log = logging.getLogger("jarvis.wake")

# openWakeWord ships pretrained models. "hey_jarvis" is the closest bundled
# model to the requested "jarvis" wake word.
_DEFAULT_MODEL = "hey_jarvis"


class WakeWordDetector:
    def __init__(self):
        from openwakeword.model import Model
        from openwakeword.utils import download_models

        # Ensure the pretrained models are present (no-op if already cached).
        try:
            download_models()
        except Exception as e:  # pragma: no cover - network/cache issues
            log.warning("Could not download openWakeWord models: %s", e)

        self.model = Model(wakeword_models=[_DEFAULT_MODEL])
        self.threshold = config.WAKE_THRESHOLD
        # openWakeWord expects 16 kHz int16 audio, 80 ms (1280 sample) chunks.
        self.chunk = 1280

    def wait_for_wake_word(self):
        """Block until the wake word is detected."""
        log.info("🎧 Listening for wake word ('%s')...", config.WAKE_WORD)
        self.model.reset()

        with sd.InputStream(
            samplerate=config.SAMPLE_RATE,
            channels=config.CHANNELS,
            dtype="int16",
            blocksize=self.chunk,
        ) as stream:
            while True:
                audio, _ = stream.read(self.chunk)
                samples = np.frombuffer(audio, dtype=np.int16)
                scores = self.model.predict(samples)
                for name, score in scores.items():
                    if score >= self.threshold:
                        log.info("✨ Wake word detected (%s: %.2f)", name, score)
                        return
