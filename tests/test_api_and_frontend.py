"""
Integration tests for FastAPI Backend and Frontend integration (Iteration 11).

Verifies:
1. successful advisory response renders (SUCCESS)
2. clarification response renders (INTENT_CLARIFICATION)
3. NO_SOP response renders (NO_SOP)
4. WEATHER_FAILURE response renders (WEATHER_FAILURE)
5. session_id is preserved across follow-ups
6. new conversation creates a new session
7. empty submission is rejected (422)
8. static index.html and assets are properly served
"""
import pytest
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient

from app.main import app
from app.schemas.intent import StructuredIntent
from app.services.geocoding import GeocodingResult
from app.services.weather import WeatherFacts, WeatherFetchError


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


def test_health_check_endpoint(client):
    """Verify /health endpoint returns 200 and reports loaded SOP count."""
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["loaded_sops_count"] >= 12


def test_serve_frontend_index(client):
    """Verify root / serves the frontend HTML interface."""
    resp = client.get("/")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "Weather Advisory Support Bot" in resp.text
    assert "Live weather + policy-grounded outdoor safety advice" in resp.text
    assert "chat-messages" in resp.text


def test_serve_frontend_static_assets(client):
    """Verify /static/style.css and /static/app.js are served."""
    css_resp = client.get("/static/style.css")
    assert css_resp.status_code == 200
    assert "text/css" in css_resp.headers["content-type"]

    js_resp = client.get("/static/app.js")
    assert js_resp.status_code == 200
    assert "javascript" in js_resp.headers["content-type"]


def test_empty_submission_rejected(client):
    """Verify empty message submission is rejected with 422 Unprocessable Entity."""
    resp = client.post("/chat", json={"session_id": "test-sess", "message": ""})
    assert resp.status_code == 422


def test_successful_advisory_response_renders(client):
    """Test 1: Successful grounded advisory response returns all decision details."""
    intent_mock = StructuredIntent(
        activity="cycling",
        intent_category="outdoor_exercise",
        location_name="Berlin",
        time_reference="today",
        target_group="general",
        is_clarification_needed=False
    )
    geo_mock = GeocodingResult(
        resolved_name="Berlin, Germany",
        latitude=52.52,
        longitude=13.405,
        timezone="Europe/Berlin"
    )
    facts_mock = WeatherFacts(
        temperature_c=22.0,
        wind_speed_kmh=44.0,  # Matches SOP-CYCLING-WIND-001
        wind_gusts_kmh=52.0,
        precipitation_mm=0.0
    )

    with patch("app.graph.nodes.extract_intent", new_callable=AsyncMock) as m_intent, \
         patch("app.graph.nodes.resolve_location", new_callable=AsyncMock) as m_geo, \
         patch("app.graph.nodes.fetch_weather_facts", new_callable=AsyncMock) as m_weather:

        m_intent.return_value = intent_mock
        m_geo.return_value = geo_mock
        m_weather.return_value = facts_mock

        resp = client.post("/chat", json={
            "session_id": "sess-success-1",
            "message": "Can I cycle in Berlin today?"
        })

    assert resp.status_code == 200
    data = resp.json()
    assert data["session_id"] == "sess-success-1"
    assert data["response_type"] == "SUCCESS"
    assert data["sop_id"] == "SOP-CYCLING-WIND-001"
    assert data["recommendation"] == "not_recommended"
    assert data["severity"] == "HIGH"
    assert data["location"] == "Berlin, Germany"
    assert data["weather_facts"]["wind_speed_kmh"] == 44.0
    assert "Cycling is not recommended" in data["response"]


def test_clarification_response_renders(client):
    """Test 2: Query missing location triggers INTENT_CLARIFICATION response."""
    intent_mock = StructuredIntent(
        activity="cycling",
        location_name=None,
        is_clarification_needed=True,
        ambiguity_reason="Missing location"
    )

    with patch("app.graph.nodes.extract_intent", new_callable=AsyncMock) as m_intent:
        m_intent.return_value = intent_mock

        resp = client.post("/chat", json={
            "session_id": "sess-clar-1",
            "message": "Can I cycle today?"
        })

    assert resp.status_code == 200
    data = resp.json()
    assert data["response_type"] == "INTENT_CLARIFICATION"
    assert "Which city or location" in data["response"]
    assert data["sop_id"] is None
    assert data["recommendation"] is None


