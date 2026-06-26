"""Intent router: classify each utterance and dispatch to the right skill.

A single Claude call with tool use decides between intents:
  - music_control   -> Spotify skill
  - system_control  -> System skill (apps, websites, files)
  - web_lookup      -> Web skill (live internet search via Claude web_search)
  - code_generation -> Code skill (generate a file and open it in an editor)
  - study_mode      -> Study skill (toggle the tutoring mode on/off)
  - general_chat    -> plain text reply

The router is deliberately biased toward web_lookup: unless Claude is highly
confident the answer is timeless/static, it should search rather than answer
from memory (see config.ROUTING_GUIDANCE).

Study Mode is a session-state flag. While it's on, the normal system prompt is
swapped for the tutoring prompt, the code-generation tool is hidden (coursework
is taught, not written to a file), and general questions become Socratic
tutoring answers instead of plain chat. Music/system/web tools still work for
explicit commands.

Claude's native tool use does both intent classification and structured
parameter extraction in one step (no hand-rolled string parsing).

Destructive system actions (delete) come back as a SkillResult with a pending
callable. The router speaks a confirmation prompt and waits; the next utterance
is interpreted as yes/no via `confirm()` before anything is executed.
"""
import logging

import config
from memory import MEMORY_CLEAR_TOOL, MEMORY_RECALL_TOOL
from skills.base import SkillResult, as_result
from skills.code_skill import CODE_GENERATION_TOOL
from skills.spotify_skill import MUSIC_CONTROL_TOOL
from skills.study_skill import STUDY_MODE_TOOL
from skills.system_skill import SYSTEM_CONTROL_TOOL
from skills.web_skill import WEB_LOOKUP_TOOL

# In study mode, answer coursework yourself as the tutor; only reach for a tool
# on an explicit command or to leave study mode.
_STUDY_ROUTING_NOTE = (
    "\n\nYou are currently in Study Mode. Answer concept, problem, and "
    "coursework questions yourself as the tutor described above — including "
    "code-related coursework, which you guide rather than write to a file. Only "
    "call a tool for an explicit music, computer/app/file, or web-search "
    "command, or to exit study mode when asked."
)

log = logging.getLogger("jarvis.router")

_AFFIRMATIVE = {
    "yes", "yeah", "yep", "yup", "sure", "confirm", "confirmed", "do it",
    "go ahead", "ok", "okay", "affirmative", "please do", "correct",
}


