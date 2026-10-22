# ruff: noqa: E501 -- long assertion and data lines are kept readable.
"""Boundary operators and individual criteria, pinned so that each can be mutated and caught."""

from __future__ import annotations

import dataclasses
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from agent_reliability.experimental.calibration import (
    AssessmentError,
    CalibrationAssessment,
    DatasetError,
    JudgeFingerprint,
    LabelProvenance,
    PolicyError,
    Split,
    assess_admission,
    build_assessment,
    load_reference_dataset,
)
from agent_reliability.experimental.calibration import (
    CalibrationStatus as S,
)
from agent_reliability.experimental.calibration._json import strict_loads
from agent_reliability.experimental.calibration.admission import (
    INCONCLUSIVE,
    MET,
    VIOLATED,
    _lower,
    _upper,
)
from agent_reliability.experimental.calibration.assessment import _body_bytes
from tests.fakes.p29_calibration import (
    KEY,
    NOW,
    case_doc,
    fingerprint,
    heldout_cases,
    human_policy,
    load,
    perfect_outcomes,
    table,
    train_cases,
    write_dataset,
)

pytestmark = pytest.mark.unit


@dataclass
class FakeProportion:
    exact: tuple[float, float] | None
    numerator: int = 1
    denominator: int = 10


# ---------------------------------------------------------- the three-way operators


@pytest.mark.parametrize(
    ("interval", "limit", "verdict"),
    [
        ((0.0, 0.05), 0.05, MET),  # upper bound exactly at the limit is within it
        ((0.0, 0.0500001), 0.05, INCONCLUSIVE),
        (
            (0.05, 0.2),
            0.05,
            INCONCLUSIVE,
        ),  # lower bound exactly at the limit is not above it
        ((0.0500001, 0.2), 0.05, VIOLATED),
        (None, 0.05, INCONCLUSIVE),
    ],
)
def test_upper_bound_criterion_operators(interval, limit, verdict) -> None:  # type: ignore[no-untyped-def]
    assert _upper("x", FakeProportion(interval), limit).verdict == verdict  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("interval", "minimum", "verdict"),
    [
        ((0.8, 0.95), 0.8, MET),  # lower bound exactly at the minimum meets it
        ((0.7999999, 0.95), 0.8, INCONCLUSIVE),
        (
            (0.5, 0.8),
            0.8,
            INCONCLUSIVE,
        ),  # upper bound exactly at the minimum is not below it
        ((0.5, 0.7999999), 0.8, VIOLATED),
        (None, 0.8, INCONCLUSIVE),
    ],
)
def test_lower_bound_criterion_operators(interval, minimum, verdict) -> None:  # type: ignore[no-untyped-def]
    assert _lower("x", FakeProportion(interval), minimum).verdict == verdict  # type: ignore[arg-type]


# ----------------------------------------------------- helpers shared with test_admission


def human_dataset(tmp_path: Path, **kw: Any):  # type: ignore[no-untyped-def]
    return load(
        tmp_path,
        {
            "heldout": heldout_cases(provenance="human_multi", multi=True),
            "train": train_cases(),
        },
        provenance={"heldout": "human_multi", "train": "human_multi"},
        **kw,
    )


def runs(outcomes: dict[str, str], n: int = 3) -> dict[str, list[str]]:
    return {k: [v] * n for k, v in outcomes.items()}


def assess(ds, outcomes=None, *, sign=True, fp=None):  # type: ignore[no-untyped-def]
    from datetime import timedelta

    from tests.fakes.p29_calibration import CREATED

    data = outcomes if outcomes is not None else runs(perfect_outcomes(ds))
    a = build_assessment(
        ds, Split.HELDOUT, table(data, fp=fp), now=CREATED + timedelta(days=1)
    )
    return a.sign(KEY) if sign else a


def decide(a, policy=None, fp=None):  # type: ignore[no-untyped-def]
    return assess_admission(
        a, fp or fingerprint(), policy or human_policy(), NOW, hmac_key=KEY
    )


def verdicts(d, verdict):  # type: ignore[no-untyped-def]
    return {c.name for c in d.criteria if c.verdict == verdict}


# ------------------------------------------------------------ individual criteria


def test_low_committed_coverage_is_uncalibrated_when_provably_low(
    tmp_path: Path,
) -> None:
    ds = human_dataset(tmp_path)
    outcomes = perfect_outcomes(ds)
    for key in list(outcomes)[:20]:
        outcomes[key] = "UNKNOWN"  # abstains on most of the headline set
    d = decide(assess(ds, runs(outcomes)), human_policy(max_abstention_rate=0.9))
    assert "committed_coverage" in verdicts(d, VIOLATED) and d.status is S.UNCALIBRATED


