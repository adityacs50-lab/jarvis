"""Persistent conversation memory for Jarvis, backed by local SQLite.

Two tables:
  - session_log:  raw per-exchange log (timestamp, user_text, jarvis_response,
                  intent_type).
  - memory_notes: compact Claude-written summaries of past sessions (date,
                  summary_text), so long-term memory stays small instead of
                  re-feeding full transcripts into every prompt.

Everything is stored locally in jarvis_memory.db. Nothing leaves the machine
except the text sent to Claude's API as context/summarization input.
"""
import datetime
import logging
import sqlite3

import config
from skills.base import SkillResult

log = logging.getLogger("jarvis.memory")

# --- tools advertised to the router --------------------------------------
MEMORY_RECALL_TOOL = {
    "name": "memory_recall",
    "description": (
        "Recall what was discussed in PAST conversations when the user "
        "explicitly asks, e.g. 'what did we talk about yesterday', 'what did we "
        "cover last time', 'remind me what we said about hash tables'. Use ONLY "
        "when the user is asking to remember/recall earlier conversations."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": (
                    "Topic/keyword to search past conversations for, if the "
                    "user named one (e.g. 'hash tables'). Omit for a general "
                    "'what did we talk about' recall."
                ),
            },
            "when": {
                "type": "string",
                "description": (
                    "Time reference if given: 'today', 'yesterday', or "
                    "'last time'. Omit if none."
                ),
            },
        },
    },
}

MEMORY_CLEAR_TOOL = {
    "name": "memory_clear",
    "description": (
        "Erase ALL of Jarvis's stored memory. Use only for explicit requests "
        "like 'forget everything', 'clear your memory', 'wipe your memory'."
    ),
    "input_schema": {"type": "object", "properties": {}},
}

_SUMMARY_SYSTEM_PROMPT = (
    "You compress a conversation into a compact long-term memory note. In 1-3 "
    "short sentences, capture only durable, useful facts: the user's stated "
    "preferences, recurring topics, ongoing projects, and key details worth "
    "remembering later. If it was a study/tutoring session, note the subjects "
    "and specific topics covered (e.g. 'studied graph algorithms — Dijkstra, "
    "BFS'). Ignore small talk and one-off chatter. Write it as terse notes, not "
    "a narrative. If there is nothing worth remembering, reply with exactly: "
    "NOTHING."
)

_RECALL_SYSTEM_PROMPT = (
    "You are Jarvis. The user asked you to recall a past conversation. Given the "
    "matching log excerpts below, answer out loud in 1-3 short, natural "
    "sentences summarizing what was discussed. Don't read timestamps or quote "
    "verbatim. If the excerpts don't really answer the question, say you don't "
    "have much saved about that."
)


