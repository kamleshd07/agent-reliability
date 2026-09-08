"""Coverage for the DX-1 (Developer Adoption) additive built-in evaluators.

(The file keeps its original "m8" module name for historical git-blame
continuity; see CHANGELOG.md for why this milestone is labeled "DX-1", not
"M8", in release-facing docs.)

Every evaluator here is exercised for: normal PASS, normal FAIL, legitimate
UNKNOWN (where applicable), invalid configuration, wrong input type, empty
input (where applicable), unicode (where applicable), and deterministic
provenance/config identity (equal construction => equal instances, usable as
a stable ``EvaluatorRunner``-facing configuration).
"""

from __future__ import annotations

import re

import pytest

from agent_reliability.domain import EvaluationOutcome
from agent_reliability.evaluation import (
    ContainsEvaluator,
    EvaluationExecutionFailure,
    EvaluatorIdentity,
    LatencyThresholdEvaluator,
    RegexMatchEvaluator,
    ToolCalledEvaluator,
    ToolNotCalledEvaluator,
)
from agent_reliability.sdk import EvaluatorRunner

# ---------------------------------------------------------------------------
# ContainsEvaluator
# ---------------------------------------------------------------------------


def test_contains_pass_and_fail() -> None:
    evaluator = ContainsEvaluator(EvaluatorIdentity("contains", "1"), "refund")
    assert (
        evaluator.evaluate("your refund is approved").outcome is EvaluationOutcome.PASS
    )
    assert (
        evaluator.evaluate("your request is approved").outcome is EvaluationOutcome.FAIL
    )


def test_contains_case_sensitivity() -> None:
    sensitive = ContainsEvaluator(EvaluatorIdentity("contains", "1"), "OK")
    assert sensitive.evaluate("ok").outcome is EvaluationOutcome.FAIL
    insensitive = ContainsEvaluator(
        EvaluatorIdentity("contains", "1"), "OK", case_sensitive=False
    )
    assert insensitive.evaluate("ok").outcome is EvaluationOutcome.PASS


def test_contains_unicode_casefold() -> None:
    evaluator = ContainsEvaluator(
        EvaluatorIdentity("contains", "1"), "STRASSE", case_sensitive=False
    )
    assert evaluator.evaluate("die straße ist lang").outcome is EvaluationOutcome.PASS


def test_contains_rejects_empty_substring_at_construction() -> None:
    """Regression: substring="" used to make ContainsEvaluator PASS on every
    input (Python's own "" in value is always True) — a silent, always-100%-
    reliability misconfiguration. It must now fail fast at construction,
    never be deferred to evaluate(), and never surface as UNKNOWN."""
    with pytest.raises(ValueError, match="substring must not be empty"):
        ContainsEvaluator(EvaluatorIdentity("contains", "1"), "")


def test_contains_whitespace_only_substring_is_not_rejected() -> None:
    """Whitespace can be a legitimate substring to check for; only the
    truly empty string is invalid."""
    evaluator = ContainsEvaluator(EvaluatorIdentity("contains", "1"), " ")
    assert evaluator.evaluate("a b").outcome is EvaluationOutcome.PASS
    assert evaluator.evaluate("ab").outcome is EvaluationOutcome.FAIL


def test_contains_non_empty_substring_behavior_unchanged() -> None:
    """Existing non-empty-substring PASS/FAIL semantics are unaffected by
    the empty-substring rejection."""
    evaluator = ContainsEvaluator(EvaluatorIdentity("contains", "1"), "refund")
    assert evaluator.evaluate("your refund is approved").outcome is (
        EvaluationOutcome.PASS
    )
    assert evaluator.evaluate("nothing to see here").outcome is EvaluationOutcome.FAIL


def test_contains_rejects_wrong_input_type() -> None:
    evaluator = ContainsEvaluator(EvaluatorIdentity("contains", "1"), "x")
    with pytest.raises(TypeError, match="value must be a str"):
        evaluator.evaluate(123)  # type: ignore[arg-type]


def test_contains_rejects_invalid_configuration() -> None:
    with pytest.raises(TypeError, match="substring must be a str"):
        ContainsEvaluator(EvaluatorIdentity("contains", "1"), 5)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="case_sensitive must be a bool"):
        ContainsEvaluator(
            EvaluatorIdentity("contains", "1"),
            "x",
            case_sensitive="yes",  # type: ignore[arg-type]
        )


