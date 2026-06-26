"""Layer 5 — intent router in isolation. Run on your machine (needs API key).

    python tests/test_5_router_live.py

Feeds text straight into the router (no voice) and prints which intent Claude
picks for each. Catches misrouting in seconds. Skills are replaced with stubs
that just echo their name, so you see the ROUTE, not real side effects (no music
plays, no files open). general_chat shows Claude's actual short reply.

Edit PHRASES below to probe your own tricky cases.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config  # noqa: E402
from intent_router import IntentRouter  # noqa: E402
from skills.base import SkillResult  # noqa: E402

PHRASES = [
    ("play some Arctic Monkeys",              "music_control"),
    ("pause the music",                       "music_control"),
    ("open Chrome",                           "system_control"),
    ("make a folder called notes",            "system_control"),
    ("what's the weather in Tokyo right now",  "web_lookup"),
    ("who's the current CEO of OpenAI",       "web_lookup"),
    ("write me a python script that renames files", "code_generation"),
    ("what does a python IndexError mean",    "general_chat"),   # NOT code_generation
    ("what's 2 plus 2",                       "general_chat"),
    ("tell me a joke",                        "general_chat"),
    ("enter study mode",                      "study_mode"),
    ("what did we talk about yesterday",      "memory_recall"),
    ("forget everything",                     "memory_clear"),
]


class StubSkill:
    """Echoes the intent name instead of doing anything real."""
    def __init__(self, name):
        self.name = name

    def handle(self, tool_input):
        return SkillResult(f"<<{self.name}>>  input={tool_input}")


class StubStudy:
    tutor_system_prompt = "You are a tutor."

    def enter(self):
        return SkillResult("<<study_mode:enter>>")

    def exit(self):
        return SkillResult("<<study_mode:exit>>")

    def note_topic(self, _):
        pass


class StubMemory:
    def context_block(self):
        return ""

    def log_exchange(self, *a):
        pass

    def maybe_summarize(self):
        pass

    def recall(self, query=None, when=None):
        return SkillResult(f"<<memory_recall>>  query={query} when={when}")

    def clear(self):
        return SkillResult("<<memory_clear:executed>>")


def main():
    config.setup_logging()
    router = IntentRouter(
        spotify_skill=StubSkill("music_control"),
        system_skill=StubSkill("system_control"),
        web_skill=StubSkill("web_lookup"),
        code_skill=StubSkill("code_generation"),
        study_skill=StubStudy(),
        memory=StubMemory(),
    )

    print("\n=== ROUTER INTENT TEST ===\n")
    passed = 0
    for phrase, expected in PHRASES:
        # Fresh router state per phrase so study-mode toggle doesn't leak.
        router.study_mode = False
        router.history = []
        router._pending = None
        result = router.handle(phrase)
        speech = (result.speech if result else "") or ""
        # Derive the route from the sentinel; general_chat = plain reply.
        if speech.startswith("<<"):
            got = speech.split(">>")[0].lstrip("<").split(":")[0]
        else:
            got = "general_chat"
        ok = (got == expected)
        passed += ok
        print(f"[{'PASS' if ok else 'FAIL'}] {phrase!r}\n"
              f"        expected={expected}  got={got}")
        if got != expected:
            print(f"        (reply: {speech[:80]!r})")
    print(f"\n{passed}/{len(PHRASES)} routed as expected.")
    print("Note: routing is Claude's judgment — a 'FAIL' may be a reasonable "
          "alternative read, not a bug. Eyeball the misses.")


if __name__ == "__main__":
    main()
