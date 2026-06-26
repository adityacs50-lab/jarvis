# Jarvis — Voice Assistant (Phase 4)

A JARVIS-style, always-listening voice assistant that runs as a background
script. Say the wake word, ask a question, and Jarvis answers out loud with a
witty, concise personality powered by Claude.

An intent-routing step classifies every request into one of four categories
and dispatches it to the right skill:

- **`music_control`** → Spotify (Phase 2)
- **`system_control`** → open apps, open websites/search, basic file ops (Phase 3)
- **`web_lookup`** → live internet search via Claude's built-in web search (Phase 4)
- **`general_chat`** → a normal spoken Claude reply

Intent classification and parameter extraction both happen in a single Claude
call using native tool use — no keyword matching. The router is deliberately
biased toward `web_lookup`: unless it's confident the answer is timeless, it
searches the web rather than risk answering with stale info.

```
wake word ("jarvis")  →  record (until you stop talking)  →  transcribe
        ↑                                                          ↓
        |                                              intent router (Claude)
        |                ┌───────────────────┬───────────────────┬───────────────────┐
        |          music_control       system_control        web_lookup         general_chat
        |                ↓                   ↓                    ↓                   ↓
      speak ← TTS ← Spotify skill  /   System skill   /   Web search (Claude)  /  Claude reply
```

## How it works

