"""Memory layer test — offline, no API key needed (uses a temp DB).

    python tests/test_memory.py

Exercises the SQLite layer directly: logging, recall by keyword/date, the
empty-result path, and clear() wiping both tables. Summarization/recall that
need Claude are covered by their fallback paths here.
"""
import datetime
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from memory import Memory  # noqa: E402

FAILS = []
def check(label, cond):
    print(f"[{'PASS' if cond else 'FAIL'}] {label}")
    if not cond:
        FAILS.append(label)


def main():
    db = str(Path(tempfile.mkdtemp()) / "t.db")
    m = Memory(db_path=db)

    check("starts with no notes", m.recent_notes() == [])
    check("empty context block", m.context_block() == "")

    m.log_exchange("explain dijkstra", "It finds shortest paths.", "study")
    m.log_exchange("what's the weather", "Sunny.", "web_lookup")
    rows = m._search_log("dijkstra", None)
    check("keyword search finds match", len(rows) == 1)
    check("keyword miss returns nothing",
          m.recall("nonexistent-xyz").speech == "I don't have anything saved about that.")

    today = datetime.date.today().isoformat()
    check("date filter 'today' finds rows", len(m._search_log(None, "today")) == 2)
    check("date filter 'yesterday' empty", m._search_log(None, "yesterday") == [])

    m.conn.execute("INSERT INTO memory_notes (date, summary_text) VALUES (?, ?)",
                   (today, "Studied graph algorithms - Dijkstra, BFS."))
    m.conn.commit()
    check("context block now populated",
          m.context_block().startswith("Relevant context from past"))
    check("note appears in context", "Dijkstra" in m.context_block())

    m.clear()
    check("clear wipes session_log", m._search_log(None, None) == [])
    check("clear wipes memory_notes", m.recent_notes() == [])

    print(f"\n{'ALL PASS' if not FAILS else f'{len(FAILS)} FAILURES: {FAILS}'}")
    sys.exit(1 if FAILS else 0)


if __name__ == "__main__":
    main()