class IntentRouter:
    def __init__(self, spotify_skill=None, system_skill=None, web_skill=None,
                 code_skill=None, study_skill=None, memory=None):
        from anthropic import Anthropic

        if not config.ANTHROPIC_API_KEY:
            raise RuntimeError(
                "ANTHROPIC_API_KEY is not set. Add it to your .env file."
            )
        self.client = Anthropic(api_key=config.ANTHROPIC_API_KEY)
        self.spotify = spotify_skill
        self.system = system_skill
        self.web = web_skill
        self.code = code_skill
        self.study = study_skill
        self.memory = memory
        self.history = []
        self._pending = None  # callable awaiting spoken confirmation
        self._current_user = None  # utterance being processed (for logging)
        self.study_mode = False  # session-state flag

        # Routing call gets extra guidance biasing toward live web lookup.
        self.system_prompt = config.SYSTEM_PROMPT + "\n\n" + config.ROUTING_GUIDANCE

        # Load compact long-term memory once, injected as quiet background.
        self.memory_context = memory.context_block() if memory else ""

    def _active_tools(self):
        """Tools advertised this turn (depends on study mode)."""
        tools = []
        if self.spotify:
            tools.append(MUSIC_CONTROL_TOOL)
        if self.system:
            tools.append(SYSTEM_CONTROL_TOOL)
        if self.web:
            tools.append(WEB_LOOKUP_TOOL)
        if self.study:
            tools.append(STUDY_MODE_TOOL)
        if self.memory:
            tools.append(MEMORY_RECALL_TOOL)
            tools.append(MEMORY_CLEAR_TOOL)
        # Code generation is hidden while studying so coursework is taught.
        if self.code and not self.study_mode:
            tools.append(CODE_GENERATION_TOOL)
        return tools

    # -- public API --------------------------------------------------------
    def handle(self, user_text) -> SkillResult:
        """Process one utterance. Returns a SkillResult to speak.

        If the result `needs_confirmation`, the caller should record a yes/no
        answer and pass it to `confirm()`.
        """
        # If we're mid-confirmation, treat this utterance as the answer.
        if self._pending is not None:
            return self.confirm(user_text)

        log.info("🧭 Routing intent...%s", " [study]" if self.study_mode else "")
        self._current_user = user_text
        self.history.append({"role": "user", "content": user_text})

        if self.study_mode and self.study:
            system = self.study.tutor_system_prompt + _STUDY_ROUTING_NOTE
            max_tokens = config.STUDY_MAX_TOKENS
        else:
            system = self.system_prompt
            max_tokens = config.CLAUDE_MAX_TOKENS

        # Inject compact long-term memory as quiet background context.
        if self.memory_context:
            system = system + "\n\n" + self.memory_context

        message = self.client.messages.create(
            model=config.CLAUDE_MODEL,
            max_tokens=max_tokens,
            system=system,
            tools=self._active_tools(),
            messages=self.history,
        )

        tool_use = next(
            (b for b in message.content if b.type == "tool_use"), None
        )

        if tool_use and tool_use.name == "study_mode" and self.study:
            return self._handle_study_toggle(tool_use)

        if tool_use and tool_use.name == "memory_recall" and self.memory:
            log.info("🧠 memory_recall %s", tool_use.input)
            return self._dispatch("🧠 memory_recall", message, tool_use,
                                   self.memory.recall(**_recall_args(tool_use.input)),
                                   intent="memory_recall", log_memory=False)

        if tool_use and tool_use.name == "memory_clear" and self.memory:
            # Wipe requires spoken confirmation via the pending mechanism.
            log.info("🧠 memory_clear requested")
            return self._dispatch(
                "🧠 memory_clear", message, tool_use,
                SkillResult(
                    "Are you sure you want me to erase everything I remember? "
                    "Say yes to confirm.",
                    pending=self._wipe_memory,
                ),
                intent="memory_clear", log_memory=False)

        if tool_use and tool_use.name == "music_control" and self.spotify:
            return self._dispatch("🎵 music_control", message, tool_use,
                                   self.spotify.handle(tool_use.input),
                                   intent="music_control")

        if tool_use and tool_use.name == "system_control" and self.system:
            return self._dispatch("🖥️  system_control", message, tool_use,
                                   self.system.handle(tool_use.input),
                                   intent="system_control")

        if tool_use and tool_use.name == "web_lookup" and self.web:
            return self._dispatch("🌐 web_lookup", message, tool_use,
                                   self.web.handle(tool_use.input),
                                   intent="web_lookup")

        if tool_use and tool_use.name == "code_generation" and self.code:
            return self._dispatch("⌨️  code_generation", message, tool_use,
                                   self.code.handle(tool_use.input),
                                   intent="code_generation")

        # No tool: a plain text reply (general chat, or tutoring in study mode).
        reply = "".join(
            b.text for b in message.content if b.type == "text"
        ).strip()
        self.history.append({"role": "assistant", "content": message.content})
        self._trim_history()
        if self.study_mode and self.study:
            self.study.note_topic(user_text)
            log.info("📚 [study] Jarvis: %s", reply)
            self._log("study", reply)
        else:
            log.info("💬 [chat] Jarvis: %s", reply)
            self._log("general_chat", reply)
        return SkillResult(reply)

    def _wipe_memory(self) -> SkillResult:
        result = self.memory.clear()
        self.memory_context = ""  # stop injecting now-deleted notes this session
        return result

    def _handle_study_toggle(self, tool_use) -> SkillResult:
        action = (tool_use.input or {}).get("action")
        # Start each mode with a clean conversation so sessions don't bleed.
        self.history = []
        if action == "exit":
            self.study_mode = False
            return self.study.exit()
        self.study_mode = True
        return self.study.enter()

    def confirm(self, answer) -> SkillResult:
        """Resolve a pending destructive action from a spoken yes/no."""
        pending, self._pending = self._pending, None
        if pending is None:
            return self.handle(answer)

        text = (answer or "").strip().lower()
        affirmative = any(word in text for word in _AFFIRMATIVE)
        if affirmative:
            log.info("✅ Confirmation received — executing.")
            return as_result(pending())
        log.info("🚫 Cancelled (no confirmation).")
        return SkillResult("Okay, cancelled. I won't do that.")

    def cancel_pending(self) -> SkillResult:
        """Abort any pending action (e.g. on a silent/timed-out confirmation)."""
        self._pending = None
        return SkillResult("Cancelled.")

    @property
    def awaiting_confirmation(self) -> bool:
        return self._pending is not None

    # -- internals ---------------------------------------------------------
    def _log(self, intent, response):
        """Persist an exchange to long-term memory (if enabled)."""
        if self.memory and self._current_user:
            self.memory.log_exchange(self._current_user, response, intent)
            self.memory.maybe_summarize()

    def _dispatch(self, tag, message, tool_use, skill_value, intent=None,
                  log_memory=True) -> SkillResult:
        log.info("%s %s", tag, tool_use.input)
        result = as_result(skill_value)

        # Record the tool exchange so follow-up turns keep context. Use the
        # confirmation prompt (or final speech) as the tool_result content.
        self.history.append({"role": "assistant", "content": message.content})
        self.history.append(
            {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": tool_use.id,
                        "content": result.speech,
                    }
                ],
            }
        )
        self._trim_history()

        if result.needs_confirmation:
            self._pending = result.pending
            log.info("⚠️  Awaiting confirmation: %s", result.speech)
        else:
            log.info("💬 Jarvis: %s", result.speech)
            if log_memory:
                self._log(intent, result.speech)
        return result

    def _trim_history(self):
        # Keep history bounded. Trim from the front, but never start the
        # window on an orphaned tool_result (which the API rejects). Study mode
        # keeps a longer window so the tutor can recall earlier topics.
        limit = 60 if self.study_mode else 20
        if len(self.history) > limit:
            self.history = self.history[-limit:]
            while self.history and _is_tool_result(self.history[0]):
                self.history.pop(0)


def _recall_args(tool_input):
    ti = tool_input or {}
    return {"query": ti.get("query"), "when": ti.get("when")}


def _is_tool_result(msg):
    content = msg.get("content")
    return (
        isinstance(content, list)
        and content
        and isinstance(content[0], dict)
        and content[0].get("type") == "tool_result"
    )