| Stage            | Library                              |
| ---------------- | ------------------------------------ |
| Wake word        | [openWakeWord](https://github.com/dscripka/openWakeWord) (`hey_jarvis` model) |
| Silence / VAD    | [webrtcvad](https://github.com/wiseman/py-webrtcvad) |
| Speech-to-text   | [faster-whisper](https://github.com/SYSTRAN/faster-whisper) (`base`, int8, CPU) |
| Intent + reasoning | Anthropic Claude (`claude-sonnet-4-6`) with **tool use** |
| Music control    | [Spotipy](https://spotipy.readthedocs.io/) (Spotify Web API) |
| System control   | Python stdlib (`os`, `subprocess`, `webbrowser`) |
| Web lookup       | Claude built-in **web search** tool (`web_search_20250305`) |
| Text-to-speech   | [pyttsx3](https://github.com/nateshmbhat/pyttsx3) (offline, default) or [ElevenLabs](https://elevenlabs.io/) (optional) |

### Music commands (natural language — no exact phrasing required)

- **Play** — "play Bohemian Rhapsody", "play some Arctic Monkeys", "put on Abbey Road"
- **Pause / resume** — "pause", "stop the music", "resume", "keep playing"
- **Skip** — "next track", "skip this", "go back", "previous song"
- **Volume** — "set volume to 40", "turn it up", "make it quieter"
- **Now playing** — "what's playing?", "what song is this?"

### System commands (Phase 3)

- **Open an app** — "open Chrome", "open VS Code", "launch Notepad"
  (resolved via your `system_config.json` app map)
- **Open a website** — "open youtube.com", "go to github.com"
- **Web search** — "search Google for lasagna recipes"
- **List a folder** — "list files in Downloads", "what's in my Documents folder"
- **Create a folder** — "make a folder called notes on my desktop"
- **Open a file** — "open report.txt"
- **Delete a file/folder** — "delete old.txt" → **requires spoken confirmation**
  (Jarvis asks "Are you sure…? Say yes to confirm" and does nothing unless you say yes)

### Web lookup commands (Phase 4)

Jarvis searches the live web (via Claude's built-in web search) for anything
current or factual, and speaks a short 1-3 sentence answer — no citations read
aloud. It leans toward searching whenever an answer might depend on current info:

- **Weather** — "what's the weather in Tokyo right now?"
- **News** — "what's the latest on the election?"
- **Scores / results** — "did the Lakers win last night?"
- **Prices** — "how much is the new iPhone?", "what's Bitcoin at?"
- **Current X** — "who's the current CEO of OpenAI?", "what's the newest Pixel?"
- **Anything 'now/today/latest'** — and any named person, product, or event it
  isn't sure is static.

Timeless stuff (math, definitions, coding help, jokes, casual chat, concept
explanations) is answered directly without a search. If a search turns up
nothing useful, Jarvis just says it couldn't find anything solid rather than
guessing.

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

### 5. System control setup (Phase 3 — app & folder mapping)

App launching is OS-specific, so the nickname → executable mapping lives in a
plain JSON file, **`system_config.json`**, that you edit by hand. No code
changes needed. The defaults assume **Windows**.

```jsonc
{
  "apps": {
    "notepad": "notepad",                       // bare command on PATH
    "chrome":  "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
    "vs code": "C:\\Users\\YOUR_USERNAME\\AppData\\Local\\Programs\\Microsoft VS Code\\Code.exe"
  },
  "folders": {
    "downloads": "C:\\Users\\YOUR_USERNAME\\Downloads",
    "desktop":   "C:\\Users\\YOUR_USERNAME\\Desktop"
  }
}
```

- **`apps`** — keys are spoken nicknames (matched case-insensitively and
  loosely, so `"vs code"` matches "open VS Code"). Values are either a bare
  command found on `PATH` (e.g. `notepad`, `calc`, `msedge`) or a full path to
  an `.exe`. **Replace `YOUR_USERNAME`** and fix any install paths for your
  machine. If a spoken app isn't in the map, Jarvis tries it as a bare command
  and, failing that, tells you to add it to `system_config.json`.
- **`folders`** — optional shortcuts so you can say "list files in Downloads"
  instead of a full path. File commands also accept literal paths and expand
  `~` / environment variables.

> **Cross-platform note:** the launcher in `skills/system_skill.py` already
> branches on OS (`os.startfile` on Windows, `open` on macOS, direct exec on
> Linux). To target Mac/Linux, just put the right commands/paths in
> `system_config.json` — e.g. `"chrome": "google-chrome"` on Linux.

> **Safety:** deleting a file or folder always triggers a spoken confirmation
> ("Are you sure you want to delete X? Say yes to confirm"). Jarvis listens for
> your yes/no answer immediately (no wake word needed) and does **nothing**
> unless you clearly confirm. Anything else cancels.

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

A system-control turn with a destructive action looks like:

```
🗣️  Heard: delete the folder old reports
🧭 Routing intent...
🖥️  system_control {'action': 'delete_path', 'path': 'old reports'}
⚠️  Awaiting confirmation: Are you sure you want to delete the folder old reports? Say yes to confirm.
🔊 Speaking...
🔴 Recording... (speak now)
🗣️  Heard: yes
✅ Confirmation received — executing.
🔊 Speaking...   # "Deleted the folder old reports."
```

A web-lookup turn looks like:

```
🗣️  Heard: what's the weather in London right now
🧭 Routing intent...
🌐 web_lookup {'query': 'current weather in London'}
🌐 Searching the web for: current weather in London
💬 Jarvis: It's about 14 degrees and overcast in London right now, with light rain expected later.
🔊 Speaking...
```

A general-chat turn (no search) looks like:

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
| `SYSTEM_CONFIG_PATH` | `system_config.json` | App/folder mapping for system control |

## Project structure

```
config.py               # settings + logging + system_config.json loader
wake_word.py            # openWakeWord detection
recorder.py             # VAD-based recording until silence
stt.py                  # faster-whisper transcription
intent_router.py        # Claude tool-use: music / system / web_lookup / general_chat
skills/
  base.py               # SkillResult (incl. pending/confirmation contract)
  spotify_skill.py      # Spotipy playback control + music_control tool schema
  system_skill.py       # apps / websites / file ops + system_control tool schema
  web_skill.py          # live web search via Claude web_search + web_lookup tool schema
system_config.json      # editable app nickname -> path + folder shortcuts
llm.py                  # standalone Claude chat helper (Phase 1; superseded by the router)
tts.py                  # pyttsx3 / ElevenLabs speech output
main.py                 # the loop that ties it all together (incl. confirmation step)
```

### Intent routing

`intent_router.py` makes a single Claude call per utterance, passing the
`music_control`, `system_control`, and `web_lookup` tool definitions. Claude
either **calls a tool** (returning a structured payload we dispatch to
`SpotifySkill`, `SystemSkill`, or `WebSkill`) or **replies in plain text**
(general chat). This uses Claude's native tool use / function calling for intent
classification *and* parameter extraction — no manual keyword parsing. Short
conversation history is retained so follow-ups ("play it again", "now what's
playing?") keep context.

**Web-search bias:** the routing call appends `config.ROUTING_GUIDANCE`, which
instructs Claude to default to `web_lookup` whenever it isn't highly confident
the answer is timeless. False positives (searching unnecessarily) are cheap;
false negatives (answering stale info) are not. `web_lookup` dispatches to
`WebSkill`, which makes a second Claude call with the hosted
`web_search_20250305` tool enabled so Claude searches and synthesizes a short
spoken answer. Clear music/system requests still route to their own skills.

**Confirmation contract:** skills return a `SkillResult`. For destructive
operations the result carries a `pending` callable instead of executing
immediately; the router speaks the confirmation prompt, enters an
"awaiting confirmation" state, and only runs `pending()` if your next spoken
answer is affirmative. This keeps the dangerous-action gate in one place and
makes it reusable by future skills.

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
- **"I don't have <app> configured":** add the app (nickname → path) to
  `system_config.json`. Remember to replace `YOUR_USERNAME` in the defaults.
- **App opens the wrong thing / not found:** the value must be a real command on
  `PATH` or a valid full path. Test it in a terminal first (e.g. `where chrome`).
- **File command can't find a folder:** use a `folders` shortcut, a full path,
  or `~`/env vars — relative names only work if they're configured.

## Limitations

Jarvis uses **live web search**, so it's far more current than a normal chatbot
— it can pull today's weather, prices, scores, and news. But it is **not
omniscient**, and it can still get things wrong:

- **Breaking news may lag.** Minutes-old developments might not be indexed yet,
  so very fresh stories can be incomplete or slightly behind.
- **No access to private/personal data.** It can't see your accounts, files it
  wasn't asked to open, messages, or anything behind a login.
- **Obscure topics with thin web coverage** may yield little, and for those
  Jarvis will usually say it couldn't find anything solid rather than guess.
- **It can occasionally be wrong or misread a source.** Synthesizing a 1-3
  sentence spoken answer means nuance gets compressed.

Treat Jarvis like a very well-informed assistant, not an oracle — for anything
high-stakes, verify independently.

## Roadmap (next phases)

- More skills (timers, reminders, smart home)
- GUI / system tray app
- Interruptible / streaming responses
