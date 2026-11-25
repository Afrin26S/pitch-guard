from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

Severity = Literal["low", "medium", "high", "critical"]
SEV_RANK = {"low": 1, "medium": 2, "high": 3, "critical": 4}
SEV_WEIGHT = {"low": 5, "medium": 12, "high": 25, "critical": 40}

CATEGORIES = [
    "AI_DISCLOSURE", "GUARANTEE", "URGENCY", "PRESSURE", "THREAT", "PRIVACY",
    "MISSING_DISCLOSURE", "CALL_HOURS", "FALSE_CLAIM", "NUMBER_MISMATCH",
]


class Fact(BaseModel):
    id: str
    text: str
    ranges: list[tuple[float, float]] = Field(default_factory=list)


class Product(BaseModel):
    id: str
    name: str
    facts: list[Fact]


class Turn(BaseModel):
    speaker: Literal["bot", "customer"]
    text: str


class Label(BaseModel):
    turn: Optional[int] = None          # None = whole-call label
    category: str


class Call(BaseModel):
    id: str
    title: str
    scenario: str
    product: str
    time: Optional[str] = None          # local call time "HH:MM"
    turns: list[Turn]
    account_facts: list[Fact] = Field(default_factory=list)
    labels: list[Label] = Field(default_factory=list)


class Violation(BaseModel):
    turn: Optional[int] = None
    rule_id: str
    category: str
    severity: Severity
    message: str
    evidence: str = ""
    source: Literal["rule", "llm", "number_check"] = "rule"
    fix_hint: str = ""
    fact_id: Optional[str] = None
    fact_quote: Optional[str] = None


class TurnResult(BaseModel):
    turn: int
    speaker: str
    text: str
    violations: list[Violation] = Field(default_factory=list)
    rewrite: Optional[str] = None
    llm_checked: bool = False


class CallReport(BaseModel):
    call_id: str
    title: str
    scenario: str
    mode: Literal["rules", "full"]
    score: int
    verdict: Literal["PASS", "REVIEW", "BLOCK"]
    turns: list[TurnResult]
    call_violations: list[Violation] = Field(default_factory=list)
    elapsed_ms: float = 0.0

    def all_violations(self) -> list[Violation]:
        return [v for t in self.turns for v in t.violations] + self.call_violations
