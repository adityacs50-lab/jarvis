"""Send transcribed text to the Anthropic Claude API and get a short reply."""
import logging

import config

log = logging.getLogger("jarvis.llm")


class Brain:
    def __init__(self):
        from anthropic import Anthropic

        if not config.ANTHROPIC_API_KEY:
            raise RuntimeError(
                "ANTHROPIC_API_KEY is not set. Add it to your .env file."
            )
        self.client = Anthropic(api_key=config.ANTHROPIC_API_KEY)
        # Keep a short rolling conversation history for context.
        self.history = []

    def ask(self, user_text):
        log.info("🤔 Thinking...")
        self.history.append({"role": "user", "content": user_text})

        message = self.client.messages.create(
            model=config.CLAUDE_MODEL,
            max_tokens=config.CLAUDE_MAX_TOKENS,
            system=config.SYSTEM_PROMPT,
            messages=self.history,
        )
        reply = "".join(
            block.text for block in message.content if block.type == "text"
        ).strip()

        self.history.append({"role": "assistant", "content": reply})
        # Cap history so context doesn't grow unbounded (keep last 10 turns).
        if len(self.history) > 20:
            self.history = self.history[-20:]

        log.info("💬 Jarvis: %s", reply)
        return reply
