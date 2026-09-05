import logging
from typing import Dict, Any, List, Tuple
from app.policies.models import (
    SOPRule,
    ConditionRule,
    MatchedCondition,
    CandidateSOP,
)

logger = logging.getLogger("weather-advisory-bot.policies.matcher")


class PolicyEvaluationError(Exception):
    """Raised when evaluation fails due to unsupported operators or malformed condition data."""
    pass


def _normalize_value(val: Any) -> Any:
    """Normalizes string values for case-insensitive comparison."""
    if isinstance(val, str):
        return val.strip().lower()
    return val


def evaluate_atomic_condition(
    condition: ConditionRule,
    facts: Dict[str, Any]
) -> MatchedCondition:
    """
    Evaluates a single ConditionRule against trusted facts.
    Distinguishes condition failure from data unavailability.
    """
    field = condition.field
    op = condition.operator
    expected = condition.value

    # Check if field exists and is not None in facts
    if field not in facts or facts[field] is None:
        return MatchedCondition(
            field=field,
            operator=op,
            threshold=expected,
            actual=None,
            result=False,
            status="UNAVAILABLE"
        )

    actual = facts[field]
    norm_actual = _normalize_value(actual)
    norm_expected = _normalize_value(expected) if not isinstance(expected, (list, tuple, dict)) else expected

    result = False

    try:
        if op == "equals":
            result = norm_actual == norm_expected
        elif op == "not_equals":
            result = norm_actual != norm_expected
        elif op == "greater_than":
            result = float(actual) > float(expected)
        elif op == "greater_than_or_equal":
            result = float(actual) >= float(expected)
        elif op == "less_than":
            result = float(actual) < float(expected)
        elif op == "less_than_or_equal":
            result = float(actual) <= float(expected)
        elif op == "in":
            if isinstance(expected, (list, tuple, set)):
                norm_list = [_normalize_value(x) for x in expected]
                result = norm_actual in norm_list
            elif isinstance(expected, str):
                result = str(norm_actual) in str(norm_expected)
            else:
                result = actual in expected
        elif op == "not_in":
            if isinstance(expected, (list, tuple, set)):
                norm_list = [_normalize_value(x) for x in expected]
                result = norm_actual not in norm_list
            else:
                result = actual not in expected
        elif op == "between":
            if not isinstance(expected, (list, tuple)) or len(expected) != 2:
                raise PolicyEvaluationError(
                    f"'between' operator requires [min, max] list, got: {expected}"
                )
            low, high = float(expected[0]), float(expected[1])
            result = low <= float(actual) <= high
        else:
            raise PolicyEvaluationError(f"Unsupported operator encountered: '{op}'")

    except (ValueError, TypeError) as ex:
        logger.debug(f"Comparison error for field '{field}' ({actual}) with operator '{op}': {ex}")
        result = False

    return MatchedCondition(
        field=field,
        operator=op,
        threshold=expected,
        actual=actual,
        result=result,
        status="PASSED" if result else "FAILED"
    )


def evaluate_sop(
    sop: SOPRule,
    facts: Dict[str, Any]
) -> Tuple[bool, List[MatchedCondition]]:
    """
    Evaluates an entire SOP against facts.
    Returns (is_matched, matched_conditions_audit).
    """
    # 1. Verify required weather fields are present
    for req_field in sop.required_weather_fields:
        if req_field not in facts or facts[req_field] is None:
            # Required weather field missing -> SOP cannot safely evaluate
            unavailable_audit = MatchedCondition(
                field=req_field,
                operator="required_field_check",
                threshold="PRESENT",
                actual=None,
                result=False,
                status="UNAVAILABLE"
            )
            return False, [unavailable_audit]

    matched_conditions: List[MatchedCondition] = []

    # 2. Evaluate 'all' block (logical AND)
    if sop.conditions.all is not None:
        all_passed = True
        for cond in sop.conditions.all:
            eval_res = evaluate_atomic_condition(cond, facts)
            matched_conditions.append(eval_res)
            if not eval_res.result:
                all_passed = False

        if not all_passed:
            return False, matched_conditions

    # 3. Evaluate 'any' block (logical OR)
    if sop.conditions.any is not None:
        any_passed = False
        any_conditions_evaluated: List[MatchedCondition] = []
        for cond in sop.conditions.any:
            eval_res = evaluate_atomic_condition(cond, facts)
            any_conditions_evaluated.append(eval_res)
            if eval_res.result:
                any_passed = True

        matched_conditions.extend(any_conditions_evaluated)
        if not any_passed:
            return False, matched_conditions

    return True, matched_conditions


def match_candidate_sops(
    sops: List[SOPRule],
    facts: Dict[str, Any]
) -> List[CandidateSOP]:
    """
    Evaluates all configured SOPs against trusted facts.
    Does NOT stop at the first match; collects all candidate SOPs.
    """
    candidates: List[CandidateSOP] = []

    for sop in sops:
        is_matched, condition_audit = evaluate_sop(sop, facts)
        if is_matched:
            # Filter only passed conditions for concise decision trace
            passed_audit = [c for c in condition_audit if c.status == "PASSED"]
            candidates.append(
                CandidateSOP(
                    sop_id=sop.id,
                    name=sop.name,
                    category=sop.category,
                    severity=sop.severity,
                    priority=sop.priority,
                    matched_conditions=passed_audit
                )
            )

    return candidates
