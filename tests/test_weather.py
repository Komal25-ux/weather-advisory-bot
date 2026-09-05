"""Test suite for Open-Meteo forecast service with mocked and live integration tests."""
import pytest
import httpx

from app.services.weather import (
    fetch_weather_facts,
    WeatherFetchError,
    WeatherDataValidationError,
)
from app.schemas.weather import WeatherFacts


@pytest.mark.asyncio
async def test_weather_fetch_success_mock():
    mock_payload = {
        "current": {
            "temperature_2m": 24.5,
            "relative_humidity_2m": 58,
            "precipitation": 0.0,
            "weather_code": 1,
            "cloud_cover": 20,
            "wind_speed_10m": 18.2,
            "wind_gusts_10m": 26.5,
            "uv_index": 5.4,
            "is_day": 1
        },
        "hourly": {
            "precipitation_probability": [15, 20, 25],
            "visibility": [10000, 10000, 9500]
        }
    }
    client = httpx.AsyncClient(transport=httpx.MockTransport(
        lambda req: httpx.Response(200, json=mock_payload)
    ))

    facts = await fetch_weather_facts(latitude=51.5, longitude=-0.12, client=client)
    assert isinstance(facts, WeatherFacts)
    assert facts.temperature_c == 24.5
    assert facts.wind_speed_kmh == 18.2
    assert facts.wind_gusts_kmh == 26.5
    assert facts.uv_index == 5.4
    assert facts.precipitation_probability == 15
    assert facts.visibility_km == 10.0
    assert facts.is_daytime is True


@pytest.mark.asyncio
async def test_weather_hourly_window_aggregation_evening():
    mock_payload = {
        "current": {"temperature_2m": 28.0},
        "hourly": {
            "time": [
                "2026-09-06T17:00",
                "2026-09-06T18:00",
                "2026-09-06T19:00",
                "2026-09-06T20:00",
                "2026-09-06T21:00",
                "2026-09-06T22:00"
            ],
            "temperature_2m": [27.0, 25.0, 24.0, 23.0, 22.0, 21.0],
            "relative_humidity_2m": [60, 65, 70, 75, 80, 85],
            "precipitation": [0.0, 0.5, 1.2, 0.0, 0.0, 0.0],
            "precipitation_probability": [20, 40, 75, 50, 30, 10],
            "wind_speed_10m": [15.0, 32.0, 42.5, 30.0, 20.0, 15.0],
            "wind_gusts_10m": [25.0, 45.0, 58.0, 40.0, 30.0, 20.0],
            "uv_index": [3.0, 1.0, 0.0, 0.0, 0.0, 0.0],
            "cloud_cover": [40, 70, 90, 80, 50, 30],
            "visibility": [10000, 8000, 5000, 6000, 8000, 10000],
            "is_day": [1, 1, 0, 0, 0, 0]
        }
    }
    client = httpx.AsyncClient(transport=httpx.MockTransport(
        lambda req: httpx.Response(200, json=mock_payload)
    ))

    facts = await fetch_weather_facts(
        latitude=51.5,
        longitude=-0.12,
        time_reference="this evening",
        client=client
    )
    # Peak risk wind in 18:00 - 22:00 is 42.5 km/h
    assert facts.wind_speed_kmh == 42.5
    assert facts.wind_gusts_kmh == 58.0
    # Peak precipitation probability is 75%
    assert facts.precipitation_probability == 75
    # Total precipitation sum is 0.5 + 1.2 = 1.7 mm
    assert facts.precipitation_mm == 1.7
    # Minimum visibility is 5.0 km
    assert facts.visibility_km == 5.0
    assert facts.target_period == "this evening"


@pytest.mark.asyncio
async def test_weather_http_500_raises_fetch_error():
    client = httpx.AsyncClient(transport=httpx.MockTransport(
        lambda req: httpx.Response(500, text="Open-Meteo Server Down")
    ))
    with pytest.raises(WeatherFetchError):
        await fetch_weather_facts(latitude=51.5, longitude=-0.12, client=client)


@pytest.mark.asyncio
async def test_weather_timeout_raises_fetch_error():
    def raise_timeout(req):
        raise httpx.TimeoutException("Read timed out")

    client = httpx.AsyncClient(transport=httpx.MockTransport(raise_timeout))
    with pytest.raises(WeatherFetchError):
        await fetch_weather_facts(latitude=51.5, longitude=-0.12, client=client)


@pytest.mark.asyncio
async def test_weather_malformed_json_raises_validation_error():
    client = httpx.AsyncClient(transport=httpx.MockTransport(
        lambda req: httpx.Response(200, json=["invalid", "array", "not", "object"])
    ))
    with pytest.raises(WeatherDataValidationError):
        await fetch_weather_facts(latitude=51.5, longitude=-0.12, client=client)


@pytest.mark.asyncio
async def test_weather_missing_fields_preserved_as_none():
    mock_payload = {
        "current": {
            "temperature_2m": 22.0
            # wind_speed_10m, uv_index, etc. omitted
        },
        "hourly": {}
    }
    client = httpx.AsyncClient(transport=httpx.MockTransport(
        lambda req: httpx.Response(200, json=mock_payload)
    ))
    facts = await fetch_weather_facts(latitude=51.5, longitude=-0.12, client=client)
    assert facts.temperature_c == 22.0
    assert facts.wind_speed_kmh is None  # MUST NOT be fabricated as 0.0
    assert facts.uv_index is None        # MUST NOT be fabricated as 0.0


@pytest.mark.asyncio
async def test_weather_live_api_integration():
    """Live integration test against Open-Meteo forecast API."""
    try:
        facts = await fetch_weather_facts(latitude=35.6762, longitude=139.6503, time_reference="today")
        assert facts is not None
        assert facts.temperature_c is not None
        assert facts.wind_speed_kmh is not None
        assert facts.retrieved_at is not None
    except WeatherFetchError as e:
        pytest.skip(f"Live network test skipped due to external network unavailability: {e}")
