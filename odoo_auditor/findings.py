"""Finding types shared by every rule."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Severity(str, Enum):
    """How likely a finding is to break a production database.

    ``CRITICAL`` is reserved for patterns observed to break core flows for every
    record, not just the addon's own, because those are the ones that take an
    ERP down rather than merely erroring in one view.
    """

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    INFO = "info"

    @property
    def rank(self) -> int:
        return {"critical": 0, "high": 1, "medium": 2, "info": 3}[self.value]


@dataclass(frozen=True)
class Finding:
    rule: str
    severity: Severity
    path: str
    line: int
    message: str
    # What to do about it, kept separate so output can be terse or verbose.
    remedy: str = ""
    snippet: str = ""

    def __post_init__(self) -> None:
        if self.line < 0:
            raise ValueError("line must not be negative")

    def as_dict(self) -> dict:
        return {
            "rule": self.rule,
            "severity": self.severity.value,
            "path": self.path,
            "line": self.line,
            "message": self.message,
            "remedy": self.remedy,
            "snippet": self.snippet,
        }
