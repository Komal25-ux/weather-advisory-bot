"""
Comprehensive test suite for Iteration 9: Session-Scoped Conversation Memory.

Validates:
1. follow-up retaining location
2. follow-up retaining activity
3. follow-up changing time
4. follow-up changing location
5. follow-up changing activity
6. two sessions remain isolated
7. no cross-session leakage
8. same session_id preserves context across separate graph invocations
9. new session_id starts without prior context
10. updated location/time causes fresh weather retrieval
11. newly fetched weather remains authoritative
"""
import pytest
from unittest.mock import AsyncMock, patch

from app.graph.workflow import build_weather_graph
from app.graph.state import WeatherState
from app.services.session import session_manager
from app.schemas.intent import StructuredIntent
from app.services.geocoding import GeocodingResult
from app.services.weather import WeatherFacts


@pytest.fixture(autouse=True)
def reset_sessions():
    """Ensure in-memory checkpointer is clean before each test."""
    session_manager.reset_all_sessions()
    yield
    session_manager.reset_all_sessions()


@pytest.fixture
def graph():
    return build_weather_graph(checkpointer=session_manager.checkpointer)


@pytest.mark.asyncio
async def test_follow_up_retaining_location(graph):
    """
    Test 1: User asks about cycling in Bhopal, then asks about running.
    Follow-up must retain location 'Bhopal' while updating activity to 'running'.
    """
    turn1_intent = StructuredIntent(
        activity="cycling",
        intent_category="outdoor_exercise",
        location_name="Bhopal",
        time_reference="today",
        target_group="general",
        is_clarification_needed=False
    )
    turn2_intent = StructuredIntent(
        activity="running",
        intent_category="outdoor_exercise",
        location_name=None,  # No location mentioned in follow-up
        time_reference="today",
        target_group="general",
        is_clarification_needed=False
    )

    geo_bhopal = GeocodingResult(
        resolved_name="Bhopal, India",
        latitude=23.25,
        longitude=77.41,
        timezone="Asia/Kolkata"
    )
    facts_bhopal = WeatherFacts(
        temperature_c=28.0,
        wind_speed_kmh=12.0,
        wind_gusts_kmh=18.0,
        precipitation_mm=0.0,
        precipitation_probability=5,
        uv_index=4.0
    )

    with patch("app.graph.nodes.extract_intent", new_callable=AsyncMock) as mock_extract, \
         patch("app.graph.nodes.resolve_location", new_callable=AsyncMock) as mock_geo, \
         patch("app.graph.nodes.fetch_weather_facts", new_callable=AsyncMock) as mock_weather:

        mock_geo.return_value = geo_bhopal
        mock_weather.return_value = facts_bhopal

        # Turn 1: "Can I cycle in Bhopal today?"
        mock_extract.return_value = turn1_intent
        state1: WeatherState = {
            "session_id": "session-retain-loc",
            "user_message": "Can I cycle in Bhopal today?",
            "chat_history": []
        }
        res1 = await graph.ainvoke(state1)
        assert res1["activity"] == "cycling"
        assert res1["location_name"] == "Bhopal"
        assert res1["response_type"] == "SUCCESS"

        # Turn 2: "What about running?" (location omitted)
        mock_extract.return_value = turn2_intent
        state2: WeatherState = {
            "session_id": "session-retain-loc",
            "user_message": "What about running?"
        }
        res2 = await graph.ainvoke(state2)
        assert res2["activity"] == "running"  # Activity replaced
        assert res2["location_name"] == "Bhopal"  # Location retained!
        assert res2["response_type"] == "SUCCESS"


