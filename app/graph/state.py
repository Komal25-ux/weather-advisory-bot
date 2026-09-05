from typing import TypedDict, Literal, Optional, List, Dict, Any


class MatchedConditionDict(TypedDict):
    """Dictionary representation of an evaluated condition for State audit."""
    field: str
    operator: str
    threshold: Any
    actual: Any
    result: bool
    status: Literal["PASSED", "FAILED", "UNAVAILABLE"]


class CandidateSOPDict(TypedDict):
    """Dictionary representation of a matching candidate SOP."""
    sop_id: str
    name: str
    category: str
    severity: Literal["CRITICAL", "HIGH", "MEDIUM", "LOW"]
    priority: int
    matched_conditions: List[MatchedConditionDict]


class WeatherState(TypedDict, total=False):
    """
    Central state object for the LangGraph Weather Advisory State Machine.
    Maintains typed conversation state, extracted intent, resolved location,
    normalized weather facts, candidate SOPs, deterministic decision, and trace.
    """
    # Session & Chat Tracking
    session_id: str
    user_message: str
    chat_history: List[Dict[str, str]]

    # Extracted Intent (LLM structured extraction)
    activity: Optional[str]
    intent_category: Optional[str]
    location_name: Optional[str]
    time_reference: Optional[str]
    target_group: Optional[str]
    intent_confidence: Optional[float]
    is_clarification_needed: bool

    # Geocoding Result (Deterministic)
    resolved_location_name: Optional[str]
    latitude: Optional[float]
    longitude: Optional[float]
    country: Optional[str]
    admin1: Optional[str]
    timezone: Optional[str]

    # Weather Facts (Normalized Deterministic Data from Open-Meteo)
    weather_facts: Optional[Dict[str, Any]]

    # Deterministic SOP Decision Engine
    candidate_sops: List[CandidateSOPDict]
    selected_sop: Optional[Dict[str, Any]]
    decision_severity: Optional[Literal["CRITICAL", "HIGH", "MEDIUM", "LOW"]]
    decision_recommendation: Optional[Literal["recommended", "caution", "not_recommended", "unsupported"]]
    matched_reasons: List[MatchedConditionDict]
    decision_trace: Optional[str]

    # Output & Flow Status
    response_type: Literal[
        "SUCCESS",
        "NO_SOP",
        "LOCATION_FAILURE",
        "WEATHER_FAILURE",
        "INTENT_CLARIFICATION"
    ]
    response: Optional[str]
    error_type: Optional[str]
    error_message: Optional[str]

    # Audit & Observability Trace
    trace: Dict[str, Any]