def test_no_sop_response_renders(client):
    """Test 3: Unsupported activity triggers NO_SOP response."""
    intent_mock = StructuredIntent(
        activity="scuba_diving",
        intent_category="recreation",
        location_name="Mumbai",
        time_reference="today",
        is_clarification_needed=False
    )
    geo_mock = GeocodingResult(
        resolved_name="Mumbai, India",
        latitude=19.07,
        longitude=72.87,
        timezone="Asia/Kolkata"
    )
    facts_mock = WeatherFacts(
        temperature_c=29.0,
        wind_speed_kmh=10.0,
        precipitation_mm=0.0
    )

    with patch("app.graph.nodes.extract_intent", new_callable=AsyncMock) as m_intent, \
         patch("app.graph.nodes.resolve_location", new_callable=AsyncMock) as m_geo, \
         patch("app.graph.nodes.fetch_weather_facts", new_callable=AsyncMock) as m_weather:

        m_intent.return_value = intent_mock
        m_geo.return_value = geo_mock
        m_weather.return_value = facts_mock

        resp = client.post("/chat", json={
            "session_id": "sess-nosop-1",
            "message": "Can I scuba dive in Mumbai today?"
        })

    assert resp.status_code == 200
    data = resp.json()
    assert data["response_type"] == "NO_SOP"
    assert data["sop_id"] is None
    assert "don't have an applicable safety policy" in data["response"]


def test_weather_failure_response_renders(client):
    """Test 4: Weather API failure triggers WEATHER_FAILURE response."""
    intent_mock = StructuredIntent(
        activity="cycling",
        location_name="Berlin",
        time_reference="today",
        is_clarification_needed=False
    )
    geo_mock = GeocodingResult(
        resolved_name="Berlin, Germany",
        latitude=52.52,
        longitude=13.405,
        timezone="Europe/Berlin"
    )

    with patch("app.graph.nodes.extract_intent", new_callable=AsyncMock) as m_intent, \
         patch("app.graph.nodes.resolve_location", new_callable=AsyncMock) as m_geo, \
         patch("app.graph.nodes.fetch_weather_facts", new_callable=AsyncMock) as m_weather:

        m_intent.return_value = intent_mock
        m_geo.return_value = geo_mock
        m_weather.side_effect = WeatherFetchError("Open-Meteo HTTP 500 error")

        resp = client.post("/chat", json={
            "session_id": "sess-fail-1",
            "message": "Can I cycle in Berlin today?"
        })

    assert resp.status_code == 200
    data = resp.json()
    assert data["response_type"] == "WEATHER_FAILURE"
    assert data["weather_facts"] is None
    assert "couldn't retrieve live weather data" in data["response"]


def test_session_id_preserved_across_follow_ups(client):
    """Test 5: Follow-up questions in same session preserve activity and location context."""
    turn1_intent = StructuredIntent(
        activity="cycling",
        location_name="Berlin",
        time_reference="today",
        is_clarification_needed=False
    )
    turn2_intent = StructuredIntent(
        activity=None,
        location_name=None,
        time_reference="this evening",
        is_clarification_needed=False
    )

    geo_mock = GeocodingResult(resolved_name="Berlin, Germany", latitude=52.52, longitude=13.405, timezone="Europe/Berlin")
    facts_turn1 = WeatherFacts(temperature_c=22.0, wind_speed_kmh=44.0, precipitation_mm=0.0)
    facts_turn2 = WeatherFacts(temperature_c=18.0, wind_speed_kmh=45.0, precipitation_mm=0.0, target_period="evening")

    with patch("app.graph.nodes.extract_intent", new_callable=AsyncMock) as m_intent, \
         patch("app.graph.nodes.resolve_location", new_callable=AsyncMock) as m_geo, \
         patch("app.graph.nodes.fetch_weather_facts", new_callable=AsyncMock) as m_weather:

        m_geo.return_value = geo_mock

        # Turn 1
        m_intent.return_value = turn1_intent
        m_weather.return_value = facts_turn1
        r1 = client.post("/chat", json={"session_id": "multi-turn-sess", "message": "Can I cycle in Berlin today?"})
        assert r1.status_code == 200
        d1 = r1.json()
        assert d1["response_type"] == "SUCCESS"
        assert d1["location"] == "Berlin, Germany"

        # Turn 2 (Follow-up)
        m_intent.return_value = turn2_intent
        m_weather.return_value = facts_turn2
        r2 = client.post("/chat", json={"session_id": "multi-turn-sess", "message": "What about this evening?"})
        assert r2.status_code == 200
        d2 = r2.json()
        assert d2["response_type"] == "SUCCESS"
        assert d2["location"] == "Berlin, Germany"  # Retained Berlin
        assert "evening" in d2["time_period"].lower()  # Updated time
        assert d2["sop_id"] == "SOP-CYCLING-WIND-001"


def test_new_conversation_creates_new_session_isolation(client):
    """Test 6: A new session starts without prior context and asks for clarification."""
    turn_new_intent = StructuredIntent(
        activity=None,
        location_name=None,
        time_reference="this evening",
        is_clarification_needed=True
    )

    with patch("app.graph.nodes.extract_intent", new_callable=AsyncMock) as m_intent:
        m_intent.return_value = turn_new_intent
        resp = client.post("/chat", json={
            "session_id": "brand-new-isolated-session-id",
            "message": "What about this evening?"
        })

    assert resp.status_code == 200
    data = resp.json()
    assert data["response_type"] == "INTENT_CLARIFICATION"
    assert "specify which outdoor activity" in data["response"]
