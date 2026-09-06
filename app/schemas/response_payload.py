from typing import List, Any, Optional
from pydantic import BaseModel, Field


class FactToReport(BaseModel):
    """A specific factual weather observation passed to the LLM response composer."""
    name: str = Field(description="Name of the weather metric, e.g. Wind Speed, Temperature, Precipitation")
    value: Any = Field(description="Exact value from API or 'UNAVAILABLE'")
    unit: str = Field(default="", description="Unit of measurement, e.g. km/h, °C, mm, %")


class ResponseGenerationPayload(BaseModel):
    """
    Bounded, trusted structured input supplied to the LLM response generator.
    Contains ONLY what the LLM is authorized to verbalize.
    """
    activity: str = Field(description="Target activity, e.g. cycling")
    location: str = Field(description="Resolved location name, e.g. Bhopal, Madhya Pradesh, India")
    time_period: str = Field(default="today", description="Temporal scope, e.g. today, this evening")
    recommendation: str = Field(description="Deterministic recommendation: recommended, caution, or not_recommended")
    severity: str = Field(description="Policy severity: CRITICAL, HIGH, MEDIUM, LOW")
    selected_sop_id: str = Field(description="Winning policy ID, e.g. SOP-CYCLING-WIND-001")
    selected_sop_name: str = Field(description="Policy title, e.g. Strong Wind and Cycling")
    applicable_sop_ids: List[str] = Field(default_factory=list, description="All matching SOP candidate IDs")
    guidance: List[str] = Field(default_factory=list, description="SOP action items")
    rationale: str = Field(default="", description="Safety/scientific reason from SOP")
    facts_used: List[FactToReport] = Field(default_factory=list, description="Exact numbers extracted from weather API")
    decision_trace: str = Field(default="", description="Auditable logic trigger string")
