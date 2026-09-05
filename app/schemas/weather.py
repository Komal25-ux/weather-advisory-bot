from typing import Optional
from pydantic import BaseModel, Field


class WeatherFacts(BaseModel):
    """
    Normalized, trusted weather facts extracted directly from Open-Meteo.
    LLMs never invent or alter these values.
    """
    temperature_c: Optional[float] = Field(
        default=None,
        description="Air temperature at 2 meters in degrees Celsius"
    )
    relative_humidity_pct: Optional[int] = Field(
        default=None,
        description="Relative humidity percentage (0-100)"
    )
    precipitation_mm: Optional[float] = Field(
        default=None,
        description="Precipitation depth in millimeters"
    )
    precipitation_probability: Optional[int] = Field(
        default=None,
        description="Probability of precipitation percentage (0-100)"
    )
    wind_speed_kmh: Optional[float] = Field(
        default=None,
        description="Wind speed at 10 meters in km/h"
    )
    wind_gusts_kmh: Optional[float] = Field(
        default=None,
        description="Wind gusts at 10 meters in km/h"
    )
    uv_index: Optional[float] = Field(
        default=None,
        description="Ultraviolet radiation index (0.0 to 12.0+)"
    )
    cloud_cover_pct: Optional[int] = Field(
        default=None,
        description="Total cloud cover percentage (0-100)"
    )
    weather_code: Optional[int] = Field(
        default=None,
        description="WMO weather interpretation code"
    )
    visibility_km: Optional[float] = Field(
        default=None,
        description="Horizontal visibility in kilometers"
    )
    target_period: str = Field(
        default="current",
        description="Resolved time period for the weather snapshot, e.g. current, morning, evening"
    )
    is_daytime: Optional[bool] = Field(
        default=True,
        description="Whether the resolved time period is during daylight hours"
    )
    retrieved_at: Optional[str] = Field(
        default=None,
        description="ISO 8601 UTC timestamp of retrieval"
    )
