"""Property-based tests for the ratio SLI kernel (agent_reliability.domain.sli).

Invariants tested here are drawn from docs/TESTING_STRATEGY.md and the
M1 requirements: ratio bounds, count conservation, UNKNOWN-policy
behavior, monotonicity, determinism, and permutation-invariance.
"""

from __future__ import annotations

from fractions import Fraction

from hypothesis import given
from hypothesis import strategies as st

from agent_reliability.domain import (
    EvaluationOutcome,
    RatioResult,
    UnknownPolicy,
    compute_ratio,
)

small_counts = st.integers(min_value=0, max_value=200)
any_policy = st.sampled_from(list(UnknownPolicy))
outcomes = st.sampled_from(list(EvaluationOutcome))


@given(
    pass_count=small_counts,
    fail_count=small_counts,
    unknown_count=small_counts,
    policy=any_policy,
)
def test_pass_ratio_is_within_unit_interval_when_defined(
    pass_count: int, fail_count: int, unknown_count: int, policy: UnknownPolicy
) -> None:
    ratio = RatioResult(
        pass_count=pass_count,
        fail_count=fail_count,
        unknown_count=unknown_count,
        unknown_policy=policy,
    )
    if ratio.pass_ratio is not None:
        assert Fraction(0) <= ratio.pass_ratio <= Fraction(1)
        assert Fraction(0) <= ratio.fail_ratio <= Fraction(1)  # type: ignore[operator]


@given(
    pass_count=small_counts,
    fail_count=small_counts,
    unknown_count=small_counts,
    policy=any_policy,
)
def test_pass_and_fail_ratio_sum_to_one_when_defined(
    pass_count: int, fail_count: int, unknown_count: int, policy: UnknownPolicy
) -> None:
    ratio = RatioResult(
        pass_count=pass_count,
        fail_count=fail_count,
        unknown_count=unknown_count,
        unknown_policy=policy,
    )
    if ratio.pass_ratio is not None:
        assert ratio.pass_ratio + ratio.fail_ratio == Fraction(1)  # type: ignore[operator]


@given(outcome_list=st.lists(outcomes, max_size=100), policy=any_policy)
def test_outcome_counts_are_conserved(
    outcome_list: list[EvaluationOutcome], policy: UnknownPolicy
) -> None:
    result = compute_ratio(outcome_list, unknown_policy=policy)
    assert result.pass_count + result.fail_count + result.unknown_count == len(
        outcome_list
    )


@given(pass_count=small_counts, fail_count=small_counts, unknown_count=small_counts)
def test_exclude_policy_never_moves_unknowns_into_considered_counts(
    pass_count: int, fail_count: int, unknown_count: int
) -> None:
    ratio = RatioResult(
        pass_count=pass_count,
        fail_count=fail_count,
        unknown_count=unknown_count,
        unknown_policy=UnknownPolicy.EXCLUDE,
    )
    assert ratio.considered_pass_count == pass_count
    assert ratio.considered_fail_count == fail_count
    assert ratio.considered_count == pass_count + fail_count


@given(outcome_list=st.lists(outcomes, min_size=1, max_size=50), policy=any_policy)
def test_permuting_observations_does_not_change_the_aggregate_result(
    outcome_list: list[EvaluationOutcome], policy: UnknownPolicy
) -> None:
    reversed_list = list(reversed(outcome_list))
    assert compute_ratio(outcome_list, unknown_policy=policy) == compute_ratio(
        reversed_list, unknown_policy=policy
    )


@given(outcome_list=st.lists(outcomes, max_size=50), policy=any_policy)
def test_identical_input_produces_identical_output(
    outcome_list: list[EvaluationOutcome], policy: UnknownPolicy
) -> None:
    first = compute_ratio(list(outcome_list), unknown_policy=policy)
    second = compute_ratio(list(outcome_list), unknown_policy=policy)
    assert first == second


@given(
    pass_count=st.integers(min_value=0, max_value=200),
    fail_count=st.integers(min_value=1, max_value=200),
)
def test_adding_a_pass_observation_cannot_decrease_the_pass_ratio(
    pass_count: int, fail_count: int
) -> None:
    before = RatioResult(
        pass_count=pass_count,
        fail_count=fail_count,
        unknown_count=0,
        unknown_policy=UnknownPolicy.EXCLUDE,
    )
    after = RatioResult(
        pass_count=pass_count + 1,
        fail_count=fail_count,
        unknown_count=0,
        unknown_policy=UnknownPolicy.EXCLUDE,
    )
    assert before.pass_ratio is not None
    assert after.pass_ratio is not None
    assert after.pass_ratio >= before.pass_ratio


@given(
    pass_count=st.integers(min_value=1, max_value=200),
    fail_count=st.integers(min_value=0, max_value=200),
)
def test_adding_a_fail_observation_cannot_increase_the_pass_ratio(
    pass_count: int, fail_count: int
) -> None:
    before = RatioResult(
        pass_count=pass_count,
        fail_count=fail_count,
        unknown_count=0,
        unknown_policy=UnknownPolicy.EXCLUDE,
    )
    after = RatioResult(
        pass_count=pass_count,
        fail_count=fail_count + 1,
        unknown_count=0,
        unknown_policy=UnknownPolicy.EXCLUDE,
    )
    assert before.pass_ratio is not None
    assert after.pass_ratio is not None
    assert after.pass_ratio <= before.pass_ratio