@pytest.mark.asyncio
async def test_follow_up_retaining_activity(graph):
    """
    Test 2: User asks "Can I cycle in Bhopal today?", then "What about this evening?".
    Follow-up must retain Bhopal + cycling and update time to 'this evening'.
    """
    turn1_intent = StructuredIntent(
        activity="cycling",
        intent_category="outdoor_exercise",
        location_name="Bhopal",
        time_reference="today",
        target_group="general",
        is_clarification_needed=False
    )
    turn2_intent = StructuredIntent(
        activity=None,
        intent_category=None,
        location_name=None,
        time_reference="this evening",
        target_group="general",
        is_clarification_needed=False
    )

    geo_bhopal = GeocodingResult(
        resolved_name="Bhopal, India",
        latitude=23.25,
        longitude=77.41,
        timezone="Asia/Kolkata"
    )
    facts_evening = WeatherFacts(
        temperature_c=25.0,
        wind_speed_kmh=15.0,
        wind_gusts_kmh=20.0,
        precipitation_mm=0.0,
        precipitation_probability=0,
        uv_index=1.0,
        target_period="evening"
    )

    with patch("app.graph.nodes.extract_intent", new_callable=AsyncMock) as mock_extract, \
         patch("app.graph.nodes.resolve_location", new_callable=AsyncMock) as mock_geo, \
         patch("app.graph.nodes.fetch_weather_facts", new_callable=AsyncMock) as mock_weather:

        mock_geo.return_value = geo_bhopal
        mock_weather.return_value = facts_evening

        # Turn 1
        mock_extract.return_value = turn1_intent
        res1 = await graph.ainvoke({
            "session_id": "session-retain-act",
            "user_message": "Can I cycle in Bhopal today?"
        })
        assert res1["activity"] == "cycling"
        assert res1["location_name"] == "Bhopal"

        # Turn 2: "What about this evening?"
        mock_extract.return_value = turn2_intent
        res2 = await graph.ainvoke({
            "session_id": "session-retain-act",
            "user_message": "What about this evening?"
        })
        assert res2["activity"] == "cycling"  # Retained
        assert res2["location_name"] == "Bhopal"  # Retained
        assert "evening" in res2["time_reference"].lower()  # Updated time
        assert res2["response_type"] == "SUCCESS"


@pytest.mark.asyncio
async def test_follow_up_changing_time(graph):
    """
    Test 3: Follow-up changing only time scope ('tomorrow afternoon').
    """
    turn1_intent = StructuredIntent(
        activity="cycling",
        intent_category="outdoor_exercise",
        location_name="Bhopal",
        time_reference="today",
        target_group="general"
    )
    turn2_intent = StructuredIntent(
        activity=None,
        location_name=None,
        time_reference="tomorrow afternoon",
        target_group="general"
    )

    with patch("app.graph.nodes.extract_intent", new_callable=AsyncMock) as mock_extract, \
         patch("app.graph.nodes.resolve_location", new_callable=AsyncMock) as mock_geo, \
         patch("app.graph.nodes.fetch_weather_facts", new_callable=AsyncMock) as mock_weather:

        mock_geo.return_value = GeocodingResult(
            resolved_name="Bhopal, India",
            latitude=23.25,
            longitude=77.41,
            timezone="Asia/Kolkata"
        )
        mock_weather.return_value = WeatherFacts(
            temperature_c=29.0,
            wind_speed_kmh=10.0,
            wind_gusts_kmh=15.0,
            target_period="tomorrow afternoon"
        )

        mock_extract.return_value = turn1_intent
        await graph.ainvoke({
            "session_id": "sess-time-change",
            "user_message": "Can I cycle in Bhopal today?"
        })

        mock_extract.return_value = turn2_intent
        res2 = await graph.ainvoke({
            "session_id": "sess-time-change",
            "user_message": "What about tomorrow afternoon?"
        })

        assert res2["activity"] == "cycling"
        assert res2["location_name"] == "Bhopal"
        assert "tomorrow afternoon" in res2["time_reference"]


@pytest.mark.asyncio
async def test_follow_up_changing_location(graph):
    """
    Test 4: User changes location to 'Delhi'.
    The new location replaces previous location and triggers fresh geocoding.
    """
    turn1_intent = StructuredIntent(
        activity="cycling",
        location_name="Bhopal",
        time_reference="today"
    )
    turn2_intent = StructuredIntent(
        activity=None,
        location_name="Delhi",
        time_reference="today"
    )

    geo_bhopal = GeocodingResult(resolved_name="Bhopal, India", latitude=23.25, longitude=77.41, timezone="Asia/Kolkata")
    geo_delhi = GeocodingResult(resolved_name="Delhi, India", latitude=28.61, longitude=77.20, timezone="Asia/Kolkata")

    with patch("app.graph.nodes.extract_intent", new_callable=AsyncMock) as mock_extract, \
         patch("app.graph.nodes.resolve_location", new_callable=AsyncMock) as mock_geo, \
         patch("app.graph.nodes.fetch_weather_facts", new_callable=AsyncMock) as mock_weather:

        mock_weather.return_value = WeatherFacts(temperature_c=26.0, wind_speed_kmh=12.0)

        # Turn 1: Bhopal
        mock_extract.return_value = turn1_intent
        mock_geo.return_value = geo_bhopal
        res1 = await graph.ainvoke({
            "session_id": "sess-loc-change",
            "user_message": "Can I cycle in Bhopal today?"
        })
        assert res1["location_name"] == "Bhopal"
        assert res1["latitude"] == 23.25

        # Turn 2: Delhi
        mock_extract.return_value = turn2_intent
        mock_geo.return_value = geo_delhi
        res2 = await graph.ainvoke({
            "session_id": "sess-loc-change",
            "user_message": "What about Delhi?"
        })
        assert res2["location_name"] == "Delhi"
        assert res2["activity"] == "cycling"  # Retained
        assert res2["latitude"] == 28.61  # Freshly geocoded!
        assert res2["resolved_location_name"] == "Delhi, India"