def test_contains_stable_configuration_identity() -> None:
    a = ContainsEvaluator(EvaluatorIdentity("contains", "1"), "x")
    b = ContainsEvaluator(EvaluatorIdentity("contains", "1"), "x")
    assert a == b
    assert a.identity == b.identity
    assert a.deterministic is True


def test_contains_evaluator_exception_becomes_execution_failure_not_unknown() -> None:
    evaluator = ContainsEvaluator(EvaluatorIdentity("contains", "1"), "x")
    result = EvaluatorRunner().evaluate(evaluator, 123)  # type: ignore[arg-type]
    assert isinstance(result, EvaluationExecutionFailure)
    assert result.exception_type == "TypeError"


# ---------------------------------------------------------------------------
# RegexMatchEvaluator
# ---------------------------------------------------------------------------


def test_regex_search_pass_and_fail() -> None:
    evaluator = RegexMatchEvaluator(EvaluatorIdentity("regex", "1"), r"\d{3}-\d{4}")
    assert evaluator.evaluate("call 555-1234 now").outcome is EvaluationOutcome.PASS
    assert evaluator.evaluate("no phone here").outcome is EvaluationOutcome.FAIL


def test_regex_fullmatch_semantics() -> None:
    evaluator = RegexMatchEvaluator(
        EvaluatorIdentity("regex", "1"), r"[a-z]+", fullmatch=True
    )
    assert evaluator.evaluate("abc").outcome is EvaluationOutcome.PASS
    assert evaluator.evaluate("abc123").outcome is EvaluationOutcome.FAIL
    search_mode = RegexMatchEvaluator(EvaluatorIdentity("regex", "1"), r"[a-z]+")
    assert search_mode.evaluate("abc123").outcome is EvaluationOutcome.PASS


def test_regex_flags_support() -> None:
    evaluator = RegexMatchEvaluator(
        EvaluatorIdentity("regex", "1"), "hello", flags=re.IGNORECASE
    )
    assert evaluator.evaluate("HELLO world").outcome is EvaluationOutcome.PASS


def test_regex_unicode() -> None:
    evaluator = RegexMatchEvaluator(EvaluatorIdentity("regex", "1"), r"^\w+$")
    assert evaluator.evaluate("café").outcome is EvaluationOutcome.PASS


def test_regex_empty_value() -> None:
    evaluator = RegexMatchEvaluator(EvaluatorIdentity("regex", "1"), r"^$")
    assert evaluator.evaluate("").outcome is EvaluationOutcome.PASS


def test_malformed_regex_fails_at_construction_not_evaluation() -> None:
    with pytest.raises(ValueError, match="invalid regex pattern"):
        RegexMatchEvaluator(EvaluatorIdentity("regex", "1"), "[unclosed")


def test_regex_rejects_wrong_input_type() -> None:
    evaluator = RegexMatchEvaluator(EvaluatorIdentity("regex", "1"), "x")
    with pytest.raises(TypeError, match="value must be a str"):
        evaluator.evaluate(None)  # type: ignore[arg-type]


def test_regex_rejects_invalid_configuration() -> None:
    with pytest.raises(TypeError, match="pattern must be a str"):
        RegexMatchEvaluator(EvaluatorIdentity("regex", "1"), 5)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="fullmatch must be a bool"):
        RegexMatchEvaluator(EvaluatorIdentity("regex", "1"), "x", fullmatch=1)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match=r"flags must be a re\.RegexFlag"):
        RegexMatchEvaluator(EvaluatorIdentity("regex", "1"), "x", flags=1)  # type: ignore[arg-type]


def test_regex_stable_configuration_identity() -> None:
    a = RegexMatchEvaluator(EvaluatorIdentity("regex", "1"), r"^ok$")
    b = RegexMatchEvaluator(EvaluatorIdentity("regex", "1"), r"^ok$")
    assert a == b
    assert hash(a) == hash(b)


def test_regex_deterministic_property() -> None:
    assert (
        RegexMatchEvaluator(EvaluatorIdentity("regex", "1"), "x").deterministic is True
    )


# ---------------------------------------------------------------------------
# LatencyThresholdEvaluator
# ---------------------------------------------------------------------------


