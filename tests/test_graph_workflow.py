"""Test suite for Iteration 5: LangGraph StateGraph workflow execution and routing branches."""
import pytest
from unittest.mock import patch, AsyncMock
from langgraph.graph.state import CompiledStateGraph

from app.graph.workflow import build_weather_graph
from app.graph.state import WeatherState
from app.schemas.intent import StructuredIntent
from app.services.geocoding import GeocodingResult, LocationNotFoundError
from app.services.weather import WeatherFetchError
from app.schemas.weather import WeatherFacts


@pytest.fixture
def graph():
    """Provides a compiled LangGraph instance."""
    return build_weather_graph()


def test_graph_compiles_successfully(graph):
    """Test 1: Graph compiles successfully and contains all required nodes."""
    assert isinstance(graph, CompiledStateGraph)
    node_names = set(graph.nodes.keys())
    expected_nodes = {
        "parse_intent",
        "resolve_location",
        "fetch_weather",
        "match_sops",
        "select_decision",
        "generate_response",
        "handle_intent_clarification",
        "handle_failure",
        "handle_no_sop",
    }
    assert expected_nodes.issubset(node_names)


@pytest.mark.asyncio
async def test_clarification_branch_routing(graph):
    """
    Test 2: Ambiguous intent routes to handle_intent_clarification -> END.
    """
    mock_intent = StructuredIntent(
        activity=None,
        location_name=None,
        is_clarification_needed=True,
        ambiguity_reason="Missing activity and location."
    )

    with patch("app.graph.nodes.extract_intent", new_callable=AsyncMock) as mock_extract:
        mock_extract.return_value = mock_intent

        initial_state: WeatherState = {
            "session_id": "test-session-1",
            "user_message": "Should I go outside?",
            "chat_history": []
        }

        final_state = await graph.ainvoke(initial_state)

        assert final_state.get("response_type") == "INTENT_CLARIFICATION"
        assert "specify which outdoor activity" in final_state.get("response", "")
        # Confirm downstream execution stopped (did not call geocoding or weather)
        assert final_state.get("latitude") is None
        assert final_state.get("weather_facts") is None


@pytest.mark.asyncio
async def test_location_failure_branch_routing(graph):
    """
    Test 3: Unresolvable location routes to handle_failure -> END.
    """
    mock_intent = StructuredIntent(
        activity="cycling",
        intent_category="outdoor_exercise",
        location_name="NonExistentCityXYZ",
        time_reference="today",
        target_group="general",
        is_clarification_needed=False
    )

    with patch("app.graph.nodes.extract_intent", new_callable=AsyncMock) as mock_extract, \
         patch("app.graph.nodes.resolve_location", new_callable=AsyncMock) as mock_geo:

        mock_extract.return_value = mock_intent
        mock_geo.side_effect = LocationNotFoundError("Could not resolve location")

        initial_state: WeatherState = {
            "session_id": "test-session-2",
            "user_message": "Can I cycle in NonExistentCityXYZ?",
            "chat_history": []
        }

        final_state = await graph.ainvoke(initial_state)

        assert final_state.get("response_type") == "LOCATION_FAILURE"
        assert "couldn't resolve that location" in final_state.get("response", "")
        assert final_state.get("weather_facts") is None
        assert final_state.get("candidate_sops") is None


@pytest.mark.asyncio
async def test_weather_failure_branch_routing(graph):
    """
    Test 4: Weather API failure routes to handle_failure -> END.
    """
    mock_intent = StructuredIntent(
        activity="cycling",
        intent_category="outdoor_exercise",
        location_name="Berlin",
        time_reference="today",
        target_group="general",
        is_clarification_needed=False
    )
    mock_geo_result = GeocodingResult(
        resolved_name="Berlin, Germany",
        latitude=52.52,
        longitude=13.405,
        timezone="Europe/Berlin"
    )

    with patch("app.graph.nodes.extract_intent", new_callable=AsyncMock) as mock_extract, \
         patch("app.graph.nodes.resolve_location", new_callable=AsyncMock) as mock_geo, \
         patch("app.graph.nodes.fetch_weather_facts", new_callable=AsyncMock) as mock_weather:

        mock_extract.return_value = mock_intent
        mock_geo.return_value = mock_geo_result
        mock_weather.side_effect = WeatherFetchError("Open-Meteo HTTP 500 server error")

        initial_state: WeatherState = {
            "session_id": "test-session-3",
            "user_message": "Is it safe to cycle in Berlin today?",
            "chat_history": []
        }

        final_state = await graph.ainvoke(initial_state)

        assert final_state.get("response_type") == "WEATHER_FAILURE"
        assert "couldn't retrieve live weather data" in final_state.get("response", "")
        assert final_state.get("weather_facts") is None
        assert final_state.get("candidate_sops") is None


