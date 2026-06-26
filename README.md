# Jarvis — Voice Assistant (Phase 1)

A JARVIS-style, always-listening voice assistant that runs as a background
script. Say the wake word, ask a question, and Jarvis answers out loud with a
witty, concise personality powered by Claude.

This is **Phase 1**: the core voice loop only — no smart actions / tool use yet.

```
wake word ("jarvis")  →  record (until you stop talking)  →  transcribe
        ↑                                                          ↓
      speak  ←  text-to-speech  ←  Claude (claude-sonnet-4-6)  ←  text
```

## How it works

| Stage            | Library                              |
| ---------------- | ------------------------------------ |
| Wake word        | [openWakeWord](https://github.com/dscripka/openWakeWord) (`hey_jarvis` model) |
| Silence / VAD    | [webrtcvad](https://github.com/wiseman/py-webrtcvad) |
| Speech-to-text   | [faster-whisper](https://github.com/SYSTRAN/faster-whisper) (`base`, int8, CPU) |
| Reasoning        | Anthropic Claude (`claude-sonnet-4-6`) |
| Text-to-speech   | [pyttsx3](https://github.com/nateshmbhat/pyttsx3) (offline, default) or [ElevenLabs](https://elevenlabs.io/) (optional) |

`faster-whisper` is used instead of vanilla `openai-whisper` because it is
several times faster on a normal laptop CPU, which matters for a real-time
voice loop.

## Setup

### 1. System dependencies

You need a working microphone plus a few system libraries used by the audio
and TTS stack.

**macOS:**
```bash
brew install portaudio espeak
```

**Debian / Ubuntu:**
```bash
sudo apt-get update
sudo apt-get install -y portaudio19-dev python3-pyaudio espeak ffmpeg libsndfile1
```

> `espeak` is the offline voice backend for pyttsx3 on Linux. `portaudio` is
> required by `sounddevice`. `ffmpeg` helps with audio decoding.

### 2. Python dependencies

Use Python 3.9–3.11 (recommended).

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

The first run downloads the Whisper model (~140 MB for `base`) and the
openWakeWord models automatically.

### 3. API keys

Copy the example env file and fill in your keys:

```bash
cp .env.example .env
```

- **Anthropic API key (required):** create one at
  <https://console.anthropic.com/> → *API Keys*. Put it in `.env` as
  `ANTHROPIC_API_KEY`.
- **ElevenLabs API key (optional):** sign up at <https://elevenlabs.io/>,
  then *Profile → API Key*. Set `ELEVENLABS_API_KEY` to use higher-quality
  cloud voices. If omitted, Jarvis uses the offline `pyttsx3` voice so it
  works out of the box.

## Run

```bash
python main.py
```

You'll see state logging in the console:

```
🎧 Listening for wake word ('jarvis')...
✨ Wake word detected (hey_jarvis: 0.87)
🔴 Recording... (speak now)
📝 Transcribing...
🗣️  Heard: what's the capital of France
🤔 Thinking...
💬 Jarvis: Paris. Shall I book you a flight?
🔊 Speaking...
```

Say **"jarvis"**, wait for the recording prompt, ask your question, and Jarvis
replies aloud — then it loops back to listening. Press `Ctrl+C` to quit.

## Configuration

All knobs live in `config.py` and can be overridden via environment variables
in `.env`. Useful ones:

| Variable             | Default            | Notes                                   |
| -------------------- | ------------------ | --------------------------------------- |
| `WHISPER_MODEL`      | `base`             | `tiny`/`base`/`small`/`medium` — bigger = more accurate, slower |
| `WAKE_THRESHOLD`     | `0.5`              | Lower = more sensitive wake word        |
| `VAD_AGGRESSIVENESS` | `2`                | 0 (lenient) … 3 (strict) silence detection |
| `SILENCE_TIMEOUT_MS` | `800`              | How long of a pause ends your recording |
| `CLAUDE_MODEL`       | `claude-sonnet-4-6`| LLM model                               |
| `TTS_ENGINE`         | auto               | `pyttsx3` or `elevenlabs`               |

## Project structure

```
config.py      # settings + logging
wake_word.py   # openWakeWord detection
recorder.py    # VAD-based recording until silence
stt.py         # faster-whisper transcription
llm.py         # Claude API call + short conversation memory
tts.py         # pyttsx3 / ElevenLabs speech output
main.py        # the loop that ties it all together
```

## Troubleshooting

- **No audio / device errors:** make sure `portaudio` is installed and your OS
  has microphone permission for the terminal. List devices with
  `python -c "import sounddevice; print(sounddevice.query_devices())"`.
- **Wake word never triggers:** lower `WAKE_THRESHOLD` (e.g. `0.4`). The
  bundled model responds to "hey jarvis" / "jarvis".
- **pyttsx3 silent on Linux:** install `espeak`.
- **Transcription too slow:** use `WHISPER_MODEL=tiny`.

## Roadmap (next phases)

- Smart actions / tool use (timers, web search, smart home, etc.)
- GUI / system tray app
- Interruptible / streaming responses
