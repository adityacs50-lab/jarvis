"""Web lookup skill: live internet access via Claude's built-in web search.

When triggered, this makes a Claude call with the server-side
`web_search_20250305` tool enabled, so Claude itself performs the searches and
synthesizes a short, spoken-friendly answer. We only read back the final text.
"""
import logging

import config
from skills.base import SkillResult

log = logging.getLogger("jarvis.web")

# The hosted web-search tool. max_uses caps searches per request for latency.
WEB_SEARCH_TOOL = {
    "type": "web_search_20250305",
    "name": "web_search",
    "max_uses": 4,
}

# Tool the router exposes so Claude can ask for a live lookup.
WEB_LOOKUP_TOOL = {
    "name": "web_lookup",
    "description": (
        "Look up CURRENT, real-time, or factual information on the internet and "
        "answer from it. Use this LIBERALLY — it is the default whenever you are "
        "not highly confident the answer is timeless, static knowledge. Trigger "
        "it for: weather, news, sports scores/results, prices, stock/crypto, "
        "'who is the current X', 'what's the latest/newest X', release dates, "
        "anything about 'now/today/current/latest/recent', and ANY named person, "
        "company, product, place, or event you aren't certain is unchanging. "
        "When in doubt, prefer this tool over answering from memory — searching "
        "unnecessarily is harmless, but answering stale info is not. Do NOT use "
        "it for genuinely timeless things (math, definitions, coding help, "
        "jokes, casual chat, explaining a concept)."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": (
                    "The thing to look up, phrased as a clear search query or "
                    "question, e.g. 'weather in Tokyo today', 'current US "
                    "president', 'latest iPhone price'."
                ),
            }
        },
        "required": ["query"],
    },
}

_SEARCH_SYSTEM_PROMPT = (
    "You are Jarvis, a witty, concise voice assistant. Use web search to answer "
    "the user's question with CURRENT information. Your answer will be spoken "
    "aloud, so reply in 1-3 short sentences of plain prose. Do NOT read out URLs, "
    "citations, or source names. Do NOT write lists, markdown, or long reports. "
    "If the search turns up nothing useful or you can't find a solid answer, say "
    "something natural like \"I couldn't find anything solid on that.\" — never "
    "make up facts."
)

_NO_RESULT = "I couldn't find anything solid on that."


class WebSkill:
    def __init__(self):
        from anthropic import Anthropic

        if not config.ANTHROPIC_API_KEY:
            raise RuntimeError(
                "ANTHROPIC_API_KEY is not set. Add it to your .env file."
            )
        self.client = Anthropic(api_key=config.ANTHROPIC_API_KEY)
        log.info("Web lookup skill initialized (Claude web_search).")

    def handle(self, tool_input):
        """Run a live lookup. Returns SkillResult. Never raises."""
        query = (tool_input or {}).get("query", "").strip()
        if not query:
            return SkillResult("What would you like me to look up?")

        log.info("🌐 Searching the web for: %s", query)
        try:
            message = self.client.messages.create(
                model=config.CLAUDE_MODEL,
                max_tokens=config.CLAUDE_MAX_TOKENS,
                system=_SEARCH_SYSTEM_PROMPT,
                tools=[WEB_SEARCH_TOOL],
                messages=[{"role": "user", "content": query}],
            )
        except Exception as e:  # pragma: no cover - network/API issues
            log.warning("Web search failed: %s", e)
            return SkillResult(
                "I had trouble reaching the internet just now. Try again in a moment."
            )

        # Collect only the final text blocks (skip search tool-use/result blocks).
        answer = "".join(
            b.text for b in message.content if getattr(b, "type", None) == "text"
        ).strip()

        if not answer:
            return SkillResult(_NO_RESULT)
        return SkillResult(answer)
