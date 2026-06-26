"""Layer 2 — STT. Run on your machine.

    python tests/test_2_stt.py path/to/clip.wav      # transcribe a file
    python tests/test_2_stt.py --mic                 # record 5s from mic, then transcribe

Isolates faster-whisper from live mic/VAD complexity. Record a short clip on
your phone (say "what's two plus two") or use --mic.
"""
import sys
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np  # noqa: E402

import config  # noqa: E402
from stt import Transcriber  # noqa: E402


def load_wav(path):
    with wave.open(path, "rb") as w:
        if w.getframerate() != config.SAMPLE_RATE or w.getnchannels() != 1:
            print(f"WARNING: expected mono {config.SAMPLE_RATE} Hz; got "
                  f"{w.getnchannels()}ch {w.getframerate()} Hz. "
                  "Transcription may be poor — re-export as 16 kHz mono.")
        frames = w.readframes(w.getnframes())
    return np.frombuffer(frames, dtype=np.int16)


def record_mic(seconds=5):
    import sounddevice as sd
    print(f"Recording {seconds}s from mic... speak now.")
    audio = sd.rec(int(seconds * config.SAMPLE_RATE),
                   samplerate=config.SAMPLE_RATE, channels=1, dtype="int16")
    sd.wait()
    return audio.flatten()


def main():
    config.setup_logging()
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    audio = record_mic() if sys.argv[1] == "--mic" else load_wav(sys.argv[1])
    transcriber = Transcriber()
    text = transcriber.transcribe(audio)
    print("\n=== TRANSCRIPTION ===")
    print(repr(text))


if __name__ == "__main__":
    main()