def test_a_forged_non_heldout_split_never_calibrates_even_when_signed(
    tmp_path: Path,
) -> None:
    ds = human_dataset(tmp_path)
    document = assess(ds, sign=False).document
    document["dataset"]["split"] = "train"
    document["integrity"] = {
        "sha256": hashlib.sha256(_body_bytes(document)).hexdigest()
    }
    forged = CalibrationAssessment(document).sign(
        KEY
    )  # a key holder can sign anything...
    d = decide(forged)
    assert d.status is S.UNCALIBRATED and "heldout_split" in verdicts(
        d, VIOLATED
    )  # ...but the rule stays


def test_the_false_negative_basis_chosen_by_the_policy_is_the_one_checked(
    tmp_path: Path,
) -> None:
    ds = human_dataset(tmp_path)
    outcomes = perfect_outcomes(ds)
    defects = [k for k in outcomes if k.startswith("f")]
    for key in defects[:6]:
        outcomes[key] = "UNKNOWN"  # half the defects are not flagged, none passed
    a = assess(ds, runs(outcomes))
    effective = decide(a, human_policy(fn_basis="effective"))
    conditional = decide(a, human_policy(fn_basis="conditional"))
    assert "fnr_effective" in verdicts(effective, INCONCLUSIVE)
    assert "fnr_conditional" not in {c.name for c in effective.criteria}
    assert "fnr_conditional" in verdicts(conditional, MET)
    assert "fnr_effective" not in {c.name for c in conditional.criteria}


def test_the_false_positive_basis_chosen_by_the_policy_is_the_one_checked(
    tmp_path: Path,
) -> None:
    a = assess(human_dataset(tmp_path))
    for basis in ("conditional", "effective"):
        d = decide(a, human_policy(fp_basis=basis))
        assert f"fpr_{basis}" in {c.name for c in d.criteria}


def test_every_size_criterion_stands_alone(tmp_path: Path) -> None:
    a = assess(human_dataset(tmp_path))
    d = decide(a, human_policy(min_per_class=13, min_examples=20))
    assert {"support_fail", "support_pass"} <= verdicts(d, VIOLATED)
    d = decide(a, human_policy(min_adversarial_fail=5))
    assert "adversarial_fail_support" in verdicts(d, VIOLATED)
    d = decide(a, human_policy(min_repeat_cases=30))
    assert "repeat_cases" in verdicts(d, VIOLATED)


def test_the_worst_case_instability_counts_cases_that_lost_their_comparison(
    tmp_path: Path,
) -> None:
    ds = human_dataset(tmp_path)
    outcomes: dict[str, Any] = runs(perfect_outcomes(ds))
    for key in list(outcomes)[:22]:  # a stable first run, then two failed runs
        outcomes[key] = [outcomes[key][0], "FAILURE", "FAILURE"]
    d = decide(
        assess(ds, outcomes), human_policy(max_unstable_rate=0.4, min_repeat_cases=12)
    )
    assert "unstable_rate_worst_case" in verdicts(d, VIOLATED)


def test_an_unmeasurable_labeler_agreement_is_inconclusive_not_met(
    tmp_path: Path,
) -> None:
    docs = heldout_cases(provenance="human_single")
    for doc in docs:
        doc["labels"] = [
            {"labeler": "rev-a", "label": doc["human_label"]}
        ]  # one labeler each
    ds = load(
        tmp_path,
        {"heldout": docs, "train": train_cases(provenance="human_single")},
        provenance={"heldout": "human_single", "train": "human_single"},
    )
    policy = human_policy(
        accepted_label_provenance=frozenset({LabelProvenance.HUMAN_SINGLE}),
        min_inter_labeler_agreement=0.5,
    )
    d = decide(assess(ds), policy)
    assert "inter_labeler_agreement" in verdicts(d, INCONCLUSIVE)
    assert d.status is S.INSUFFICIENT_REFERENCE_EVIDENCE


def test_the_rubric_id_is_compared_not_only_its_version(tmp_path: Path) -> None:
    ds = dataclasses.replace(human_dataset(tmp_path), rubric_id="some-other-rubric")
    d = decide(assess(ds))
    assert d.status is S.INCOMPATIBLE and "rubric_matches_dataset" in verdicts(
        d, VIOLATED
    )