@pytest.mark.asyncio
async def test_follow_up_changing_activity(graph):
    """
    Test 5: User changes activity from cycling to running.
    The new activity replaces the previous one.
    """
    turn1_intent = StructuredIntent(activity="cycling", location_name="Bhopal", time_reference="today")
    turn2_intent = StructuredIntent(activity="running", location_name=None, time_reference="today")

    with patch("app.graph.nodes.extract_intent", new_callable=AsyncMock) as mock_extract, \
         patch("app.graph.nodes.resolve_location", new_callable=AsyncMock) as mock_geo, \
         patch("app.graph.nodes.fetch_weather_facts", new_callable=AsyncMock) as mock_weather:

        mock_geo.return_value = GeocodingResult(resolved_name="Bhopal, India", latitude=23.25, longitude=77.41, timezone="Asia/Kolkata")
        mock_weather.return_value = WeatherFacts(temperature_c=25.0, wind_speed_kmh=10.0)

        mock_extract.return_value = turn1_intent
        res1 = await graph.ainvoke({"session_id": "sess-act-change", "user_message": "Can I cycle in Bhopal today?"})
        assert res1["activity"] == "cycling"

        mock_extract.return_value = turn2_intent
        res2 = await graph.ainvoke({"session_id": "sess-act-change", "user_message": "What about running?"})
        assert res2["activity"] == "running"
        assert res2["location_name"] == "Bhopal"


@pytest.mark.asyncio
async def test_two_sessions_remain_isolated(graph):
    """
    Test 6 & 7: Two sessions remain isolated with zero cross-session context leakage.
    Session A: "Can I cycle in Bhopal today?" -> complete.
    Session B: "What about this evening?" -> must NOT inherit Bhopal or cycling!
    """
    turn_a_intent = StructuredIntent(activity="cycling", location_name="Bhopal", time_reference="today")
    turn_b_intent = StructuredIntent(activity=None, location_name=None, time_reference="this evening", is_clarification_needed=True)

    with patch("app.graph.nodes.extract_intent", new_callable=AsyncMock) as mock_extract, \
         patch("app.graph.nodes.resolve_location", new_callable=AsyncMock) as mock_geo, \
         patch("app.graph.nodes.fetch_weather_facts", new_callable=AsyncMock) as mock_weather:

        mock_geo.return_value = GeocodingResult(resolved_name="Bhopal, India", latitude=23.25, longitude=77.41, timezone="Asia/Kolkata")
        mock_weather.return_value = WeatherFacts(
            temperature_c=25.0,
            wind_speed_kmh=44.0,  # Matches SOP-CYCLING-WIND-001
            precipitation_mm=0.0
        )

        # Session A completes successfully
        mock_extract.return_value = turn_a_intent
        res_a = await graph.ainvoke({
            "session_id": "session-A",
            "user_message": "Can I cycle in Bhopal today?"
        })
        assert res_a["response_type"] == "SUCCESS"
        assert res_a["activity"] == "cycling"
        assert res_a["location_name"] == "Bhopal"
        assert res_a["selected_sop"]["sop_id"] == "SOP-CYCLING-WIND-001"

        # Session B starts asking "What about this evening?"
        mock_extract.return_value = turn_b_intent
        res_b = await graph.ainvoke({
            "session_id": "session-B",
            "user_message": "What about this evening?"
        })
        # Session B MUST NOT inherit Bhopal or cycling
        assert res_b["activity"] is None
        assert res_b["location_name"] is None
        assert res_b["response_type"] == "INTENT_CLARIFICATION"
        assert "specify which outdoor activity" in res_b["response"]