@pytest.mark.asyncio
async def test_no_sop_branch_routing(graph):
    """
    Test 5: Valid intent and weather, but zero matching policies routes to handle_no_sop -> END.
    """
    mock_intent = StructuredIntent(
        activity="drone_flying",
        intent_category="recreation",
        location_name="Berlin",
        time_reference="today",
        target_group="general",
        is_clarification_needed=False
    )
    mock_geo_result = GeocodingResult(
        resolved_name="Berlin, Germany",
        latitude=52.52,
        longitude=13.405,
        timezone="Europe/Berlin"
    )
    mock_facts = WeatherFacts(
        temperature_c=22.0,
        wind_speed_kmh=12.0,
        precipitation_mm=0.0,
        precipitation_probability=10,
        uv_index=4.0
    )

    with patch("app.graph.nodes.extract_intent", new_callable=AsyncMock) as mock_extract, \
         patch("app.graph.nodes.resolve_location", new_callable=AsyncMock) as mock_geo, \
         patch("app.graph.nodes.fetch_weather_facts", new_callable=AsyncMock) as mock_weather:

        mock_extract.return_value = mock_intent
        mock_geo.return_value = mock_geo_result
        mock_weather.return_value = mock_facts

        initial_state: WeatherState = {
            "session_id": "test-session-4",
            "user_message": "Can I fly my drone in Berlin today?",
            "chat_history": []
        }

        final_state = await graph.ainvoke(initial_state)

        assert final_state.get("response_type") == "NO_SOP"
        assert "don't have an applicable safety policy for drone_flying" in final_state.get("response", "")
        assert final_state.get("selected_sop") is None


@pytest.mark.asyncio
async def test_normal_successful_path_reaches_response_generation(graph):
    """
    Test 6: Full successful path traverses all nodes to generate_response.
    """
    mock_intent = StructuredIntent(
        activity="cycling",
        intent_category="outdoor_exercise",
        location_name="Berlin",
        time_reference="today",
        target_group="general",
        is_clarification_needed=False
    )
    mock_geo_result = GeocodingResult(
        resolved_name="Berlin, Germany",
        latitude=52.52,
        longitude=13.405,
        timezone="Europe/Berlin"
    )
    # Wind 44.0 km/h triggers SOP-CYCLING-WIND-001
    mock_facts = WeatherFacts(
        temperature_c=24.0,
        wind_speed_kmh=44.0,
        wind_gusts_kmh=52.0,
        precipitation_mm=0.0,
        precipitation_probability=10,
        uv_index=5.0
    )

    with patch("app.graph.nodes.extract_intent", new_callable=AsyncMock) as mock_extract, \
         patch("app.graph.nodes.resolve_location", new_callable=AsyncMock) as mock_geo, \
         patch("app.graph.nodes.fetch_weather_facts", new_callable=AsyncMock) as mock_weather:

        mock_extract.return_value = mock_intent
        mock_geo.return_value = mock_geo_result
        mock_weather.return_value = mock_facts

        initial_state: WeatherState = {
            "session_id": "test-session-5",
            "user_message": "Is it safe to cycle in Berlin today?",
            "chat_history": []
        }

        final_state = await graph.ainvoke(initial_state)

        # Confirm all state artifacts are populated
        assert final_state.get("response_type") == "SUCCESS"
        assert final_state.get("selected_sop") is not None
        assert final_state.get("selected_sop")["sop_id"] == "SOP-CYCLING-WIND-001"
        assert "Policy evaluated: SOP-CYCLING-WIND-001" in final_state.get("response", "")
        assert final_state.get("trace")["matched_sop_count"] >= 1
