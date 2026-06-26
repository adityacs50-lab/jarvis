# Jarvis — Voice Assistant (Phase 8)

A JARVIS-style, always-listening voice assistant that runs as a background
script. Say the wake word, ask a question, and Jarvis answers out loud with a
witty, concise personality powered by Claude.

An intent-routing step classifies every request and dispatches it to the right
skill:

- **`music_control`** → Spotify (Phase 2)
- **`system_control`** → open apps, open websites/search, basic file ops (Phase 3)
- **`web_lookup`** → live internet search via Claude's built-in web search (Phase 4)
- **`code_generation`** → generate code to a file and open it in an editor (Phase 5)
- **`study_mode`** → toggle an adaptive Socratic **Study Mode** tutor (Phase 6)
- **`memory_recall`** / **`memory_clear`** → recall or wipe long-term memory (Phase 7)
- **`vision_request`** → capture a webcam frame (or file) and analyze it (Phase 8)
- **`general_chat`** → a normal spoken Claude reply

**Study Mode** is a session toggle: while on, concept/coursework questions are
answered by a Socratic tutor instead of the normal assistant (see
[Study Mode](#study-mode) below). **Memory** gives Jarvis continuity across
sessions via a local database (see [Memory](#memory) below).

Intent classification and parameter extraction both happen in a single Claude
call using native tool use — no keyword matching. The router is deliberately
biased toward `web_lookup`: unless it's confident the answer is timeless, it
searches the web rather than risk answering with stale info.

```
wake word ("jarvis")  →  record (until you stop talking)  →  transcribe
        ↑                                                          ↓
        |                                              intent router (Claude)
        |        ┌──────────────┬──────────────┬──────────────┬──────────────┐
        |  music_control  system_control  web_lookup   code_generation  general_chat
        |        ↓              ↓              ↓              ↓              ↓
      speak ← TTS ← Spotify / System / Web search / Code→file→editor / Claude reply
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
| Code generation  | Claude + local file write + VS Code `code` CLI / OS editor |
| Study Mode       | Claude with a dedicated Socratic tutoring prompt + session state |
| Memory           | local **SQLite** (`jarvis_memory.db`) + Claude session summaries |
| Vision           | **OpenCV** webcam capture + Claude vision (`claude-sonnet-4-6`) |
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

### Code generation commands (Phase 5)

Ask Jarvis to write code and it generates a file, saves it to
`./jarvis_generated_code/`, and opens it in your editor — then gives a short
spoken confirmation instead of reading the code aloud.

- "write me a Python script that renames all files in a folder"
- "create a Java function for bubble sort"
- "write a webpage in HTML with a contact form"
- "make a script that scrapes headlines from a website"

The language sets the extension (`.py`, `.js`, `.html`, `.java`, …). If you name
the file ("call it scraper") that's used; otherwise Jarvis picks a sensible name
from your request. Existing files are **never overwritten** — it appends a
number (`scraper.py`, `scraper_1.py`, …).

> **Not** code generation: "what does this Python error mean", "explain this
> function", "how do I use a dictionary" — those stay general chat. Code
> generation triggers only when you want a **new file** written.

> ⚠️ **Safety:** generated code is **never executed automatically** — Jarvis
> only writes the file and opens it. You review and run it yourself.

## Study Mode

Study Mode turns Jarvis into an adaptive, Socratic tutor for engineering
coursework (DSA, algorithms, OOP, math, systems). It's a **session toggle**,
separate from the code-generation skill.

**Toggle it by voice:**

- "Jarvis, enter study mode" / "let's study" / "start studying" → Jarvis
  announces the change and asks once: *"What are we working on today, and are we
  doing a quick concept check or going deep?"* so it can calibrate pacing.
- "Jarvis, exit study mode" / "I'm done studying" → returns to normal behavior.

**While in study mode, the tutor:**

- Is **Socratic** — when you're stuck it asks a leading question to find where
  your understanding breaks down *before* handing over the full solution.
- **Defaults to hints and partial explanations**, revealing more as needed —
  *unless* you say "just give me the answer" or "I don't have time, explain it
  directly," in which case it answers straight.
- **Builds from first principles** — intuition and a simple example first, then
  the formal definition.
- For **coding coursework**, it encourages you to write the code yourself and
  offers to review/debug it. It deliberately will **not** write the full
  solution to a file (the `code_generation` skill is disabled while studying).
- Keeps each spoken turn reasonably short, but goes longer for genuine
  explanations.
- **Remembers the session** — earlier topics stay in context, so it can say
  things like "like we discussed with segment trees earlier."

Music, system, and web commands still work in study mode for explicit requests
("play some lo-fi", "what's the weather") — only general/coursework questions
get routed to the tutor.

> **Honest note:** Study Mode is designed to help you *understand the material,
> not to do the work for you.* It will deliberately resist just handing over
> full answers unless you explicitly ask it to. That's the point — it's a tutor,
> not an answer key.

## Memory

Jarvis remembers across sessions. Everything is stored **locally** in an SQLite
file, **`jarvis_memory.db`**, created automatically on first run. Two tables:

- **`session_log`** — the raw log of each exchange (`timestamp`, `user_text`,
  `jarvis_response`, `intent_type`).
- **`memory_notes`** — compact, Claude-written summaries of past sessions
  (`date`, `summary_text`). These keep long-term memory small instead of
  bloating every future prompt with full transcripts.

**How it works:**

- **During a session**, every ~6 exchanges (and once more on exit) Jarvis makes
  a *separate, lightweight* Claude call to summarize the recent exchanges into a
  short memory note. Study sessions capture the subjects/topics covered, for
  tutoring continuity.
- **At the start of each session**, the most recent notes (default 10,
  configurable via `MEMORY_NOTES_TO_LOAD`) are loaded and injected into the
  system prompt as quiet background context — so Jarvis has continuity without
  re-reading full transcripts.
- **It won't bring up old conversations unprompted.** Memory is used quietly to
  inform tone/context; Jarvis only surfaces a specific past detail when it's
  directly relevant or when you explicitly ask.

**Recall on demand** (queries the raw log by keyword/date):

- "Jarvis, what did we talk about yesterday?"
- "what did we cover last time?"
- "remind me what we said about hash tables"

**Clear memory** (wipes *both* tables, with a spoken confirmation first):

- "Jarvis, forget everything" / "clear your memory" → Jarvis asks
  "Are you sure…? Say yes to confirm" and only wipes if you confirm.

**View it yourself** — it's a plain SQLite file:

```bash
sqlite3 jarvis_memory.db "SELECT timestamp, user_text, jarvis_response FROM session_log;"
sqlite3 jarvis_memory.db "SELECT date, summary_text FROM memory_notes;"
```

> 🔒 **Privacy:** memory is **local to this machine** and is never sent anywhere
> except to Claude's API as context/summarization input. But it is **not
> encrypted** — anyone with access to `jarvis_memory.db` can read your
> conversation history. Don't speak sensitive information (passwords, card
> numbers, secrets) to Jarvis. Delete `jarvis_memory.db` or say "forget
> everything" to wipe it.

## Vision

Jarvis can look at something through your webcam (or an image file) and answer
about it — read a page, describe an object, or help with a problem you hold up.

**Trigger phrases** (Claude infers the intent):

- "Jarvis, look at this" / "can you see this?"
- "what does this say?" / "read this page"
- "help me with this problem" (when you're clearly showing something)
- File mode: "look at the image in `photo.jpg`" (skips the webcam, reads the file)

**What happens:**

1. Jarvis says **"Okay, hold it steady"** and waits ~2 seconds
   (`CAPTURE_DELAY_SECONDS`) so you can position the page/object.
2. It captures **one** frame, sends it to Claude's vision model with your spoken
   request as context, and speaks a concise answer (you're probably holding a
   book at an awkward angle — it keeps it short).
3. The temp capture is **deleted** afterward by default.

**Study Mode aware:** if you're in [Study Mode](#study-mode) and show it a
homework problem, it stays Socratic — leaning toward a hint or leading question
rather than just reading out the answer, unless you ask for the direct answer.

> 🔒 **Privacy:** the camera is used **only on an explicit voice command** — it
> is **never continuous or always-on**. Jarvis opens the webcam, grabs a single
> frame, and releases it immediately. Captures are saved to `jarvis_temp/` and
> **deleted after analysis** unless you set `KEEP_CAPTURES=true` in `.env`. The
> frame is sent to Claude's API for analysis (and nowhere else).
>
> **Webcam permissions are OS-specific.** Your OS may need to grant camera
> access to the terminal/Python process. On **Windows**, check
> *Settings → Privacy & security → Camera* and ensure "Let desktop apps access
> your camera" is on (and that your terminal/Python is allowed). On macOS you'll
> get a camera-permission prompt the first time. If the camera can't be opened,
> Jarvis says so out loud instead of crashing.

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

### 6. Code generation setup (Phase 5 — VS Code CLI, optional)

Generated code is saved to a **`jarvis_generated_code/`** folder in the project
directory (created automatically) and opened in an editor.

For the **VS Code integration**, the `code` command must be available on your
`PATH`. To enable it: open VS Code → **Command Palette** (`Ctrl/Cmd+Shift+P`) →
run **"Shell Command: Install 'code' command in PATH"**
([docs](https://code.visualstudio.com/docs/configure/command-line#_launching-from-command-line)).

If the `code` command isn't found, Jarvis falls back to opening the file with
your **OS default editor** for that file type, so this step is optional.

> ⚠️ **Safety:** Jarvis **never executes** generated code. It only writes the
> file and opens it for you to review and run yourself. Existing files are never
> overwritten — a numeric suffix is added instead.

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

A code-generation turn looks like:

```
🗣️  Heard: write me a python script that renames files
🧭 Routing intent...
⌨️  code_generation {'request': 'a script that renames files', 'language': 'python'}
⌨️  Generating code: a script that renames files
💾 Saved /path/to/jarvis_generated_code/renames_files.py
💬 Jarvis: Done, I've opened renames_files.py in VS Code.
🔊 Speaking...
```

A study-mode session looks like:

```
🗣️  Heard: jarvis enter study mode
🧭 Routing intent...
📚 Study mode ON — new session.
💬 Jarvis: Study mode on. What are we working on today, and are we doing a quick concept check or going deep?
🔊 Speaking...
...
🗣️  Heard: I'm stuck on reversing a linked list
🧭 Routing intent... [study]
📚 [study] Jarvis: Before I show you — what do you think you need to keep track of as you walk the list? What would you lose if you just moved forward?
🔊 Speaking...
```

A vision turn looks like:

```
🗣️  Heard: jarvis what does this say
🧭 Routing intent...
👁️  vision_request {'request': 'what does this say'}
🔊 Speaking...   # "Okay, hold it steady."
📸 Opening webcam...
📸 Captured frame (48213 bytes).
👁️  Analyzing image...
🧹 Deleted temp capture.
💬 Jarvis: It's a page about binary search trees — the heading says "BST insertion".
🔊 Speaking...
```

A memory-recall turn looks like:

```
🗣️  Heard: what did we talk about yesterday
🧭 Routing intent...
🧠 memory_recall {'when': 'yesterday'}
💬 Jarvis: Yesterday we went over graph algorithms — mostly Dijkstra and BFS — and you asked about the weather.
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
intent_router.py        # Claude tool-use router + study-mode state machine + memory logging
memory.py               # SQLite persistent memory: session log, summaries, recall, clear
skills/
  base.py               # SkillResult (incl. pending/confirmation contract)
  spotify_skill.py      # Spotipy playback control + music_control tool schema
  system_skill.py       # apps / websites / file ops + system_control tool schema
  web_skill.py          # live web search via Claude web_search + web_lookup tool schema
  code_skill.py         # code generation -> file -> editor + code_generation tool schema
  study_skill.py        # Socratic tutor prompt + study_mode toggle + session topics
  vision_skill.py       # OpenCV webcam capture + Claude vision + vision_request tool schema
system_config.json      # editable app nickname -> path + folder shortcuts
jarvis_generated_code/  # (auto-created) generated code files land here
jarvis_memory.db        # (auto-created) local SQLite conversation memory
jarvis_temp/            # (auto-created) temporary webcam captures (deleted by default)
llm.py                  # standalone Claude chat helper (Phase 1; superseded by the router)
tts.py                  # pyttsx3 / ElevenLabs speech output
main.py                 # the loop that ties it all together (incl. confirmation step)
```

### Intent routing

`intent_router.py` makes a single Claude call per utterance, passing the
`music_control`, `system_control`, `web_lookup`, and `code_generation` tool
definitions. Claude either **calls a tool** (returning a structured payload we
dispatch to `SpotifySkill`, `SystemSkill`, `WebSkill`, or `CodeSkill`) or
**replies in plain text** (general chat). This uses Claude's native tool use /
function calling for intent classification *and* parameter extraction — no
manual keyword parsing. Short conversation history is retained so follow-ups
("play it again", "now what's playing?") keep context.

**Vision:** the `vision_request` tool dispatches to `VisionSkill`, which speaks
a "hold it steady" heads-up (via a `notify` callback into TTS), captures one
webcam frame with OpenCV, base64-encodes it, and sends it to Claude's vision
model with the spoken request as context. In study mode it uses the tutoring
prompt so homework images stay Socratic. The temp capture is deleted unless
`KEEP_CAPTURES=true`. Camera errors become spoken messages, never crashes.

**Memory:** `memory.py` logs every exchange to SQLite and periodically asks
Claude (a separate summarization prompt) to compress recent exchanges into a
compact note. At startup the router loads recent notes via `memory.context_block()`
and injects them as quiet background context — with an explicit instruction *not*
to bring up past conversations unprompted. The `memory_recall` and `memory_clear`
tools (the latter gated by the same spoken-confirmation mechanism as deletes)
handle on-demand recall and wiping. Memory works in study mode too; study
summaries record the subjects covered for tutoring continuity.

**Study Mode state machine:** the router holds a `study_mode` flag. The
`study_mode` tool toggles it (and clears history for a clean session). While on,
the router swaps in the tutoring system prompt, hides the `code_generation` tool,
allows longer answers, and keeps a larger conversation window so the tutor can
recall earlier topics — all without affecting the other skills.

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

**Generated code** is written and opened, never run. Like any AI-generated
code it can contain bugs or insecure patterns — review it before executing.

## Roadmap (next phases)

- More skills (timers, reminders, smart home)
- GUI / system tray app
- Interruptible / streaming responses
