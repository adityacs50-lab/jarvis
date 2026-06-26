"""Record speech from the mic until the user stops talking (VAD-based)."""
import collections
import logging

import numpy as np
import sounddevice as sd
import webrtcvad

import config

log = logging.getLogger("jarvis.rec")


class Recorder:
    def __init__(self):
        self.vad = webrtcvad.Vad(config.VAD_AGGRESSIVENESS)
        self.frame_samples = int(config.SAMPLE_RATE * config.FRAME_MS / 1000)
        self.silence_frames = config.SILENCE_TIMEOUT_MS // config.FRAME_MS
        self.max_frames = int(config.MAX_RECORD_SECONDS * 1000 / config.FRAME_MS)
        self.min_speech_frames = config.MIN_SPEECH_MS // config.FRAME_MS

    def record(self):
        """Record until silence is detected. Returns int16 numpy array (or None)."""
        log.info("🔴 Recording... (speak now)")
        collected = []
        # Small ring buffer so we keep a bit of audio before speech starts.
        ring = collections.deque(maxlen=5)
        triggered = False
        num_silent = 0
        speech_frames = 0

        with sd.InputStream(
            samplerate=config.SAMPLE_RATE,
            channels=config.CHANNELS,
            dtype="int16",
            blocksize=self.frame_samples,
        ) as stream:
            for _ in range(self.max_frames):
                audio, _ = stream.read(self.frame_samples)
                frame = np.frombuffer(audio, dtype=np.int16)
                is_speech = self.vad.is_speech(frame.tobytes(), config.SAMPLE_RATE)

                if not triggered:
                    ring.append(frame)
                    if is_speech:
                        triggered = True
                        collected.extend(ring)
                        ring.clear()
                else:
                    collected.append(frame)
                    if is_speech:
                        speech_frames += 1
                        num_silent = 0
                    else:
                        num_silent += 1
                        if num_silent >= self.silence_frames:
                            break

        if not collected or speech_frames < self.min_speech_frames:
            log.info("🤫 No speech detected.")
            return None

        return np.concatenate(collected)
