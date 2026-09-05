"""Generic condition matcher skeleton for Iteration 1."""
from typing import Dict, Any, List
from app.policies.models import SOPRule, CandidateSOP


def match_candidate_sops(
    sops: List[SOPRule],
    facts: Dict[str, Any]
) -> List[CandidateSOP]:
    """
    Placeholder: matches facts against generic condition trees across all SOPs.
    Full generic condition engine scheduled for Iteration 2.
    """
    raise NotImplementedError("Generic condition matcher will be implemented in Iteration 2.")
