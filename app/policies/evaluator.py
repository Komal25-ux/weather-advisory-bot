import logging
from typing import List, Optional, Dict
from app.policies.models import (
    CandidateSOP,
    DeterministicDecision,
    SOPRule,
    SeverityLevel,
)

logger = logging.getLogger("weather-advisory-bot.policies.evaluator")

SEVERITY_WEIGHTS: Dict[SeverityLevel, int] = {
    "CRITICAL": 4,
    "HIGH": 3,
    "MEDIUM": 2,
    "LOW": 1,
}


def _ranking_key(candidate: CandidateSOP):
    """
    Deterministic sorting tuple:
    1. Severity weight (descending)
    2. Priority (descending)
    3. SOP ID (ascending alphanumeric)
    """
    severity_rank = SEVERITY_WEIGHTS.get(candidate.severity, 0)
    return (-severity_rank, -candidate.priority, candidate.sop_id)


def select_primary_decision(
    candidate_sops: List[CandidateSOP],
    all_sops: List[SOPRule]
) -> Optional[DeterministicDecision]:
    """
    Selects exactly one primary SOP decision using deterministic rules:
    Severity (CRITICAL > HIGH > MEDIUM > LOW) -> Priority (desc) -> SOP ID (asc).

    Returns None if candidate_sops is empty.
    """
    if not candidate_sops:
        return None

    # Sort deterministically
    sorted_candidates = sorted(candidate_sops, key=_ranking_key)
    winning_candidate = sorted_candidates[0]

    # Map back to full SOP definition for advice and rationale
    sop_lookup = {sop.id: sop for sop in all_sops}
    full_sop = sop_lookup.get(winning_candidate.sop_id)

    if not full_sop:
        logger.error(f"Matched SOP ID '{winning_candidate.sop_id}' not found in loaded SOP collection.")
        return None

    # Generate human-readable decision trace
    condition_snippets = [
        f"{c.field} ({c.actual}) {c.operator} {c.threshold}"
        for c in winning_candidate.matched_conditions
    ]
    trace_str = " AND ".join(condition_snippets) if condition_snippets else "Conditions met"

    return DeterministicDecision(
        sop_id=full_sop.id,
        sop_name=full_sop.name,
        severity=full_sop.severity,
        recommendation=full_sop.advice.recommendation,
        priority=full_sop.priority,
        matched_conditions=winning_candidate.matched_conditions,
        applicable_sop_ids=[c.sop_id for c in candidate_sops],
        guidance=full_sop.advice.guidance,
        rationale=full_sop.advice.rationale,
        decision_trace=trace_str
    )
