"""Study Mode: an adaptive Socratic tutoring mode for engineering coursework.

This is a *mode*, not a one-shot action. When active, the router swaps the
normal assistant system prompt for the tutoring prompt below and stops
advertising the code-generation skill, so coursework questions get taught
rather than turned into files. The skill owns the tutoring prompt, the
enter/exit announcements, and lightweight per-session topic tracking.

The actual conversational memory is the router's running message history, which
is what lets the tutor say things like "like we discussed with segment trees
earlier" — those turns are still in context.
"""
import logging

from skills.base import SkillResult

log = logging.getLogger("jarvis.study")

# Tool the router exposes so Claude can toggle study mode on a voice command.
STUDY_MODE_TOOL = {
    "name": "study_mode",
    "description": (
        "Turn Study Mode on or off. Use ONLY for explicit requests like 'enter "
        "study mode', 'start studying', 'let's study', or 'exit study mode', "
        "'stop studying', 'I'm done studying'. Not for normal questions."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["enter", "exit"],
                "description": "Whether to enter or exit study mode.",
            }
        },
        "required": ["action"],
    },
}

# The tutoring persona. Swapped in for the normal system prompt while active.
TUTOR_SYSTEM_PROMPT = (
    "You are Jarvis in Study Mode: a patient, Socratic tutor for an engineering "
    "student (data structures, algorithms, OOP, math, systems, etc.). Your goal "
    "is to help them UNDERSTAND, not to hand over answers.\n\n"
    "Tutoring principles:\n"
    "- Be Socratic. When the student is stuck on a problem, ask one clarifying "
    "or leading question first to find where their understanding breaks down, "
    "before giving the full solution.\n"
    "- Default to hints and partial explanations before full answers. Reveal "
    "more only as needed. BUT if the student explicitly says something like "
    "'just give me the answer' or 'I don't have time, explain it directly', "
    "skip the Socratic step and give a clear, direct explanation.\n"
    "- Build from first principles: start with intuition and a simple concrete "
    "example, then generalize to the formal definition — not the reverse.\n"
    "- For coding coursework (DSA, OOP), encourage the student to write the code "
    "themselves. Offer to review or debug what they write. Do NOT write the full "
    "solution file for them — guide them to it. Walking through a small snippet "
    "to illustrate an idea is fine.\n"
    "- This is spoken aloud: keep each turn reasonably short, but it's okay to "
    "go longer when they're genuinely asking for a real explanation rather than "
    "a quick check. Avoid markdown, bullet dumps, and reading out long code.\n"
    "- You have the running conversation in context. Reference earlier topics "
    "when relevant ('like we said about hash collisions earlier') to connect "
    "ideas across the session."
)

# Asked once when entering, to calibrate pacing for the session.
_CALIBRATION = (
    "What are we working on today, and are we doing a quick concept check or "
    "going deep?"
)


class StudySkill:
    def __init__(self):
        self.topics = []          # raw questions seen this session
        self._session_open = False

    @property
    def tutor_system_prompt(self):
        return TUTOR_SYSTEM_PROMPT

    def enter(self):
        """Begin a fresh study session. Returns the spoken announcement."""
        self.topics = []
        self._session_open = True
        log.info("📚 Study mode ON — new session.")
        return SkillResult("Study mode on. " + _CALIBRATION)

    def exit(self):
        """End the study session. Returns the spoken announcement."""
        n = len(self.topics)
        self._session_open = False
        log.info("📚 Study mode OFF (%d topics this session).", n)
        return SkillResult("Exiting study mode. Nice work — ping me anytime.")

    def note_topic(self, user_text):
        """Record that a topic/question came up this session (in-memory)."""
        text = (user_text or "").strip()
        if text:
            self.topics.append(text)
            log.info("📚 [study] topic noted (%d this session).", len(self.topics))
