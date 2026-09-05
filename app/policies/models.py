from typing import Literal, Optional, List, Any, Dict
from pydantic import BaseModel, Field

SeverityLevel = Literal["CRITICAL", "HIGH", "MEDIUM", "LOW"]
RecommendationType = Literal["recommended", "caution", "not_recommended", "unsupported"]
ConditionOperator = Literal[
    "equals",
    "not_equals",
    "greater_than",
    "greater_than_or_equal",
    "less_than",
    "less_than_or_equal",
    "in",
    "not_in",
    "between"
]


class ConditionRule(BaseModel):
    """Atomic rule condition comparing a fact against a threshold."""
    field: str = Field(description="Target fact key, e.g. wind_speed_kmh, activity")
    operator: ConditionOperator = Field(description="Comparison operator")
    value: Any = Field(description="Scalar or list comparison threshold")


class ConditionGroup(BaseModel):
    """Composite rule conditions supporting logical ALL (AND) and ANY (OR)."""
    all: Optional[List[ConditionRule]] = Field(
        default=None,
        description="Every condition in this list must evaluate to True"
    )
    any: Optional[List[ConditionRule]] = Field(
        default=None,
        description="At least one condition in this list must evaluate to True"
    )


class SOPAdvice(BaseModel):
    """Structured advisory output associated with an SOP."""
    recommendation: RecommendationType = Field(
        default="not_recommended",
        description="Primary safety decision"
    )
    title: str = Field(description="Headline advisory summary")
    guidance: List[str] = Field(description="Actionable policy instructions")
    rationale: str = Field(description="Scientific or safety justification")


class SOPRule(BaseModel):
    """Complete externalized Standard Operating Procedure specification."""
    id: str = Field(description="Unique policy identifier, e.g. SOP-CYCLING-WIND-001")
    name: str = Field(description="Human-readable policy title")
    version: str = Field(default="1.0", description="Policy version")
    category: str = Field(description="Domain category, e.g. outdoor_exercise, travel")
    severity: SeverityLevel = Field(description="Safety severity level")
    priority: int = Field(
        default=50,
        ge=0,
        le=100,
        description="Tie-breaking priority within the same severity level (higher wins)"
    )
    description: str = Field(description="Summary explanation for non-technical users")
    conditions: ConditionGroup = Field(description="Evaluated rule conditions")
    required_weather_fields: List[str] = Field(
        default_factory=list,
        description="Fields that must exist in weather response to evaluate"
    )
    advice: SOPAdvice = Field(description="Actionable guidance if policy matches")


class MatchedCondition(BaseModel):
    """Audit record of a single evaluated condition."""
    field: str
    operator: str
    threshold: Any
    actual: Any
    result: bool
    status: Literal["PASSED", "FAILED", "UNAVAILABLE"] = "PASSED"


class CandidateSOP(BaseModel):
    """An SOP that matched all condition requirements."""
    sop_id: str
    name: str
    category: str
    severity: SeverityLevel
    priority: int
    matched_conditions: List[MatchedCondition] = Field(default_factory=list)


class DeterministicDecision(BaseModel):
    """
    Final deterministic safety decision selected by the rule engine.
    Chosen solely via Severity > Priority > SOP ID.
    """
    sop_id: str
    sop_name: str
    severity: SeverityLevel
    recommendation: RecommendationType
    priority: int
    matched_conditions: List[MatchedCondition]
    guidance: List[str]
    rationale: str
    decision_trace: str
