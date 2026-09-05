from typing import Optional, Literal, Dict, Any, List
from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """Incoming user chat message."""
    session_id: str = Field(
        description="Unique session identifier for chat-scoped context"
    )
    message: str = Field(
        min_length=1,
        max_length=2000,
        description="User natural-language query"
    )


class TraceResponse(BaseModel):
    """Detailed observability and audit trace for explainability."""
    activity: Optional[str] = None
    intent_category: Optional[str] = None
    location_query: Optional[str] = None
    resolved_location: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    time_reference: Optional[str] = None
    target_group: Optional[str] = None
    matched_sop_count: int = 0
    candidate_sop_ids: List[str] = Field(default_factory=list)
    selected_sop_id: Optional[str] = None
    decision_severity: Optional[str] = None
    decision_trace: Optional[str] = None


class ChatResponse(BaseModel):
    """User-facing chat response returned by FastAPI."""
    session_id: str
    response_type: Literal[
        "SUCCESS",
        "NO_SOP",
        "LOCATION_FAILURE",
        "WEATHER_FAILURE",
        "INTENT_CLARIFICATION"
    ]
    response: str
    sop_id: Optional[str] = None
    sop_name: Optional[str] = None
    severity: Optional[str] = None
    recommendation: Optional[str] = None
    weather_facts: Optional[Dict[str, Any]] = None
    trace: Optional[TraceResponse] = None


class HealthResponse(BaseModel):
    """System health status response."""
    status: str = "ok"
    loaded_sops_count: int = 0
    version: str = "1.0.0"
