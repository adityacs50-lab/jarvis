# Testing Jarvis (bottom-up)

Test one layer at a time, in order. When something breaks you'll know exactly
which layer it is instead of guessing across all phases.

First, on your machine: `pip install -r ../requirements.txt`, system deps
(portaudio, espeak, ffmpeg — see main README), and a `.env` with
`ANTHROPIC_API_KEY`.

| # | Layer | Command | Needs |
|---|-------|---------|-------|
| 1 | **TTS** (output only) | `python tests/test_1_tts.py` | audio out |
| 2 | **STT** (no mic/VAD yet) | `python tests/test_2_stt.py clip.wav` or `--mic` | (mic if `--mic`) |
| 3 | **Wake + VAD + record** | `python tests/test_3_listen.py` | mic |
| 4 | **Core loop, no skills** | `python tests/test_4_chat_loop.py` | mic, audio, API key |
| 5 | **Router intents** (text in) | `python tests/test_5_router_live.py` | API key |
| 6 | **Each skill, by voice** | `python ../main.py` | everything |

Tips:
- **Layer 2:** record a 16 kHz mono WAV ("what's two plus two"). Wrong
  sample rate just warns and still tries.
- **Layer 3:** the usual trouble spot. Tune `WAKE_THRESHOLD` (lower = more
  sensitive), `VAD_AGGRESSIVENESS` (0–3), `SILENCE_TIMEOUT_MS` in `.env`.
- **Layer 5:** skills are stubbed so you see the *route*, not side effects.
  A "FAIL" may just be a reasonable alternative read — eyeball the misses.
- **Layer 6:** test skills individually — Spotify → system → web → code →
  study → memory — before assuming combinations work.

## Offline tests (no mic / audio / API key — CI-friendly)

These run anywhere and validate the logic *around* the audio/LLM:

```bash
python tests/test_router_wiring.py   # dispatch for every intent, with a faked Claude
python tests/test_memory.py          # SQLite logging / recall / clear
```

`test_router_wiring.py` fakes the Anthropic client so it can assert that each
intent dispatches to the right skill, study mode hides the code tool, the
confirmation flow gates deletes and memory-wipe, and exchanges get logged —
*without* a key. It does **not** test Claude's intent judgment; that's what the
live layer-5 test is for.
