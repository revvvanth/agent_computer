"""Strict model actions. Identity, budgets and ancestry are runtime-owned."""

from __future__ import annotations

import os
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from agents.harness.contracts import SpecialistOutputV1


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Scope(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    tenant_id: str = Field(
        min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$"
    )
    user_id: str = Field(
        min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$"
    )
    encounter_id: str = Field(
        min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$"
    )
    document_ids: tuple[
        Annotated[
            str,
            Field(
                min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$"
            ),
        ],
        ...,
    ] = Field(default=(), max_length=40)


class Search(StrictModel):
    action: Literal["search"]
    corpus: Literal["patient", "knowledge"]
    query: str = Field(min_length=3, max_length=1500)
    top_k: int = Field(default=5, ge=1, le=8)


class Fetch(StrictModel):
    action: Literal["fetch"]
    evidence_ids: list[Annotated[str, Field(min_length=1, max_length=128)]] = Field(
        min_length=1,
        max_length=8,
    )


class AskSpecialty(StrictModel):
    action: Literal["ask_specialty"]
    specialty: str = Field(min_length=1, max_length=80)
    goal: str = Field(min_length=5, max_length=2500)
    evidence_ids: list[str] = Field(default_factory=list, max_length=16)


class Challenge(StrictModel):
    action: Literal["challenge"]
    claim: str = Field(min_length=3, max_length=2500)
    evidence_ids: list[str] = Field(default_factory=list, max_length=16)


class ChildTask(StrictModel):
    role: str = Field(min_length=1, max_length=80)
    profile: Literal["specialist", "researcher", "critic", "medication_reviewer"]
    specialty: str | None = Field(default=None, max_length=80)
    goal: str = Field(min_length=5, max_length=2500)
    evidence_ids: list[str] = Field(default_factory=list, max_length=16)


class Delegate(StrictModel):
    action: Literal["delegate"]
    children: list[ChildTask] = Field(min_length=1, max_length=3)


class Inspect(StrictModel):
    action: Literal["inspect"]
    session_id: str = Field(min_length=1, max_length=80)


class Revise(StrictModel):
    action: Literal["revise"]
    note: str = Field(min_length=1, max_length=2000)


class RequestInput(StrictModel):
    action: Literal["request_clinician_input"]
    questions: list[Annotated[str, Field(min_length=3, max_length=500)]] = Field(
        min_length=1,
        max_length=8,
    )


class ChildResult(StrictModel):
    summary: str = Field(min_length=1, max_length=6000)
    evidence_references: list[str] = Field(default_factory=list, max_length=40)
    limitations: list[str] = Field(default_factory=list, max_length=20)


class Finalize(StrictModel):
    action: Literal["finalize"]
    result: SpecialistOutputV1 | ChildResult


class CalculateClinicalScores(StrictModel):
    action: Literal["calculate_clinical_scores"]


Action = Annotated[
    CalculateClinicalScores
    | Search
    | Fetch
    | AskSpecialty
    | Challenge
    | Delegate
    | Inspect
    | Revise
    | RequestInput
    | Finalize,
    Field(discriminator="action"),
]
ACTION_ADAPTER = TypeAdapter(Action)


class Limits(StrictModel):
    max_depth: int = Field(default=2, ge=0, le=3)
    max_children: int = Field(default=5, ge=0, le=8)
    max_sessions: int = Field(default=20, ge=1, le=40)
    max_turns: int = Field(default=12, ge=1, le=32)
    max_calls: int = Field(default=80, ge=1, le=160)
    max_tools: int = Field(default=80, ge=0, le=160)
    max_parallel: int = Field(default=5, ge=1, le=8)
    max_invalid: int = Field(default=2, ge=0, le=3)
    max_context_chars: int = Field(default=48000, ge=4000, le=96000)
    # A finalize for a data-rich chart can exceed 6144 tokens and was cut off mid-JSON.
    max_output_tokens: int = Field(default=8192, ge=512, le=8192)
    # Conservative UTF-8 byte + output-token reservations, not calibrated billing.
    max_token_units: int = Field(default=1000000, ge=2000, le=4000000)
    deadline_seconds: int = Field(default=210, ge=10, le=1200)
    call_timeout_seconds: int = Field(default=150, ge=1, le=240)

    @classmethod
    def from_environment(cls) -> "Limits":
        mapping = {
            "max_depth": "CDSS_FREEFORM_MAX_DEPTH",
            "max_children": "CDSS_FREEFORM_MAX_CHILDREN",
            "max_sessions": "CDSS_FREEFORM_MAX_SESSIONS",
            "max_turns": "CDSS_FREEFORM_MAX_TURNS",
            "max_calls": "CDSS_FREEFORM_MAX_CALLS",
            "max_tools": "CDSS_FREEFORM_MAX_TOOLS",
            "max_parallel": "CDSS_FREEFORM_MAX_PARALLEL",
            "max_invalid": "CDSS_FREEFORM_MAX_INVALID",
            "max_context_chars": "CDSS_FREEFORM_MAX_CONTEXT_CHARS",
            "max_output_tokens": "CDSS_FREEFORM_MAX_OUTPUT_TOKENS",
            "max_token_units": "CDSS_FREEFORM_MAX_TOKEN_UNITS",
            "deadline_seconds": "CDSS_FREEFORM_DEADLINE_SECONDS",
            "call_timeout_seconds": "CDSS_FREEFORM_CALL_TIMEOUT_SECONDS",
        }
        values = {
            field: os.environ[variable]
            for field, variable in mapping.items()
            if os.getenv(variable, "").strip()
        }
        return cls.model_validate(values)


class CapabilityDenied(RuntimeError):
    pass


class ResourceLimited(RuntimeError):
    pass


class InvestigationIncomplete(RuntimeError):
    pass


class FreeFormExecutionError(RuntimeError):
    """Expose a PHI-safe failure trace without returning partial clinical work."""

    def __init__(self, error_type: str, trace: dict) -> None:
        super().__init__("free-form specialist investigation failed")
        self.error_type = error_type
        self.trace = trace