@pytest.mark.asyncio
async def test_same_session_id_preserves_context_across_separate_graph_invocations(graph):
    """
    Test 8: Invocations sharing the same session_id retain state across multiple separate calls.
    """
    with patch("app.graph.nodes.extract_intent", new_callable=AsyncMock) as mock_extract, \
         patch("app.graph.nodes.resolve_location", new_callable=AsyncMock) as mock_geo, \
         patch("app.graph.nodes.fetch_weather_facts", new_callable=AsyncMock) as mock_weather:

        mock_geo.return_value = GeocodingResult(resolved_name="Paris, France", latitude=48.85, longitude=2.35, timezone="Europe/Paris")
        mock_weather.return_value = WeatherFacts(temperature_c=20.0, wind_speed_kmh=15.0)

        mock_extract.return_value = StructuredIntent(activity="walking", location_name="Paris", time_reference="today")
        res1 = await graph.ainvoke({"session_id": "multi-call-sess", "user_message": "Can I walk in Paris today?"})
        assert res1["chat_history"] is not None
        assert len(res1["chat_history"]) == 2  # 1 user + 1 assistant

        mock_extract.return_value = StructuredIntent(activity=None, location_name=None, time_reference="tonight")
        res2 = await graph.ainvoke({"session_id": "multi-call-sess", "user_message": "What about tonight?"})
        assert res2["activity"] == "walking"
        assert res2["location_name"] == "Paris"
        assert len(res2["chat_history"]) == 4  # Preserved chat history across invocations!


@pytest.mark.asyncio
async def test_new_session_id_starts_without_prior_context(graph):
    """
    Test 9: A brand new session_id starts with a completely clean state.
    """
    with patch("app.graph.nodes.extract_intent", new_callable=AsyncMock) as mock_extract:
        mock_extract.return_value = StructuredIntent(activity="cycling", location_name=None, is_clarification_needed=False)

        res = await graph.ainvoke({
            "session_id": "brand-new-isolated-session",
            "user_message": "Can I cycle?"
        })
        # Missing location -> requires clarification
        assert res["response_type"] == "INTENT_CLARIFICATION"
        assert "Which city or location" in res["response"]


@pytest.mark.asyncio
async def test_updated_location_time_causes_fresh_weather_retrieval(graph):
    """
    Test 10: Stale weather facts are invalidated; every follow-up performs a fresh weather retrieval.
    """
    turn1_facts = WeatherFacts(temperature_c=28.0, wind_speed_kmh=10.0, target_period="today")
    turn2_facts = WeatherFacts(temperature_c=22.0, wind_speed_kmh=25.0, target_period="this evening")

    with patch("app.graph.nodes.extract_intent", new_callable=AsyncMock) as mock_extract, \
         patch("app.graph.nodes.resolve_location", new_callable=AsyncMock) as mock_geo, \
         patch("app.graph.nodes.fetch_weather_facts", new_callable=AsyncMock) as mock_weather:

        mock_geo.return_value = GeocodingResult(resolved_name="Bhopal, India", latitude=23.25, longitude=77.41, timezone="Asia/Kolkata")
        
        # Turn 1
        mock_extract.return_value = StructuredIntent(activity="cycling", location_name="Bhopal", time_reference="today")
        mock_weather.return_value = turn1_facts
        res1 = await graph.ainvoke({"session_id": "sess-weather-fresh", "user_message": "Can I cycle in Bhopal today?"})
        assert res1["weather_facts"]["temperature_c"] == 28.0
        assert mock_weather.call_count == 1

        # Turn 2
        mock_extract.return_value = StructuredIntent(activity=None, location_name=None, time_reference="this evening")
        mock_weather.return_value = turn2_facts
        res2 = await graph.ainvoke({"session_id": "sess-weather-fresh", "user_message": "What about this evening?"})
        assert res2["weather_facts"]["temperature_c"] == 22.0  # Freshly retrieved facts
        assert mock_weather.call_count == 2  # Weather was fetched a second time!