def test_a_held_out_only_dataset_cannot_show_the_absence_of_leakage(
    tmp_path: Path,
) -> None:
    ds = load(
        tmp_path,
        {"heldout": heldout_cases(provenance="human_multi", multi=True)},
        provenance={"heldout": "human_multi"},
    )
    d = decide(assess(ds))
    assert d.status is S.INSUFFICIENT_REFERENCE_EVIDENCE
    assert "leakage_checked_against_other_splits" in verdicts(d, INCONCLUSIVE)


# ------------------------------------------------------------------- loader guards


def test_fullwidth_and_compatibility_forms_are_folded_when_looking_for_leakage(
    tmp_path: Path,
) -> None:
    ds = load(
        tmp_path,
        {
            "train": [case_doc("t1", text="REFUND policy is thirty days")],
            "heldout": [
                case_doc(
                    "h1",
                    text="\uff32\uff25\uff26\uff35\uff2e\uff24 policy is thirty days",
                )
            ],
        },
    )
    assert ds.leakage.cross_split


def test_reordered_parts_do_not_evade_leakage_detection(tmp_path: Path) -> None:
    a = case_doc("t1", text="same words")
    b = case_doc("h1", text="same words")
    b["parts"] = list(reversed(b["parts"]))
    ds = load(tmp_path, {"train": [a], "heldout": [b]})
    assert ds.leakage.identical_normalized


def test_duplicate_case_ids_inside_one_split_are_refused(tmp_path: Path) -> None:
    path, digest = write_dataset(
        tmp_path, {"heldout": [case_doc("a"), case_doc("a", text="other")]}
    )
    with pytest.raises(DatasetError, match="unique"):
        load_reference_dataset(path, expected_manifest_sha256=digest)


def test_split_file_names_with_nul_or_dots_are_refused(tmp_path: Path) -> None:
    path, _ = write_dataset(tmp_path, {"heldout": heldout_cases()})
    for name in ("a\x00b.jsonl", ".", ".."):
        manifest = json.loads(path.read_text())
        manifest["splits"]["heldout"]["file"] = name
        raw = json.dumps(manifest, sort_keys=True).encode()
        path.write_bytes(raw)
        with pytest.raises(DatasetError):
            load_reference_dataset(
                path, expected_manifest_sha256=hashlib.sha256(raw).hexdigest()
            )


def test_strict_json_rejects_duplicates_depth_overflow_and_absurd_numbers() -> None:
    strict_loads("[" * 8 + "]" * 8)  # exactly the limit
    for hostile in (
        '{"a":1,"a":2}',
        "[" * 9 + "]" * 9,
        "1e999",
        "-1e999",
        "NaN",
        "Infinity",
        "1" * 40,
        '{"a":' + "9" * 30 + "}",
    ):
        with pytest.raises(ValueError):
            strict_loads(hostile)
    assert strict_loads('{"a": 123456789012345678}') == {"a": 123456789012345678}


def test_hostile_numbers_in_assessments_and_policies_raise_the_documented_errors(
    tmp_path: Path,
) -> None:
    text = assess(human_dataset(tmp_path)).to_json()
    for hostile in ("1e999", "9" * 40):
        with pytest.raises(AssessmentError):
            CalibrationAssessment.from_json(
                text.replace('"heldout_attempt": 1', f'"heldout_attempt": {hostile}')
            )
    for overrides in (
        {"min_examples": 10**30},
        {"max_fnr": 10**400},
        {"validity_days": 10**12},
    ):
        with pytest.raises(PolicyError):
            human_policy(**overrides)


def test_a_fingerprint_whose_digest_does_not_match_its_components_is_refused() -> None:
    document = fingerprint().as_dict()
    document["limits_digest"] = "0" * 64  # components changed, digest not recomputed
    with pytest.raises(ValueError, match="digest"):
        JudgeFingerprint.from_dict(document)


def test_an_empty_other_split_checks_nothing(tmp_path: Path) -> None:
    # An empty split cannot be written through the helper, so replace it in memory.
    base = human_dataset(tmp_path)
    emptied = dataclasses.replace(base, splits={**base.splits, Split.TRAIN: ()})
    a = assess(emptied)
    assert a.document["dataset"]["leakage_checked_against"] == []
    d = decide(a)
    assert d.status is S.INSUFFICIENT_REFERENCE_EVIDENCE
    assert "leakage_checked_against_other_splits" in verdicts(d, INCONCLUSIVE)


def test_day_windows_beyond_timedelta_are_refused_by_the_policy() -> None:
    for name in ("validity_days", "max_dataset_age_days"):
        with pytest.raises(PolicyError):
            human_policy(**{name: 10**9})
