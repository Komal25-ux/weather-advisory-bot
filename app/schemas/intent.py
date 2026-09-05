from typing import Optional, Literal
from pydantic import BaseModel, Field


class StructuredIntent(BaseModel):
    """
    Structured extraction of user intent produced by LLM.
    Strictly factual: does NOT contain safety assessments or recommendations.
    """
    activity: Optional[str] = Field(
        default=None,
        description="Granular outdoor action, e.g. cycling, running, picnic, park, commute"
    )
    intent_category: Optional[str] = Field(
        default=None,
        description="Broad category, e.g. outdoor_exercise, travel, recreation, vulnerable_groups"
    )
    location: Optional[str] = Field(
        default=None,
        description="Named geographic location, e.g. Bhopal, London, Paris"
    )
    time_reference: Optional[str] = Field(
        default="today",
        description="Temporal scope, e.g. today, tomorrow, this afternoon, this evening"
    )
    target_group: Optional[Literal["general", "child", "elderly"]] = Field(
        default="general",
        description="Target demographic if mentioned, e.g. child, elderly, general"
    )
    confidence: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Confidence score for intent extraction"
    )
    is_clarification_needed: bool = Field(
        default=False,
        description="True if query is completely ambiguous (e.g. 'Should I go?')"
    )
