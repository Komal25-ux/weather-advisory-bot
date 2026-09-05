import logging
from typing import Optional
import httpx
from pydantic import BaseModel, Field

from app.config import settings

logger = logging.getLogger("weather-advisory-bot.services.geocoding")


class LocationResolutionError(Exception):
    """Base exception for location resolution errors."""
    pass


class LocationNotFoundError(LocationResolutionError):
    """Raised when geocoding returns no matching location."""
    pass


class GeocodingServiceError(LocationResolutionError):
    """Raised on API errors, timeouts, or network failures."""
    pass


class GeocodingResult(BaseModel):
    """Normalized geocoding outcome from Open-Meteo."""
    resolved_name: str = Field(description="Formatted location name, e.g. Bhopal, Madhya Pradesh, India")
    latitude: float = Field(description="Geographic latitude coordinate")
    longitude: float = Field(description="Geographic longitude coordinate")
    country: Optional[str] = Field(default=None, description="Country name")
    admin1: Optional[str] = Field(default=None, description="State / Province / Region name")
    timezone: str = Field(default="UTC", description="IANA timezone, e.g. Asia/Kolkata")


async def resolve_location(
    location_name: str,
    client: Optional[httpx.AsyncClient] = None
) -> GeocodingResult:
    """
    Resolves a location query to coordinates and metadata using Open-Meteo Geocoding API.
    Enforces a bounded retry (max 1 retry), explicit timeout, and strict error handling.
    Does NOT guess or fall back to hardcoded coordinates.
    """
    cleaned_query = location_name.strip()
    if not cleaned_query:
        raise LocationResolutionError("Location query cannot be empty.")

    params = {
        "name": cleaned_query,
        "count": 1,
        "language": "en",
        "format": "json"
    }

    url = settings.GEOCODING_BASE_URL
    timeout = settings.OPEN_METEO_TIMEOUT_SECONDS
    max_retries = 1

    close_client_when_done = False
    if client is None:
        client = httpx.AsyncClient(timeout=timeout)
        close_client_when_done = True

    try:
        last_error = None
        for attempt in range(max_retries + 1):
            try:
                response = await client.get(url, params=params)
                if response.status_code >= 500:
                    response.raise_for_status()

                if response.status_code != 200:
                    raise GeocodingServiceError(
                        f"Geocoding API returned status {response.status_code}: {response.text}"
                    )

                data = response.json()
                results = data.get("results")
                if not results or len(results) == 0:
                    raise LocationNotFoundError(
                        f"Could not resolve any location matching '{cleaned_query}'."
                    )

                top_result = results[0]
                lat = top_result.get("latitude")
                lon = top_result.get("longitude")
                name = top_result.get("name")

                if lat is None or lon is None or not name:
                    raise GeocodingServiceError(
                        f"Malformed geocoding payload received: missing coordinates or name."
                    )

                country = top_result.get("country")
                admin1 = top_result.get("admin1")
                tz = top_result.get("timezone", "UTC")

                # Format descriptive resolved name
                parts = [p for p in [name, admin1, country] if p]
                full_name = ", ".join(parts)

                logger.info(
                    f"Resolved '{cleaned_query}' to '{full_name}' (lat: {lat}, lon: {lon}, tz: {tz})"
                )

                return GeocodingResult(
                    resolved_name=full_name,
                    latitude=float(lat),
                    longitude=float(lon),
                    country=country,
                    admin1=admin1,
                    timezone=tz
                )

            except (httpx.TimeoutException, httpx.NetworkError, httpx.HTTPStatusError) as e:
                last_error = e
                if attempt < max_retries:
                    logger.warning(
                        f"Geocoding call for '{cleaned_query}' failed (attempt {attempt + 1}/{max_retries + 1}): {e}. Retrying..."
                    )
                    continue
                else:
                    raise GeocodingServiceError(
                        f"Geocoding service unavailable after {max_retries + 1} attempts: {e}"
                    ) from e

        raise GeocodingServiceError(f"Geocoding failed: {last_error}")

    finally:
        if close_client_when_done:
            await client.aclose()
