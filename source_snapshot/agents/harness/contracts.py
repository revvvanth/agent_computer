"""Versioned contracts enforced at the specialist/graph boundary."""

from __future__ import annotations

import logging
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

logger = logging.getLogger("cdss.harness.contracts")


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class BeyondBaselineItem(BaseModel):
    """One thing a competent clinician is likely to miss on this patient (see agents.beyond_baseline).

    ``basis`` is mandatory: an insight that cannot name the patient facts or evidence IDs it
    rests on is an opinion, not a finding. Unknown keys are ignored, not rejected.
    """

    model_config = ConfigDict(extra="ignore")

    kind: Literal[
        "discordant_finding",
        "trend_or_timing",
        "patient_specific_hazard",
        "alternative_diagnosis",
        "missing_high_yield_data",
        "guidance_does_not_fit",
    ]
    insight: str = Field(min_length=1)
    basis: list[str] = Field(min_length=1)
    suggested_action: str = Field(min_length=1)


def _lenient_insights(value: Any, limit: int) -> list[BeyondBaselineItem]:
    """Advisory field: keep well-formed items, drop the rest, never fail the consult.

    The core clinical fields stay strictly validated. A malformed *advisory* item must not
    turn a valid specialist report into an unavailable one, so it is dropped (and logged)
    instead of raising, and an over-long list is truncated instead of rejected.
    """
    if not isinstance(value, list):
        return []
    kept: list[BeyondBaselineItem] = []
    for item in value:
        try:
            kept.append(BeyondBaselineItem.model_validate(item))
        except ValidationError:
            logger.warning("Dropped a malformed beyond_baseline item")
    return kept[:limit]


class KeyFinding(StrictModel):
    finding: str = Field(min_length=1)
    significance: str = Field(min_length=1)
    supports_primary_dx: bool


class Differential(StrictModel):
    dx: str = Field(min_length=1)
    probability: int = Field(ge=0, le=100)
    rationale: str = Field(min_length=1)


class StatWorkup(StrictModel):
    test: str = Field(min_length=1)
    rationale: str = Field(min_length=1)
    timing: str = Field(min_length=1)
    critical_threshold: str = Field(min_length=1)


class RoutineWorkup(StrictModel):
    test: str = Field(min_length=1)
    rationale: str = Field(min_length=1)


class ProposedTreatment(StrictModel):
    drug: str = Field(min_length=1)
    dose: str = Field(min_length=1)
    route: str = Field(min_length=1)
    frequency: str = Field(min_length=1)
    indication: str = Field(min_length=1)
    contraindications: list[str]


class MonitoringPlan(StrictModel):
    frequency: str
    escalate_if: list[str]
    targets: list[str]


class SpecialistOutputV1(StrictModel):
    """Only this validated shape is allowed to enter board consensus."""

    schema_version: Literal["1.0"] = "1.0"
    voice_summary: str = Field(min_length=1)
    clinical_assessment: str = Field(min_length=1)
    key_findings: list[KeyFinding]
    differential: list[Differential]
    must_not_miss: list[str]
    missing_data: list[str]
    stat_workup: list[StatWorkup]
    routine_workup: list[RoutineWorkup]
    treatment: list[ProposedTreatment]
    monitoring: MonitoringPlan
    confidence: Literal["high", "medium", "low"]
    confidence_reasoning: str = Field(min_length=1)
    evidence_references: list[str]
    beyond_baseline: list[BeyondBaselineItem] = Field(default_factory=list)

    @field_validator("beyond_baseline", mode="before")
    @classmethod
    def _advisory_insights(cls, value: Any) -> list[BeyondBaselineItem]:
        return _lenient_insights(value, limit=6)


class SafetyVerdictV1(StrictModel):
    """Strict post-consensus medication safety verdict."""

    cleared: bool
    summary: str = Field(min_length=1)
    allergy_conflicts: list[dict]
    interactions: list[dict]
    dose_adjustments: list[dict]
    additional_monitoring: list[dict]
    cumulative_risks: list[dict]
    drugs_to_remove: list[str]
    confidence: Literal["high", "medium", "low"]


class BoardPrognosisV1(StrictModel):
    """Qualitative outlook for review, without unvalidated outcome probabilities."""
    time_horizon: str = Field(max_length=200)
    outlook: str = Field(max_length=2400)
    patient_specific_drivers: list[str] = Field(default_factory=list, max_length=20)
    improvement_signs: list[str] = Field(default_factory=list, max_length=20)
    deterioration_signs: list[str] = Field(default_factory=list, max_length=20)
    uncertainties: list[str] = Field(default_factory=list, max_length=20)
    evidence_references: list[str] = Field(default_factory=list, max_length=30)


class BoardConsensusV1(StrictModel):
    """Versioned consensus shape consumed by safety and finalization."""

    schema_version: Literal["1.0"] = "1.0"
    urgency_banner: str = Field(min_length=1)
    primary_dx: dict
    differentials: list[dict]
    must_not_miss: list[str]
    management_plan: dict
    treatment_protocol: list[dict]
    monitoring_plan: dict
    disposition: dict
    specialist_consensus: dict
    guideline_basis: list[dict]
    clinical_scores_applied: list[dict]
    confidence_summary: dict
    beyond_baseline: list[BeyondBaselineItem] = Field(default_factory=list)
    prognosis: BoardPrognosisV1 | None = None

    @field_validator("beyond_baseline", mode="before")
    @classmethod
    def _advisory_insights(cls, value: Any) -> list[BeyondBaselineItem]:
        return _lenient_insights(value, limit=8)