def test_latency_pass_and_fail_inclusive_default() -> None:
    evaluator = LatencyThresholdEvaluator(EvaluatorIdentity("latency", "1"), 2.0)
    assert evaluator.evaluate(1.5).outcome is EvaluationOutcome.PASS
    assert evaluator.evaluate(2.0).outcome is EvaluationOutcome.PASS  # inclusive
    assert evaluator.evaluate(2.1).outcome is EvaluationOutcome.FAIL


def test_latency_exclusive_boundary() -> None:
    evaluator = LatencyThresholdEvaluator(
        EvaluatorIdentity("latency", "1"), 2.0, inclusive=False
    )
    assert evaluator.evaluate(2.0).outcome is EvaluationOutcome.FAIL
    assert evaluator.evaluate(1.999).outcome is EvaluationOutcome.PASS


def test_latency_missing_measurement_is_unknown_never_fail() -> None:
    evaluator = LatencyThresholdEvaluator(EvaluatorIdentity("latency", "1"), 2.0)
    decision = evaluator.evaluate(None)
    assert decision.outcome is EvaluationOutcome.UNKNOWN
    assert decision.reason_code == "measurement_unavailable"


def test_negative_threshold_is_a_construction_time_config_error() -> None:
    with pytest.raises(ValueError, match="threshold_seconds must be >= 0"):
        LatencyThresholdEvaluator(EvaluatorIdentity("latency", "1"), -1.0)


def test_threshold_rejects_wrong_type_and_non_finite() -> None:
    with pytest.raises(TypeError, match="threshold_seconds must be an int or float"):
        LatencyThresholdEvaluator(EvaluatorIdentity("latency", "1"), "2")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="threshold_seconds must be a finite number"):
        LatencyThresholdEvaluator(EvaluatorIdentity("latency", "1"), float("inf"))
    with pytest.raises(ValueError, match="threshold_seconds must be a finite number"):
        LatencyThresholdEvaluator(EvaluatorIdentity("latency", "1"), float("nan"))


def test_inclusive_rejects_wrong_type() -> None:
    with pytest.raises(TypeError, match="inclusive must be a bool"):
        LatencyThresholdEvaluator(EvaluatorIdentity("latency", "1"), 1.0, inclusive=1)  # type: ignore[arg-type]


def test_duration_rejects_non_finite_value() -> None:
    evaluator = LatencyThresholdEvaluator(EvaluatorIdentity("latency", "1"), 2.0)
    with pytest.raises(ValueError, match="duration_seconds must be a finite number"):
        evaluator.evaluate(float("nan"))


def test_latency_rejects_wrong_input_type_and_negative_value() -> None:
    evaluator = LatencyThresholdEvaluator(EvaluatorIdentity("latency", "1"), 2.0)
    with pytest.raises(TypeError, match="duration_seconds must be"):
        evaluator.evaluate("slow")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="duration_seconds must be >= 0"):
        evaluator.evaluate(-0.5)


def test_latency_stable_configuration_identity() -> None:
    a = LatencyThresholdEvaluator(EvaluatorIdentity("latency", "1"), 2.0)
    b = LatencyThresholdEvaluator(EvaluatorIdentity("latency", "1"), 2.0)
    assert a == b


def test_latency_evaluator_exception_becomes_execution_failure_not_unknown() -> None:
    """Adversarial: a genuine misuse (wrong type) must surface as an
    EvaluatorRunner execution failure, never as UNKNOWN and never as FAIL."""
    evaluator = LatencyThresholdEvaluator(EvaluatorIdentity("latency", "1"), 2.0)
    result = EvaluatorRunner().evaluate(evaluator, "not-a-number")  # type: ignore[arg-type]
    assert isinstance(result, EvaluationExecutionFailure)
    assert result.exception_type == "TypeError"


# ---------------------------------------------------------------------------
# ToolCalledEvaluator / ToolNotCalledEvaluator
# ---------------------------------------------------------------------------


def test_tool_called_pass_and_fail() -> None:
    evaluator = ToolCalledEvaluator(EvaluatorIdentity("tool-called", "1"), "refund")
    assert (
        evaluator.evaluate(frozenset({"refund", "lookup"})).outcome
        is EvaluationOutcome.PASS
    )
    assert evaluator.evaluate(frozenset({"lookup"})).outcome is EvaluationOutcome.FAIL


def test_tool_called_empty_set() -> None:
    evaluator = ToolCalledEvaluator(EvaluatorIdentity("tool-called", "1"), "refund")
    assert evaluator.evaluate(frozenset()).outcome is EvaluationOutcome.FAIL


