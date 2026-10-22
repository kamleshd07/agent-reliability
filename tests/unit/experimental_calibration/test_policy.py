# ruff: noqa: E501 -- long assertion and data lines are kept readable.
"""The policy is the caller's: explicit, coherent, and tied to provenance rules."""

from __future__ import annotations

import dataclasses

import pytest

from agent_reliability.experimental.calibration import (
    CalibrationPolicy,
    LabelProvenance,
    PolicyError,
)
from tests.fakes.p29_calibration import demo_policy, human_policy

pytestmark = pytest.mark.unit


def test_there_is_no_implicit_threshold() -> None:
    with pytest.raises(TypeError):
        CalibrationPolicy()  # type: ignore[call-arg]
    assert all(
        f.default is dataclasses.MISSING and f.default_factory is dataclasses.MISSING
        for f in dataclasses.fields(CalibrationPolicy)
    )


def test_the_starting_point_is_valid_coherent_and_not_below_itself() -> None:
    policy = CalibrationPolicy.starting_point()
    assert policy.below_starting_point() == ()
    assert not policy.demonstration_only
    assert policy.accepted_label_provenance == frozenset(
        {LabelProvenance.HUMAN_MULTI, LabelProvenance.HUMAN_ADJUDICATED}
    )
    assert policy.digest == CalibrationPolicy.starting_point().digest


def test_a_looser_policy_is_flagged_but_not_blocked() -> None:
    loose = human_policy()
    weaker = loose.below_starting_point()
    for name in ("min_examples", "max_fnr", "validity_days"):
        assert name in weaker or getattr(loose, name) == getattr(
            CalibrationPolicy.starting_point(), name
        )
    assert "min_examples" in weaker and "max_fnr" in weaker
    assert loose.summary()["below_starting_point"] == list(weaker)


@pytest.mark.parametrize(
    "overrides",
    [
        {"min_per_class": 10, "max_fnr": 0.05},  # 10 zero-error cases cannot show <= 5%
        {"min_examples": 30, "max_failure_rate": 0.02},
        {"min_repeat_cases": 20, "max_unstable_rate": 0.05},
        {"min_examples": 400, "min_per_class": 500},
        {"min_examples": 5, "min_committed_coverage": 0.95},
    ],
)
def test_size_minima_that_cannot_meet_their_own_bound_are_rejected(
    overrides: dict[str, object],
) -> None:
    with pytest.raises(PolicyError):
        human_policy(**overrides)


@pytest.mark.parametrize(
    "overrides",
    [
        {"min_examples": 0},
        {"min_examples": True},
        {"max_fnr": 0.0},
        {"max_fnr": 1.5},
        {"max_fnr": float("nan")},
        {"min_committed_coverage": 1.0},
        {"fn_basis": "weighted"},
        {"fp_basis": ""},
        {"accepted_label_provenance": frozenset()},
        {"accepted_label_provenance": {LabelProvenance.HUMAN_MULTI}},  # not a frozenset
        {"require_verified_integrity": "yes"},
        {"max_adversarial_pass_on_fail": -1},
        {"min_inter_labeler_agreement": 0},
    ],
)
def test_invalid_values_are_rejected(overrides: dict[str, object]) -> None:
    with pytest.raises(PolicyError):
        human_policy(**overrides)


def test_synthetic_provenance_is_accepted_only_by_demonstration_policies() -> None:
    with pytest.raises(PolicyError, match="demonstration_only"):
        human_policy(
            accepted_label_provenance=frozenset(
                {LabelProvenance.SYNTHETIC, LabelProvenance.HUMAN_MULTI}
            )
        )
    assert demo_policy().demonstration_only


def test_a_demonstration_policy_may_not_be_turned_into_a_calibrating_one_by_provenance() -> (
    None
):
    with pytest.raises(PolicyError, match="demonstration_only"):
        demo_policy(
            demonstration_only=False,
            accepted_label_provenance=frozenset({LabelProvenance.SYNTHETIC}),
        )


def test_a_policy_is_immutable_and_its_digest_follows_its_content() -> None:
    policy = human_policy()
    with pytest.raises(dataclasses.FrozenInstanceError):
        policy.max_fnr = 0.9  # type: ignore[misc]
    assert policy.digest != human_policy(max_fnr=0.4).digest
    assert policy.as_dict()["accepted_label_provenance"] == [
        "human_adjudicated",
        "human_multi",
    ]
