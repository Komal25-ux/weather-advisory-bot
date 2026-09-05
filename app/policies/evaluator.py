"""Deterministic decision evaluator skeleton for Iteration 1."""
from typing import List, Optional
from app.policies.models import CandidateSOP, DeterministicDecision, SOPRule


def select_primary_decision(
    candidate_sops: List[CandidateSOP],
    all_sops: List[SOPRule]
) -> Optional[DeterministicDecision]:
    """
    Placeholder: deterministically selects primary SOP using Severity > Priority > SOP ID.
    Full deterministic resolution engine scheduled for Iteration 2 / 6.
    """
    raise NotImplementedError("Deterministic evaluator will be implemented in Iteration 2/6.")