def test_tool_not_called_pass_and_fail() -> None:
    evaluator = ToolNotCalledEvaluator(
        EvaluatorIdentity("tool-not-called", "1"), "delete_account"
    )
    assert evaluator.evaluate(frozenset({"refund"})).outcome is EvaluationOutcome.PASS
    assert (
        evaluator.evaluate(frozenset({"delete_account"})).outcome
        is EvaluationOutcome.FAIL
    )


def test_tool_evaluators_reject_invalid_configuration() -> None:
    with pytest.raises(ValueError, match="tool_name must be a non-blank str"):
        ToolCalledEvaluator(EvaluatorIdentity("tool-called", "1"), "")
    with pytest.raises(ValueError, match="tool_name must be a non-blank str"):
        ToolNotCalledEvaluator(EvaluatorIdentity("tool-not-called", "1"), "")


def test_tool_evaluators_reject_whitespace_only_tool_name() -> None:
    """A tool named entirely by whitespace has no credible legitimate use
    case and is far more likely to be a call-site bug; reject it at
    construction like the empty-string case."""
    with pytest.raises(ValueError, match="tool_name must be a non-blank str"):
        ToolCalledEvaluator(EvaluatorIdentity("tool-called", "1"), "   ")
    with pytest.raises(ValueError, match="tool_name must be a non-blank str"):
        ToolNotCalledEvaluator(EvaluatorIdentity("tool-not-called", "1"), "\t\n")


def test_tool_evaluators_do_not_normalize_a_non_blank_tool_name() -> None:
    """A non-blank name with incidental surrounding whitespace is stored and
    matched exactly, never silently stripped."""
    evaluator = ToolCalledEvaluator(EvaluatorIdentity("tool-called", "1"), " tool ")
    assert evaluator.tool_name == " tool "
    assert evaluator.evaluate(frozenset({" tool "})).outcome is EvaluationOutcome.PASS
    assert evaluator.evaluate(frozenset({"tool"})).outcome is EvaluationOutcome.FAIL


def test_tool_evaluators_reject_wrong_input_type() -> None:
    evaluator = ToolCalledEvaluator(EvaluatorIdentity("tool-called", "1"), "refund")
    with pytest.raises(TypeError, match="frozenset"):
        evaluator.evaluate({"refund"})  # type: ignore[arg-type]  # plain set, not frozenset
    with pytest.raises(TypeError, match="str tool names"):
        evaluator.evaluate(frozenset({1, 2}))  # type: ignore[arg-type]


def test_tool_evaluators_unicode_tool_names() -> None:
    evaluator = ToolCalledEvaluator(
        EvaluatorIdentity("tool-called", "1"), "réservation"
    )
    assert (
        evaluator.evaluate(frozenset({"réservation"})).outcome is EvaluationOutcome.PASS
    )


def test_tool_evaluators_stable_configuration_identity() -> None:
    a = ToolCalledEvaluator(EvaluatorIdentity("tool-called", "1"), "refund")
    b = ToolCalledEvaluator(EvaluatorIdentity("tool-called", "1"), "refund")
    assert a == b


def test_tool_evaluators_deterministic_property() -> None:
    assert ToolCalledEvaluator(EvaluatorIdentity("tc", "1"), "x").deterministic is True
    assert (
        ToolNotCalledEvaluator(EvaluatorIdentity("tnc", "1"), "x").deterministic is True
    )


def test_tool_called_evaluator_never_retains_arguments_or_results() -> None:
    """Adversarial privacy check: inspect the evaluator's own state/repr.

    ToolCalledEvaluator/ToolNotCalledEvaluator are frozen ``slots`` dataclasses
    declaring only ``identity`` and ``tool_name``; evaluating a call set must
    not create any new attribute, and the repr must never contain anything
    beyond those two configuration fields.
    """
    evaluator = ToolCalledEvaluator(EvaluatorIdentity("tool-called", "1"), "refund")
    called_tools = frozenset({"refund", "lookup_account_balance_1234"})
    evaluator.evaluate(called_tools)
    assert evaluator.__slots__ == ("identity", "tool_name")
    representation = repr(evaluator)
    assert "lookup_account_balance_1234" not in representation
    assert representation == (
        "ToolCalledEvaluator(identity=EvaluatorIdentity(name='tool-called', "
        "version='1', configuration_id=None), tool_name='refund')"
    )
