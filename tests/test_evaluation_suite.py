"""
Automated PyTest integration for the 8 Evaluation Suite scenarios.
Verifies that all 8 evaluation cases pass under automated testing.
"""
import pytest
from evals.eval_suite import (
    evaluate_case_1_clear_sop,
    evaluate_case_2_another_clear_sop,
    evaluate_case_3_paraphrased_intent,
    evaluate_case_4_another_paraphrased_intent,
    evaluate_case_5_severe_live_weather,
    evaluate_case_6_no_sop,
    evaluate_case_7_weather_api_failure,
    evaluate_case_8_adversarial_prompt_injection,
)


@pytest.mark.asyncio
async def test_eval_case_1_clear_sop():
    result = await evaluate_case_1_clear_sop()
    assert result.status == "PASS", f"Case 1 failed: {result.actual_result}"
    assert result.actual_result["selected_sop_id"] == "SOP-CYCLING-WIND-001"
    assert result.actual_result["decision_recommendation"] == "not_recommended"


@pytest.mark.asyncio
async def test_eval_case_2_another_clear_sop():
    result = await evaluate_case_2_another_clear_sop()
    assert result.status == "PASS", f"Case 2 failed: {result.actual_result}"
    assert result.actual_result["selected_sop_id"] == "SOP-WIND-TWOWHEELER-001"
    assert result.actual_result["decision_recommendation"] == "not_recommended"


@pytest.mark.asyncio
async def test_eval_case_3_paraphrased_intent():
    result = await evaluate_case_3_paraphrased_intent()
    assert result.status == "PASS", f"Case 3 failed: {result.actual_result}"
    assert result.actual_result["extracted_activity"] == "cycling"
    assert result.actual_result["extracted_location"] == "London"


@pytest.mark.asyncio
async def test_eval_case_4_another_paraphrased_intent():
    result = await evaluate_case_4_another_paraphrased_intent()
    assert result.status == "PASS", f"Case 4 failed: {result.actual_result}"
    assert result.actual_result["target_group"] == "child"
    assert result.actual_result["activity"] == "park"
    assert result.actual_result["selected_sop_id"] == "SOP-RAIN-CHILD-PARK-001"


@pytest.mark.asyncio
async def test_eval_case_5_severe_live_weather():
    result = await evaluate_case_5_severe_live_weather()
    assert result.status == "PASS", f"Case 5 failed: {result.actual_result}"
    assert result.actual_result["response_type"] in ["SUCCESS", "NO_SOP"]
    assert result.actual_result["coordinates"]["latitude"] is not None
    assert result.actual_result["coordinates"]["longitude"] is not None
    assert result.actual_result["live_weather_facts"]["retrieved_at"] is not None


@pytest.mark.asyncio
async def test_eval_case_6_no_sop():
    result = await evaluate_case_6_no_sop()
    assert result.status == "PASS", f"Case 6 failed: {result.actual_result}"
    assert result.actual_result["response_type"] == "NO_SOP"
    assert result.actual_result["selected_sop"] is None


@pytest.mark.asyncio
async def test_eval_case_7_weather_api_failure():
    result = await evaluate_case_7_weather_api_failure()
    assert result.status == "PASS", f"Case 7 failed: {result.actual_result}"
    assert result.actual_result["response_type"] == "WEATHER_FAILURE"
    assert result.actual_result["weather_facts"] is None
    assert result.actual_result["decision_recommendation"] is None


@pytest.mark.asyncio
async def test_eval_case_8_adversarial_prompt_injection():
    result = await evaluate_case_8_adversarial_prompt_injection()
    assert result.status == "PASS", f"Case 8 failed: {result.actual_result}"
    assert result.actual_result["selected_sop_id"] == "SOP-CYCLING-WIND-001"
    assert result.actual_result["decision_recommendation"] == "not_recommended"
    assert result.actual_result["decision_severity"] == "HIGH"
