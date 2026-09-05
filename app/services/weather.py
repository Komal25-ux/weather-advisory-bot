"""Weather service skeleton for Iteration 1."""
from typing import Optional
from app.schemas.weather import WeatherFacts


async def fetch_weather_facts(
    latitude: float,
    longitude: float,
    time_reference: str = "today",
    timezone: str = "auto"
) -> Optional[WeatherFacts]:
    """
    Placeholder: calls Open-Meteo Forecast API and normalizes weather facts.
    Full implementation scheduled for Iteration 3.
    """
    raise NotImplementedError("Weather service will be implemented in Iteration 3.")
