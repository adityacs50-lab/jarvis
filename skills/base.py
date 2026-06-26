"""Shared types for Jarvis skills."""
from dataclasses import dataclass
from typing import Callable, Optional


@dataclass
class SkillResult:
    """The outcome of a skill action.

    speech:
        The short text Jarvis should say.
    pending:
        If set, the action is destructive and needs confirmation. Calling
        ``pending()`` performs the real action and returns a follow-up
        SkillResult (or plain string) to speak once confirmed.
    """

    speech: str
    pending: Optional[Callable[[], "SkillResult | str"]] = None

    @property
    def needs_confirmation(self) -> bool:
        return self.pending is not None


def as_result(value) -> SkillResult:
    """Normalize a skill return value (str or SkillResult) to a SkillResult."""
    if isinstance(value, SkillResult):
        return value
    return SkillResult(speech=str(value))
