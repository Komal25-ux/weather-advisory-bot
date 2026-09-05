"""Test suite for Open-Meteo geocoding service with mocked and live integration tests."""
import pytest
import httpx
from unittest.mock import AsyncMock, patch

from app.services.geocoding import (
    resolve_location,
    LocationNotFoundError,
    GeocodingServiceError,
    LocationResolutionError,
    GeocodingResult,
)


@pytest.mark.asyncio
async def test_geocoding_success_mock():
    mock_payload = {
        "results": [
            {
                "name": "London",
                "latitude": 51.50853,
                "longitude": -0.12574,
                "country": "United Kingdom",
                "admin1": "England",
                "timezone": "Europe/London"
            }
        ]
    }
    client = httpx.AsyncClient(transport=httpx.MockTransport(
        lambda req: httpx.Response(200, json=mock_payload)
    ))
    res = await resolve_location("London", client=client)
    assert isinstance(res, GeocodingResult)
    assert res.latitude == 51.50853
    assert res.longitude == -0.12574
    assert res.country == "United Kingdom"
    assert "London" in res.resolved_name
    assert res.timezone == "Europe/London"


@pytest.mark.asyncio
async def test_geocoding_empty_results_raises_not_found():
    mock_payload = {"results": []}
    client = httpx.AsyncClient(transport=httpx.MockTransport(
        lambda req: httpx.Response(200, json=mock_payload)
    ))
    with pytest.raises(LocationNotFoundError) as exc_info:
        await resolve_location("NonExistentCityXYZ999", client=client)
    assert "Could not resolve" in str(exc_info.value)


@pytest.mark.asyncio
async def test_geocoding_http_500_raises_service_error():
    client = httpx.AsyncClient(transport=httpx.MockTransport(
        lambda req: httpx.Response(500, text="Internal Server Error")
    ))
    with pytest.raises(GeocodingServiceError):
        await resolve_location("Berlin", client=client)


@pytest.mark.asyncio
async def test_geocoding_timeout_raises_service_error():
    def raise_timeout(req):
        raise httpx.TimeoutException("Connection timed out")

    client = httpx.AsyncClient(transport=httpx.MockTransport(raise_timeout))
    with pytest.raises(GeocodingServiceError):
        await resolve_location("Madrid", client=client)


@pytest.mark.asyncio
async def test_geocoding_malformed_json_missing_coords():
    mock_payload = {
        "results": [
            {"name": "NoCoordsCity"}  # Missing latitude and longitude
        ]
    }
    client = httpx.AsyncClient(transport=httpx.MockTransport(
        lambda req: httpx.Response(200, json=mock_payload)
    ))
    with pytest.raises(GeocodingServiceError) as exc_info:
        await resolve_location("NoCoordsCity", client=client)
    assert "missing coordinates" in str(exc_info.value)


@pytest.mark.asyncio
async def test_geocoding_empty_query_raises_resolution_error():
    with pytest.raises(LocationResolutionError):
        await resolve_location("   ")


@pytest.mark.asyncio
async def test_geocoding_live_api_integration():
    """Live integration test querying Open-Meteo Geocoding API."""
    try:
        res = await resolve_location("Paris")
        assert res is not None
        assert abs(res.latitude - 48.85) < 0.2
        assert abs(res.longitude - 2.35) < 0.2
        assert res.country is not None
    except GeocodingServiceError as e:
        pytest.skip(f"Live network test skipped due to external network unavailability: {e}")
