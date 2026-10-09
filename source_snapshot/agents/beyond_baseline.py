"""Keep agents on what a competent clinician is most likely to miss, not on what they know.

Rules, scores and guidelines are the floor: the attending already knows them and is shown
every deterministic alert before any model runs. An agent that spends its answer
restating them adds review burden and no information. This module holds

* the value-add standard every specialist and the synthesizer is held to,
* the "already known" block that tells an agent what the clinician has been shown,
* deterministic merging of the insights specialists return.

An alert is a floor, not a conclusion: telling an agent a pattern matched must not stop it
considering the diagnoses that pattern does not explain.
"""

from __future__ import annotations

import re
from typing import Any, Iterable, Mapping

BEYOND_BASELINE_KINDS = (
    "discordant_finding",
    "trend_or_timing",
    "patient_specific_hazard",
    "alternative_diagnosis",
    "missing_high_yield_data",
    "guidance_does_not_fit",
)

VALUE_ADD_STANDARD = """\
VALUE-ADD STANDARD:
The attending already knows standard guidelines, the usual scores, and every alert listed
under ALREADY KNOWN. Do not spend your answer restating them. Spend it on what a busy,
competent clinician is most likely to miss on THIS patient, and put each such point in
`beyond_baseline`:
- discordant_finding: a finding that does NOT fit the leading diagnosis. Name it.
- trend_or_timing: a change over time, or a contradiction between two supplied data points.
- patient_specific_hazard: a drug-drug, drug-disease, organ-function dosing or allergy
  cross-reactivity problem for this patient.
- alternative_diagnosis: a diagnosis, common or uncommon, that explains more of the findings
  than the obvious one. Say which findings support it and the single test that separates it
  from the leading diagnosis.
- missing_high_yield_data: the one absent datum that would most change management.
- guidance_does_not_fit: where standard guidance should be modified or not applied for this
  patient, and why.
Rules for `beyond_baseline`:
1. Every item needs `basis` (the specific patient facts or supplied evidence IDs it rests on)
   and a concrete `suggested_action`.
2. Never pad. If standard care covers the case and you see nothing beyond it, return an empty
   list. A short honest list beats a long generic one.
3. Do not restate an alert or a guideline as an insight.
4. A matched rule or alert is a floor, not a conclusion: keep considering the diagnoses it
   does not explain.
5. Keep standard-of-care actions brief, in the normal treatment and workup fields.
6. At most 4 `beyond_baseline` items; each insight and action is one or two sentences.

LENGTH BUDGET:
Answers that run past the output limit are cut off and discarded, so stay well inside it.
Keep the whole JSON under about 1,200 words: one-sentence rationales, at most 4
differentials, 5 stat and 4 routine workup items, 5 treatments, and short lists elsewhere.
Prefer the few points that change management over completeness.
"""

BEYOND_BASELINE_SCHEMA_FIELD = """\
  "beyond_baseline": [
    {
      "kind": "discordant_finding" | "trend_or_timing" | "patient_specific_hazard" | "alternative_diagnosis" | "missing_high_yield_data" | "guidance_does_not_fit",
      "insight": "<what a busy clinician is likely to miss, specific to THIS patient>",
      "basis": ["<specific patient fact or supplied evidence ID this rests on>"],
      "suggested_action": "<concrete next step>"
    }
  ],"""


def known_to_clinician_block(
    findings: Iterable[Mapping[str, Any]] = (),
    emergency_hits: Iterable[Mapping[str, Any]] = (),
) -> str:
    """What the clinician has already been shown, so the agent builds on it. Empty if nothing."""
    lines = [f"- {item.get('message', item)}" for item in findings]
    lines += [
        f"- Emergency pattern matched: {hit.get('title', hit.get('rule_id'))}"
        for hit in emergency_hits
    ]
    if not lines:
        return ""
    return (
        "ALREADY KNOWN TO THE TREATING CLINICIAN (shown to them as alerts before you ran; "
        "do not restate, build on it and look past it):\n" + "\n".join(lines)
    )


_NORMALISE = re.compile(r"[^a-z0-9]+")


def _signature(item: Mapping[str, Any]) -> tuple[str, str]:
    text = _NORMALISE.sub(" ", str(item.get("insight", "")).lower()).strip()
    return str(item.get("kind", "")), " ".join(text.split()[:12])


def merge_insights(
    groups: Iterable[Iterable[Mapping[str, Any]]],
    limit: int = 8,
) -> list[dict[str, Any]]:
    """Flatten and de-duplicate insights across specialists, keeping first-seen order.

    Deterministic fallback for when the synthesizer is unavailable or returns none, so a
    specialist's insight is not lost because a later stage failed. Duplicates are judged on
    kind plus the first words of the insight; nothing is rewritten.
    """
    seen: set[tuple[str, str]] = set()
    merged: list[dict[str, Any]] = []
    for group in groups:
        for item in group:
            if not isinstance(item, Mapping):
                continue
            key = _signature(item)
            if not key[1] or key in seen:
                continue
            seen.add(key)
            merged.append(dict(item))
            if len(merged) >= limit:
                return merged
    return merged
