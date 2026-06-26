# Jarvis — Voice Assistant (Phase 2)

A JARVIS-style, always-listening voice assistant that runs as a background
script. Say the wake word, ask a question, and Jarvis answers out loud with a
witty, concise personality powered by Claude.

**Phase 2** adds a **Spotify control skill**: an intent-routing step decides
whether each request is *music control* or *general chat*. Music requests are
parsed into structured actions via Claude's tool use and executed through the
Spotify Web API.

```
wake word ("jarvis")  →  record (until you stop talking)  →  transcribe
        ↑                                                          ↓
        |                                              intent router (Claude)
        |                                            ┌──────────┴──────────┐
        |                                       music_control        general_chat
        |                                            ↓                     ↓
      speak  ←  text-to-speech  ←──────────  Spotify skill    /    Claude reply
```

## How it works

| Stage            | Library                              |
| ---------------- | ------------------------------------ |
| Wake word        | [openWakeWord](https://github.com/dscripka/openWakeWord) (`hey_jarvis` model) |
| Silence / VAD    | [webrtcvad](https://github.com/wiseman/py-webrtcvad) |
| Speech-to-text   | [faster-whisper](https://github.com/SYSTRAN/faster-whisper) (`base`, int8, CPU) |
| Intent + reasoning | Anthropic Claude (`claude-sonnet-4-6`) with **tool use** |
| Music control    | [Spotipy](https://spotipy.readthedocs.io/) (Spotify Web API) |
| Text-to-speech   | [pyttsx3](https://github.com/nateshmbhat/pyttsx3) (offline, default) or [ElevenLabs](https://elevenlabs.io/) (optional) |

### Music commands (natural language — no exact phrasing required)

- **Play** — "play Bohemian Rhapsody", "play some Arctic Monkeys", "put on Abbey Road"
- **Pause / resume** — "pause", "stop the music", "resume", "keep playing"
- **Skip** — "next track", "skip this", "go back", "previous song"
- **Volume** — "set volume to 40", "turn it up", "make it quieter"
- **Now playing** — "what's playing?", "what song is this?"

Anything that isn't music control is answered conversationally as before.

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

### 4. Spotify setup (Phase 2 — required for music control)

Music control talks to the Spotify Web API, which needs your own Spotify
**Developer app** credentials. A **Spotify Premium** account is required —
Spotify's API does not allow playback control on free accounts.

1. Go to the **Spotify Developer Dashboard**:
   <https://developer.spotify.com/dashboard> and log in.
2. Click **Create app**. Give it any name/description (e.g. "Jarvis").
3. In the app settings, add this **Redirect URI** exactly and save:
   ```
   http://127.0.0.1:8888/callback
   ```
   > It must match `SPOTIPY_REDIRECT_URI` in your `.env` character-for-character.
   > (Spotify no longer accepts `localhost`; use `127.0.0.1`.)
4. Under **APIs used**, select **Web API**.
5. Copy the **Client ID** and **Client Secret** from the app's settings page
   into your `.env`:
   ```
   SPOTIPY_CLIENT_ID=your_client_id
   SPOTIPY_CLIENT_SECRET=your_client_secret
   SPOTIPY_REDIRECT_URI=http://127.0.0.1:8888/callback
   ```
6. **First run authorization:** the first time you issue a music command,
   Spotipy opens a browser window asking you to authorize the app. Approve it;
   you'll be redirected to the `127.0.0.1:8888/callback` URL. The token is
   cached in `.spotify_cache` so you only do this once.

> **Important:** Spotify can only control playback on an *active device*. Open
> the Spotify app on your phone, desktop, or web player and start playing
> something (or just have it open) so Jarvis has a device to control. If there's
> no active device, Jarvis will say so out loud instead of crashing.

If you skip Spotify setup, Jarvis still runs — it just falls back to chat-only
mode and tells you music control is unavailable.

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
🗣️  Heard: play some Arctic Monkeys
🧭 Routing intent...
🎵 [music_control] {'action': 'play', 'query': 'Arctic Monkeys'}
💬 [music] Jarvis: Playing Do I Wanna Know? by Arctic Monkeys.
🔊 Speaking...
```

A general-chat turn looks like:

```
🗣️  Heard: what's the capital of France
🧭 Routing intent...
💬 [chat] Jarvis: Paris. Shall I book you a flight?
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
config.py               # settings + logging
wake_word.py            # openWakeWord detection
recorder.py             # VAD-based recording until silence
stt.py                  # faster-whisper transcription
intent_router.py        # Claude tool-use: music_control vs. general_chat
skills/
  spotify_skill.py      # Spotipy playback control + music_control tool schema
llm.py                  # standalone Claude chat helper (Phase 1; superseded by the router)
tts.py                  # pyttsx3 / ElevenLabs speech output
main.py                 # the loop that ties it all together
```

### Intent routing

`intent_router.py` makes a single Claude call per utterance, passing the
`music_control` tool definition. Claude decides whether to **call the tool**
(returning a structured `{action, query, volume_level, ...}` payload that we
dispatch to `SpotifySkill`) or to **reply in plain text** (general chat). This
uses Claude's native tool use / function calling for intent classification and
parameter extraction — no manual keyword parsing. Short conversation history is
retained so follow-ups ("play it again", "now what's playing?") keep context.

## Troubleshooting

- **No audio / device errors:** make sure `portaudio` is installed and your OS
  has microphone permission for the terminal. List devices with
  `python -c "import sounddevice; print(sounddevice.query_devices())"`.
- **Wake word never triggers:** lower `WAKE_THRESHOLD` (e.g. `0.4`). The
  bundled model responds to "hey jarvis" / "jarvis".
- **pyttsx3 silent on Linux:** install `espeak`.
- **Transcription too slow:** use `WHISPER_MODEL=tiny`.
- **"No active Spotify device":** open Spotify somewhere (phone/desktop/web) and
  press play once so it registers as the active device, then try again.
- **Spotify 403 / "denied":** playback control requires a **Premium** account.
- **Spotify re-auth loop / wrong redirect:** make sure the Redirect URI in the
  Spotify dashboard exactly matches `SPOTIPY_REDIRECT_URI`. Delete the
  `.spotify_cache` file to force re-authorization.

## Roadmap (next phases)

- More skills (timers, reminders, web search, smart home)
- GUI / system tray app
- Interruptible / streaming responses
