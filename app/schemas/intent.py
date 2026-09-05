from typing import Optional, Literal
from pydantic import BaseModel, Field, model_validator


class StructuredIntent(BaseModel):
    """
    Structured extraction of user intent produced by LLM.
    Strictly factual: does NOT contain safety assessments, weather numbers, or recommendations.
    """
    activity: Optional[str] = Field(
        default=None,
        description="Specific outdoor activity, e.g. cycling, running, picnic, park, commute, drone_flying"
    )
    intent_category: Optional[str] = Field(
        default=None,
        description="Broad category: outdoor_exercise, travel, recreation, vulnerable_groups"
    )
    location_name: Optional[str] = Field(
        default=None,
        description="Extracted location or city name if mentioned (e.g. Bhopal, London, Tokyo)"
    )
    time_reference: Optional[str] = Field(
        default="today",
        description="Temporal scope from query, e.g. today, tomorrow, this afternoon, this evening, now"
    )
    target_group: Optional[Literal["general", "child", "elderly", "other"]] = Field(
        default="general",
        description="Target demographic: general, child, elderly, other"
    )
    confidence: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Extraction confidence score"
    )
    is_clarification_needed: bool = Field(
        default=False,
        description="True if query is too ambiguous to identify an outdoor activity or intent"
    )
    ambiguity_reason: Optional[str] = Field(
        default=None,
        description="Explanation if clarification is required"
    )

    @model_validator(mode="before")
    @classmethod
    def handle_location_alias(cls, data: dict):
        if isinstance(data, dict):
            # Support both 'location' and 'location_name' seamlessly
            if "location" in data and "location_name" not in data:
                data["location_name"] = data["location"]
            elif "location_name" in data and "location" not in data:
                data["location"] = data["location_name"]
        return data

    @property
    def location(self) -> Optional[str]:
        """Convenience accessor for location_name."""
        return self.location_name
