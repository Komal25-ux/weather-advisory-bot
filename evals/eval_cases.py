"""
Data models and case specifications for the Weather-Advisory Evaluation Suite.
"""
from typing import Optional, Dict, Any, Literal
from pydantic import BaseModel, Field


class EvalCaseResult(BaseModel):
    """Execution output and audit result for an evaluation case."""
    case_id: str
    title: str
    user_input: str
    setup_environment: str
    what_is_checked: str
    expected_behavior: str
    pass_criteria: str
    actual_result: Dict[str, Any] = Field(default_factory=dict)
    status: Literal["PASS", "FAIL"] = "PASS"
    honest_notes: str = ""
    timestamp: str = ""
    evaluation_type: Literal["unit_evaluation", "end_to_end_behavioral"] = "end_to_end_behavioral"


class EvalSummary(BaseModel):
    """Overall evaluation run summary."""
    run_timestamp: str
    total_cases: int
    passed_cases: int
    failed_cases: int
    results: list[EvalCaseResult]
