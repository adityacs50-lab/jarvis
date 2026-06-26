"""Intent router: classify each utterance and dispatch to the right skill.

A single Claude call with tool use decides between three intents:
  - music_control   -> Spotify skill
  - system_control  -> System skill (apps, websites, files)
  - general_chat    -> plain text reply

Claude's native tool use does both intent classification and structured
parameter extraction in one step (no hand-rolled string parsing).

Destructive system actions (delete) come back as a SkillResult with a pending
callable. The router speaks a confirmation prompt and waits; the next utterance
is interpreted as yes/no via `confirm()` before anything is executed.
"""
import logging

import config
from skills.base import SkillResult, as_result
from skills.spotify_skill import MUSIC_CONTROL_TOOL
from skills.system_skill import SYSTEM_CONTROL_TOOL

log = logging.getLogger("jarvis.router")

_AFFIRMATIVE = {
    "yes", "yeah", "yep", "yup", "sure", "confirm", "confirmed", "do it",
    "go ahead", "ok", "okay", "affirmative", "please do", "correct",
}


class IntentRouter:
    def __init__(self, spotify_skill=None, system_skill=None):
        from anthropic import Anthropic

        if not config.ANTHROPIC_API_KEY:
            raise RuntimeError(
                "ANTHROPIC_API_KEY is not set. Add it to your .env file."
            )
        self.client = Anthropic(api_key=config.ANTHROPIC_API_KEY)
        self.spotify = spotify_skill
        self.system = system_skill
        self.history = []
        self._pending = None  # callable awaiting spoken confirmation

        # Only advertise tools whose skills are actually available.
        self.tools = []
        if spotify_skill:
            self.tools.append(MUSIC_CONTROL_TOOL)
        if system_skill:
            self.tools.append(SYSTEM_CONTROL_TOOL)

    # -- public API --------------------------------------------------------
    def handle(self, user_text) -> SkillResult:
        """Process one utterance. Returns a SkillResult to speak.

        If the result `needs_confirmation`, the caller should record a yes/no
        answer and pass it to `confirm()`.
        """
        # If we're mid-confirmation, treat this utterance as the answer.
        if self._pending is not None:
            return self.confirm(user_text)

        log.info("🧭 Routing intent...")
        self.history.append({"role": "user", "content": user_text})

        message = self.client.messages.create(
            model=config.CLAUDE_MODEL,
            max_tokens=config.CLAUDE_MAX_TOKENS,
            system=config.SYSTEM_PROMPT,
            tools=self.tools,
            messages=self.history,
        )

        tool_use = next(
            (b for b in message.content if b.type == "tool_use"), None
        )

        if tool_use and tool_use.name == "music_control" and self.spotify:
            return self._dispatch("🎵 music_control", message, tool_use,
                                   self.spotify.handle(tool_use.input))

        if tool_use and tool_use.name == "system_control" and self.system:
            return self._dispatch("🖥️  system_control", message, tool_use,
                                   self.system.handle(tool_use.input))

        # General chat: speak Claude's text reply.
        reply = "".join(
            b.text for b in message.content if b.type == "text"
        ).strip()
        self.history.append({"role": "assistant", "content": message.content})
        self._trim_history()
        log.info("💬 [chat] Jarvis: %s", reply)
        return SkillResult(reply)

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
    def _dispatch(self, tag, message, tool_use, skill_value) -> SkillResult:
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
        return result

    def _trim_history(self):
        # Keep history bounded. Trim from the front, but never start the
        # window on an orphaned tool_result (which the API rejects).
        if len(self.history) > 20:
            self.history = self.history[-20:]
            while self.history and _is_tool_result(self.history[0]):
                self.history.pop(0)


def _is_tool_result(msg):
    content = msg.get("content")
    return (
        isinstance(content, list)
        and content
        and isinstance(content[0], dict)
        and content[0].get("type") == "tool_result"
    )
