"""Hermetic router WIRING test — runs with no deps, no API key, no audio.

This fakes the Anthropic client so *we* decide which tool Claude "calls", then
asserts the router dispatches to the right skill, toggles study mode, hides the
code tool while studying, runs the confirmation flow for destructive actions,
and logs exchanges to memory. It does NOT test Claude's intent judgment (that
needs a key — see test_5_router_live.py); it tests everything around it.

    python tests/test_router_wiring.py
"""
import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# --- fake the anthropic module BEFORE importing the router ----------------
fake_anthropic = types.ModuleType("anthropic")
fake_anthropic.Anthropic = lambda *a, **k: None  # replaced on the router later
sys.modules["anthropic"] = fake_anthropic

import config  # noqa: E402
config.ANTHROPIC_API_KEY = "test-key"  # satisfy the router's guard

from intent_router import IntentRouter  # noqa: E402
from skills.base import SkillResult  # noqa: E402


# --- fake Claude response plumbing ----------------------------------------
class Block:
    def __init__(self, **kw):
        self.__dict__.update(kw)


def tool_msg(name, tool_input):
    return Block(content=[Block(type="tool_use", name=name,
                                input=tool_input, id="tu_1")])


def text_msg(text):
    return Block(content=[Block(type="text", text=text)])


class FakeClient:
    """Returns whatever response is queued; records the last call's kwargs."""
    def __init__(self):
        self._queue = []
        self.last_kwargs = None
        self.messages = types.SimpleNamespace(create=self._create)

    def queue(self, response):
        self._queue.append(response)

    def _create(self, **kwargs):
        self.last_kwargs = kwargs
        return self._queue.pop(0)


# --- stub skills ----------------------------------------------------------
class Stub:
    def __init__(self, name):
        self.name = name
        self.calls = []

    def handle(self, tool_input):
        self.calls.append(tool_input)
        return SkillResult(f"<<{self.name}>>")


class DeleteStub(Stub):
    def handle(self, tool_input):
        self.calls.append(tool_input)
        self.executed = False

        def _do():
            self.executed = True
            return SkillResult("deleted")
        return SkillResult("Are you sure? Say yes to confirm.", pending=_do)


class StudyStub:
    tutor_system_prompt = "TUTOR"
    def __init__(self): self.entered = False
    def enter(self): self.entered = True; return SkillResult("study on")
    def exit(self): self.entered = False; return SkillResult("study off")
    def note_topic(self, _): pass


class MemStub:
    def __init__(self): self.logged = []; self.cleared = False
    def context_block(self): return ""
    def log_exchange(self, u, r, i): self.logged.append((u, r, i))
    def maybe_summarize(self): pass
    def recall(self, query=None, when=None): return SkillResult("<<recall>>")
    def clear(self): self.cleared = True; return SkillResult("wiped")


# --- test runner ----------------------------------------------------------
FAILS = []
def check(label, cond):
    print(f"[{'PASS' if cond else 'FAIL'}] {label}")
    if not cond:
        FAILS.append(label)


def make_router():
    spotify, system, web, code = (Stub("music"), DeleteStub("system"),
                                  Stub("web"), Stub("code"))
    study, mem = StudyStub(), MemStub()
    r = IntentRouter(spotify_skill=spotify, system_skill=system, web_skill=web,
                     code_skill=code, study_skill=study, memory=mem)
    r.client = FakeClient()
    return r, spotify, system, web, code, study, mem


def main():
    # 1. Each tool routes to its skill.
    for tool, attr in [("music_control", "music"), ("web_lookup", "web"),
                       ("code_generation", "code")]:
        r, sp, sy, we, co, st, mem = make_router()
        r.client.queue(tool_msg(tool, {"x": 1}))
        out = r.handle("whatever")
        check(f"{tool} dispatches + returns sentinel",
              out.speech.startswith("<<"))
        check(f"{tool} logged to memory",
              len(mem.logged) == 1 and mem.logged[0][2] == tool)

    # 2. Destructive system action -> confirmation -> execute only on yes.
    r, sp, sy, we, co, st, mem = make_router()
    r.client.queue(tool_msg("system_control", {"action": "delete_path"}))
    out = r.handle("delete old.txt")
    check("delete asks for confirmation", out.needs_confirmation)
    check("delete NOT executed before yes", getattr(sy, "executed", False) is False)
    out2 = r.confirm("yes")
    check("delete executes after yes", out2.speech == "deleted")

    # 3. Confirmation rejected -> not executed.
    r, sp, sy, we, co, st, mem = make_router()
    r.client.queue(tool_msg("system_control", {"action": "delete_path"}))
    r.handle("delete old.txt")
    r.confirm("no thanks")
    check("delete NOT executed after no", getattr(sy, "executed", False) is False)

    # 4. Study mode toggle flips flag and hides code tool, keeps study tool.
    r, sp, sy, we, co, st, mem = make_router()
    r.client.queue(tool_msg("study_mode", {"action": "enter"}))
    r.handle("enter study mode")
    check("study_mode flag set", r.study_mode is True)
    check("study announced", st.entered is True)
    names = {t["name"] for t in r._active_tools()}
    check("code_generation hidden while studying", "code_generation" not in names)
    check("study_mode tool still present", "study_mode" in names)
    # exiting restores code tool
    r.client.queue(tool_msg("study_mode", {"action": "exit"}))
    r.handle("exit study mode")
    check("study_mode flag cleared", r.study_mode is False)
    check("code_generation visible again",
          "code_generation" in {t["name"] for t in r._active_tools()})

    # 5. In study mode, the tutor system prompt is used for the call.
    r, sp, sy, we, co, st, mem = make_router()
    r.study_mode = True
    r.client.queue(text_msg("Socratic question?"))
    r.handle("explain dijkstra")
    check("tutor prompt used in study mode",
          r.client.last_kwargs["system"].startswith("TUTOR"))

    # 6. memory_clear requires confirmation, then wipes.
    r, sp, sy, we, co, st, mem = make_router()
    r.client.queue(tool_msg("memory_clear", {}))
    out = r.handle("forget everything")
    check("memory_clear asks confirmation", out.needs_confirmation)
    check("memory NOT wiped before yes", mem.cleared is False)
    r.confirm("yes")
    check("memory wiped after yes", mem.cleared is True)

    # 7. memory_recall routes to memory.recall.
    r, sp, sy, we, co, st, mem = make_router()
    r.client.queue(tool_msg("memory_recall", {"when": "yesterday"}))
    out = r.handle("what did we talk about yesterday")
    check("memory_recall returns recall result", out.speech == "<<recall>>")

    # 8. Plain text (no tool) -> general_chat reply + logged.
    r, sp, sy, we, co, st, mem = make_router()
    r.client.queue(text_msg("Paris."))
    out = r.handle("capital of France?")
    check("general_chat returns text", out.speech == "Paris.")
    check("general_chat logged as general_chat",
          mem.logged and mem.logged[-1][2] == "general_chat")

    print(f"\n{'ALL PASS' if not FAILS else f'{len(FAILS)} FAILURES: {FAILS}'}")
    sys.exit(1 if FAILS else 0)


if __name__ == "__main__":
    main()
