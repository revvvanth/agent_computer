"""
eval.core.insight_evaluator
===========================
Does the agent add value beyond what the clinician already knows?

Safety gates ask "did the agent say something unsafe?". They cannot tell a useful agent from
one that recites guidelines, because reciting is safe. This evaluator measures the other
side: on a case with a known non-obvious problem (a drug interaction hidden in the med list,
a finding that does not fit the obvious diagnosis), does the agent surface it in
``beyond_baseline``, and on a standard case does it stay quiet instead of padding?

A case declares:

* ``planted_insights``: the non-obvious things a good agent must raise. Each lists
  ``any_terms``, alternative term-sets; an insight is *surfaced* when one term-set has every
  term present in a single ``beyond_baseline`` item. Mentioning it elsewhere (assessment
  prose, treatment list) does not count: the point is that it is flagged as a finding.
* ``baseline_statements``: what any clinician or guideline already says, as term-sets. A
  ``beyond_baseline`` item that matches one of these and no planted insight is *padding*.

Matching is deterministic keyword matching so CI can run it offline. It is a floor under
the live evaluation (recorded model outputs scored here), not a substitute for clinician
review of whether an insight is correct.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Sequence

MIN_INSIGHT_RECALL = 1.0       # every planted insight must be surfaced
MAX_PADDING_RATIO = 0.34       # at most about a third of the items may restate baseline
MAX_ITEMS_WITHOUT_INSIGHT = 1  # a case with nothing planted should get (almost) nothing

_TOKEN = re.compile(r"[a-z0-9]+")


def _text(item: Mapping[str, Any]) -> str:
    parts = [item.get("insight", ""), item.get("suggested_action", "")]
    parts += [str(b) for b in (item.get("basis") or [])]
    return " ".join(str(p) for p in parts).lower()


def _matches(text: str, term_sets: Sequence[Sequence[str]]) -> bool:
    """True if any term-set has all of its terms in the text (substring, case-insensitive)."""
    return any(terms and all(term.lower() in text for term in terms) for terms in term_sets)


@dataclass(frozen=True)
class InsightScore:
    case_id: str
    n_items: int
    surfaced: List[str]
    missed: List[str]
    recall: float
    padding_items: int
    padding_ratio: float
    ungrounded_items: int
    passed: bool
    reasons: List[str] = field(default_factory=list)


def score_value_add(
    case: Mapping[str, Any],
    output: Mapping[str, Any],
    *,
    min_recall: float = MIN_INSIGHT_RECALL,
    max_padding_ratio: float = MAX_PADDING_RATIO,
    max_items_without_insight: int = MAX_ITEMS_WITHOUT_INSIGHT,
) -> InsightScore:
    planted: List[Mapping[str, Any]] = list(case.get("planted_insights") or [])
    baseline: List[Sequence[str]] = list(case.get("baseline_statements") or [])
    items = [i for i in (output.get("beyond_baseline") or []) if isinstance(i, Mapping)]
    texts = [_text(i) for i in items]

    surfaced = [
        p["id"] for p in planted
        if any(_matches(t, p.get("any_terms") or []) for t in texts)
    ]
    missed = [p["id"] for p in planted if p["id"] not in surfaced]
    recall = len(surfaced) / len(planted) if planted else 1.0

    all_planted_terms = [ts for p in planted for ts in (p.get("any_terms") or [])]
    padding = sum(
        1 for t in texts
        if _matches(t, baseline) and not _matches(t, all_planted_terms)
    )
    padding_ratio = padding / len(items) if items else 0.0
    ungrounded = sum(1 for i in items if not i.get("basis"))

    reasons: List[str] = []
    if recall < min_recall:
        reasons.append(f"missed planted insights: {', '.join(missed)}")
    if padding_ratio > max_padding_ratio:
        reasons.append(f"{padding} of {len(items)} items restate baseline care")
    if ungrounded:
        reasons.append(f"{ungrounded} items name no supporting patient fact")
    if not planted and len(items) > max_items_without_insight:
        reasons.append(f"{len(items)} insights offered on a case with nothing beyond standard care")

    return InsightScore(
        case_id=str(case.get("case_id", "")),
        n_items=len(items),
        surfaced=surfaced,
        missed=missed,
        recall=recall,
        padding_items=padding,
        padding_ratio=padding_ratio,
        ungrounded_items=ungrounded,
        passed=not reasons,
        reasons=reasons,
    )


def format_score(score: InsightScore) -> str:
    verdict = "PASS" if score.passed else "FAIL"
    detail = f" ({'; '.join(score.reasons)})" if score.reasons else ""
    return (
        f"[{verdict}] {score.case_id}: recall {score.recall:.2f}, "
        f"padding {score.padding_items}/{score.n_items}, ungrounded {score.ungrounded_items}{detail}"
    )