@pytest.mark.asyncio
async def test_newly_fetched_weather_remains_authoritative(graph):
    """
    Test 11: Memory never overrides freshly fetched weather data.
    Turn 1: Wind is 15 km/h -> caution.
    Turn 2: Wind spikes to 45 km/h (SOP-CYCLING-WIND-001) -> not_recommended.
    The decision in Turn 2 must be strictly governed by the newly fetched 45 km/h.
    """
    # Turn 1 triggers SOP-UV-EXERCISE-001 (MEDIUM severity, caution)
    facts_turn1 = WeatherFacts(
        temperature_c=28.0,
        wind_speed_kmh=15.0,
        wind_gusts_kmh=20.0,
        precipitation_mm=0.0,
        uv_index=9.0,
        is_daytime=True
    )
    # Turn 2 triggers SOP-CYCLING-WIND-001 (HIGH severity, not_recommended)
    facts_turn2 = WeatherFacts(
        temperature_c=22.0,
        wind_speed_kmh=45.0,
        wind_gusts_kmh=55.0,
        precipitation_mm=0.0,
        uv_index=1.0,
        is_daytime=False
    )

    with patch("app.graph.nodes.extract_intent", new_callable=AsyncMock) as mock_extract, \
         patch("app.graph.nodes.resolve_location", new_callable=AsyncMock) as mock_geo, \
         patch("app.graph.nodes.fetch_weather_facts", new_callable=AsyncMock) as mock_weather:

        mock_geo.return_value = GeocodingResult(resolved_name="Bhopal, India", latitude=23.25, longitude=77.41, timezone="Asia/Kolkata")

        # Turn 1: High UV causes CAUTION
        mock_extract.return_value = StructuredIntent(
            activity="cycling",
            intent_category="outdoor_exercise",
            location_name="Bhopal",
            time_reference="today"
        )
        mock_weather.return_value = facts_turn1
        res1 = await graph.ainvoke({"session_id": "sess-auth-weather", "user_message": "Can I cycle in Bhopal today?"})
        assert res1["decision_recommendation"] == "caution"
        assert res1["decision_severity"] == "MEDIUM"
        assert res1["selected_sop"]["sop_id"] == "SOP-UV-EXERCISE-001"

        # Turn 2: Gale wind in evening causes NOT_RECOMMENDED
        mock_extract.return_value = StructuredIntent(
            activity=None,
            intent_category=None,
            location_name=None,
            time_reference="this evening"
        )
        mock_weather.return_value = facts_turn2
        res2 = await graph.ainvoke({"session_id": "sess-auth-weather", "user_message": "What about this evening?"})
        
        # Decision must be updated strictly to NOT_RECOMMENDED under SOP-CYCLING-WIND-001
        assert res2["decision_recommendation"] == "not_recommended"
        assert res2["decision_severity"] == "HIGH"
        assert res2["selected_sop"]["sop_id"] == "SOP-CYCLING-WIND-001"
        assert res2["weather_facts"]["wind_speed_kmh"] == 45.0


@pytest.mark.asyncio
async def test_explicit_thread_id_config(graph):
    """
    Test 12: Verify explicit config passing via session_manager.get_thread_config().
    """
    config = session_manager.get_thread_config("explicit-sess-123")
    assert config == {"configurable": {"thread_id": "explicit-sess-123"}}

    with patch("app.graph.nodes.extract_intent", new_callable=AsyncMock) as mock_extract, \
         patch("app.graph.nodes.resolve_location", new_callable=AsyncMock) as mock_geo, \
         patch("app.graph.nodes.fetch_weather_facts", new_callable=AsyncMock) as mock_weather:

        mock_geo.return_value = GeocodingResult(resolved_name="Bhopal, India", latitude=23.25, longitude=77.41, timezone="Asia/Kolkata")
        mock_weather.return_value = WeatherFacts(
            temperature_c=25.0,
            wind_speed_kmh=42.0,  # Matches SOP-CYCLING-WIND-001
            precipitation_mm=0.0
        )
        mock_extract.return_value = StructuredIntent(
            activity="cycling",
            intent_category="outdoor_exercise",
            location_name="Bhopal",
            time_reference="today"
        )

        res = await graph.ainvoke(
            {"user_message": "Can I cycle in Bhopal today?"},
            config=config
        )
        assert res["response_type"] == "SUCCESS"
        assert res["activity"] == "cycling"
        assert res["location_name"] == "Bhopal"
        assert res["selected_sop"]["sop_id"] == "SOP-CYCLING-WIND-001"