class Memory:
    def __init__(self, db_path=None):
        self.db_path = db_path or config.MEMORY_DB_PATH
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._init_db()
        self._buffer = []   # unsummarized exchanges from this session
        self._client = None
        log.info("Memory ready (%s).", self.db_path)

    # -- schema ------------------------------------------------------------
    def _init_db(self):
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS session_log (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp       TEXT NOT NULL,
                user_text       TEXT,
                jarvis_response TEXT,
                intent_type     TEXT
            );
            CREATE TABLE IF NOT EXISTS memory_notes (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                date         TEXT NOT NULL,
                summary_text TEXT NOT NULL
            );
            """
        )
        self.conn.commit()

    def _client_or_none(self):
        if self._client is not None:
            return self._client
        if not config.ANTHROPIC_API_KEY:
            return None
        try:
            from anthropic import Anthropic

            self._client = Anthropic(api_key=config.ANTHROPIC_API_KEY)
        except Exception as e:  # pragma: no cover
            log.warning("Could not init Anthropic client for memory: %s", e)
            self._client = None
        return self._client

    # -- logging -----------------------------------------------------------
    def log_exchange(self, user_text, jarvis_response, intent_type):
        ts = datetime.datetime.now().isoformat(timespec="seconds")
        self.conn.execute(
            "INSERT INTO session_log (timestamp, user_text, jarvis_response, "
            "intent_type) VALUES (?, ?, ?, ?)",
            (ts, user_text, jarvis_response, intent_type),
        )
        self.conn.commit()
        self._buffer.append((intent_type, user_text, jarvis_response))

    # -- long-term notes ---------------------------------------------------
    def recent_notes(self, n=None):
        n = n or config.MEMORY_NOTES_TO_LOAD
        rows = self.conn.execute(
            "SELECT date, summary_text FROM memory_notes ORDER BY id DESC LIMIT ?",
            (n,),
        ).fetchall()
        return list(reversed(rows))  # chronological

    def context_block(self):
        """Background-context string for the system prompt, or '' if empty."""
        notes = self.recent_notes()
        if not notes:
            return ""
        lines = "\n".join(f"- ({r['date']}) {r['summary_text']}" for r in notes)
        return (
            "Relevant context from past conversations (background only — do NOT "
            "bring these up unprompted; use them quietly for continuity, and "
            "surface a specific detail only if directly relevant or if the user "
            "asks you to recall something):\n" + lines
        )

    def maybe_summarize(self):
        """Summarize periodically once enough exchanges have accumulated."""
        if len(self._buffer) >= config.MEMORY_SUMMARIZE_EVERY:
            self._summarize_buffer()

    def summarize_session(self):
        """Flush any remaining unsummarized exchanges (call at shutdown)."""
        if self._buffer:
            self._summarize_buffer()

    def _summarize_buffer(self):
        client = self._client_or_none()
        if client is None:
            self._buffer.clear()  # can't summarize without API; avoid pile-up
            return
        transcript = "\n".join(
            f"[{intent}] User: {u}\nJarvis: {r}"
            for (intent, u, r) in self._buffer
        )
        try:
            msg = client.messages.create(
                model=config.CLAUDE_MODEL,
                max_tokens=200,
                system=_SUMMARY_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": transcript}],
            )
            summary = "".join(
                b.text for b in msg.content if getattr(b, "type", None) == "text"
            ).strip()
        except Exception as e:  # pragma: no cover
            log.warning("Session summarization failed: %s", e)
            return
        self._buffer.clear()
        if not summary or summary.strip().upper() == "NOTHING":
            log.info("📝 Nothing worth remembering from this batch.")
            return
        today = datetime.date.today().isoformat()
        self.conn.execute(
            "INSERT INTO memory_notes (date, summary_text) VALUES (?, ?)",
            (today, summary),
        )
        self.conn.commit()
        log.info("📝 Stored memory note: %s", summary)

    # -- recall on demand --------------------------------------------------
    def recall(self, query=None, when=None):
        rows = self._search_log(query, when)
        if not rows:
            return SkillResult("I don't have anything saved about that.")

        client = self._client_or_none()
        excerpts = "\n".join(
            f"({r['timestamp']}) User: {r['user_text']} | Jarvis: {r['jarvis_response']}"
            for r in rows
        )
        if client is None:
            # Fallback: stitch a couple of user lines together.
            sample = "; ".join(r["user_text"] for r in rows[:3] if r["user_text"])
            return SkillResult(f"We talked about: {sample}." if sample else
                               "I found some history but can't summarize it right now.")
        ask = (query or "what we talked about")
        try:
            msg = client.messages.create(
                model=config.CLAUDE_MODEL,
                max_tokens=config.CLAUDE_MAX_TOKENS,
                system=_RECALL_SYSTEM_PROMPT,
                messages=[{
                    "role": "user",
                    "content": f"Question: {ask}\n\nMatching log excerpts:\n{excerpts}",
                }],
            )
            answer = "".join(
                b.text for b in msg.content if getattr(b, "type", None) == "text"
            ).strip()
        except Exception as e:  # pragma: no cover
            log.warning("Recall summarization failed: %s", e)
            return SkillResult("I had trouble looking that up just now.")
        return SkillResult(answer or "I don't have much saved about that.")

    def _search_log(self, query, when):
        clauses, params = [], []
        if query:
            clauses.append("(user_text LIKE ? OR jarvis_response LIKE ?)")
            params += [f"%{query}%", f"%{query}%"]
        if when:
            w = when.lower()
            if "yesterday" in w:
                day = datetime.date.today() - datetime.timedelta(days=1)
                clauses.append("date(timestamp) = ?")
                params.append(day.isoformat())
            elif "today" in w:
                clauses.append("date(timestamp) = ?")
                params.append(datetime.date.today().isoformat())
            elif "last" in w:
                # Most recent day we have any log for.
                row = self.conn.execute(
                    "SELECT date(timestamp) d FROM session_log ORDER BY id DESC LIMIT 1"
                ).fetchone()
                if row:
                    clauses.append("date(timestamp) = ?")
                    params.append(row["d"])
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        return self.conn.execute(
            f"SELECT timestamp, user_text, jarvis_response FROM session_log{where} "
            "ORDER BY id DESC LIMIT 30",
            params,
        ).fetchall()

    # -- wipe --------------------------------------------------------------
    def clear(self):
        self.conn.execute("DELETE FROM session_log")
        self.conn.execute("DELETE FROM memory_notes")
        self.conn.commit()
        self._buffer.clear()
        log.info("🧹 Memory cleared (both tables wiped).")
        return SkillResult("Done. I've cleared everything I remembered.")
