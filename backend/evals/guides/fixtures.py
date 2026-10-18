"""Fixture schemas for the accuracy check (contracts/accuracy-check.md §Inputs) and a loader.

Layout under ``backend/evals/guides/``:

- ``facts/<raid|mplus>/<Class>-<Spec>.json`` — a list of ``FactCase``
- ``adversarial/<case>.json``               — one ``AdversarialCase``
- ``coaching/<id>.json``                    — one ``CoachingCase``
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

ROOT = Path(__file__).resolve().parent
ContentType = Literal["raid", "mplus"]

UNVERIFIED = "UNVERIFIED — maintainer must hand-check against the live game"


def _compile_all(patterns: list[str]) -> list[str]:
    for p in patterns:
        re.compile(p)  # fail loudly on a bad fixture
    return patterns


class FactCase(BaseModel):
    """One checkable statement about a guide (FR-021)."""

    id: str
    statement: str
    expected: Literal["present", "absent"]
    match: list[str] = Field(min_length=1)  # regexes: the fact is stated
    contradict: list[str] = []  # regexes: the guide says the opposite
    notes: str = UNVERIFIED

    @field_validator("match", "contradict")
    @classmethod
    def _valid_regexes(cls, v: list[str]) -> list[str]:
        return _compile_all(v)


class FactFile(BaseModel):
    class_name: str
    spec: str
    content_type: ContentType
    facts: list[FactCase]

    @property
    def key(self) -> tuple[str, str, str]:
        return self.class_name, self.spec, self.content_type


class AdversarialCase(BaseModel):
    """A misleading situation and the outcome a correct system produces (FR-021).

    ``check`` names the evaluator in ``adversarial.py``; ``inputs`` and ``expected`` are
    evaluator-specific.
    """

    case: str
    description: str
    check: str
    content_type: ContentType = "raid"
    inputs: dict[str, Any] = {}
    expected: dict[str, Any] = {}


class ExpectedPoint(BaseModel):
    id: str
    kind: Literal["raise", "not_contradict"]
    match: list[str] = []
    contradict: list[str] = []
    notes: str = UNVERIFIED

    @field_validator("match", "contradict")
    @classmethod
    def _valid_regexes(cls, v: list[str]) -> list[str]:
        return _compile_all(v)


class CoachingCase(BaseModel):
    """One coaching question on a real log, with what a good answer raises (FR-022)."""

    id: str
    report_code: str
    fight_id: int | None = None
    player: str
    class_name: str
    spec: str
    content_type: ContentType
    question: str
    expected_points: list[ExpectedPoint] = Field(min_length=1)
    notes: str = UNVERIFIED


def _read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_facts(root: Path = ROOT) -> list[FactFile]:
    files: list[FactFile] = []
    for content_type in ("raid", "mplus"):
        for path in sorted((root / "facts" / content_type).glob("*.json")):
            class_name, _, spec = path.stem.partition("-")
            files.append(
                FactFile(
                    class_name=class_name,
                    spec=spec,
                    content_type=content_type,
                    facts=[FactCase.model_validate(f) for f in _read(path)],
                )
            )
    return files


def load_adversarial(root: Path = ROOT) -> list[AdversarialCase]:
    return [
        AdversarialCase.model_validate(_read(p)) for p in sorted((root / "adversarial").glob("*.json"))
    ]


def load_coaching(root: Path = ROOT) -> list[CoachingCase]:
    return [
        CoachingCase.model_validate(_read(p)) for p in sorted((root / "coaching").glob("*.json"))
    ]


def load_all(root: Path = ROOT) -> tuple[list[FactFile], list[AdversarialCase], list[CoachingCase]]:
    """Validate every fixture file; raises on the first invalid one."""
    return load_facts(root), load_adversarial(root), load_coaching(root)
