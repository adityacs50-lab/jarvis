"""Intent router: decides whether a request is music control or general chat.

Uses a single Claude call with tool use (function calling). Claude either:
  - calls the `music_control` tool (with structured action + params), which we
    dispatch to the Spotify skill, or
  - returns a normal text reply for general conversation.

This means intent classification and parameter extraction happen in one step,
using Claude's native tool use rather than hand-rolled string parsing.
"""
import logging

import config
from skills.spotify_skill import MUSIC_CONTROL_TOOL

log = logging.getLogger("jarvis.router")


class IntentRouter:
    def __init__(self, spotify_skill=None):
        from anthropic import Anthropic

        if not config.ANTHROPIC_API_KEY:
            raise RuntimeError(
                "ANTHROPIC_API_KEY is not set. Add it to your .env file."
            )
        self.client = Anthropic(api_key=config.ANTHROPIC_API_KEY)
        self.spotify = spotify_skill
        self.history = []

        # Only advertise the music tool if Spotify is actually available.
        self.tools = [MUSIC_CONTROL_TOOL] if spotify_skill else []

    def handle(self, user_text):
        """Process one user utterance. Returns the spoken response string."""
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

        if tool_use and tool_use.name == "music_control":
            return self._handle_music(message, tool_use)

        # General chat: speak Claude's text reply.
        reply = "".join(
            b.text for b in message.content if b.type == "text"
        ).strip()
        self.history.append({"role": "assistant", "content": message.content})
        self._trim_history()
        log.info("💬 [chat] Jarvis: %s", reply)
        return reply

    def _handle_music(self, message, tool_use):
        log.info("🎵 [music_control] %s", tool_use.input)
        result = self.spotify.handle(tool_use.input)

        # Record the tool exchange so follow-up turns have context.
        self.history.append({"role": "assistant", "content": message.content})
        self.history.append(
            {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": tool_use.id,
                        "content": result,
                    }
                ],
            }
        )
        self._trim_history()
        log.info("💬 [music] Jarvis: %s", result)
        # The skill already returns a short, speakable confirmation, so we
        # speak it directly rather than making another Claude round-trip.
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
