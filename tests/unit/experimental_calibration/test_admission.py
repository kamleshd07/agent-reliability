# ruff: noqa: E501 -- long assertion and data lines are kept readable.
"""Calibration status: every route to 'calibrated' is narrow; every other route is named."""

from __future__ import annotations

import dataclasses
import json
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest

from agent_reliability.experimental.calibration import (
    AssessmentError,
    CalibrationAssessment,
    CalibrationStatus,
    ModelDeclaration,
    ReferenceDataset,
    Split,
    assess_admission,
    assess_drift,
    build_assessment,
)
from tests.fakes.p29_calibration import (
    CANARY,
    CREATED,
    KEY,
    NOW,
    case_doc,
    demo_policy,
    fingerprint,
    heldout_cases,
    human_policy,
    load,
    perfect_outcomes,
    table,
)

pytestmark = pytest.mark.unit

S = CalibrationStatus


def human_dataset(tmp_path: Path, **kw: Any) -> ReferenceDataset:
    return load(
        tmp_path,
        {"heldout": heldout_cases(provenance="human_multi", multi=True)},
        provenance={"heldout": "human_multi"},
        **kw,
    )


def runs(outcomes: dict[str, str], n: int = 3) -> dict[str, list[str]]:
    return {k: [v] * n for k, v in outcomes.items()}


def assessed(
    dataset: ReferenceDataset, outcomes: dict[str, Any] | None = None, **kw: Any
) -> CalibrationAssessment:
    data = outcomes if outcomes is not None else runs(perfect_outcomes(dataset))
    return build_assessment(
        dataset,
        Split.HELDOUT,
        table(data, fp=kw.pop("fp", None)),
        now=CREATED + timedelta(days=1),
        **kw,
    )


def decide(assessment, policy=None, *, now=NOW, fp=None, key=None):  # type: ignore[no-untyped-def]
    return assess_admission(
        assessment, fp or fingerprint(), policy or human_policy(), now, hmac_key=key
    )


def names(decision, verdict: str) -> set[str]:  # type: ignore[no-untyped-def]
    return {c.name for c in decision.criteria if c.verdict == verdict}


# ------------------------------------------------------------------ calibrated


def test_a_perfect_judge_on_human_labelled_held_out_data_is_calibrated(
    tmp_path: Path,
) -> None:
    decision = decide(assessed(human_dataset(tmp_path)))
    assert decision.status is S.CALIBRATED and decision.admissible
    assert decision.integrity == "unverified"
    assert not decision.failing()
    assert (
        decision.model
        == ModelDeclaration("local", "llama-3-8b-q4", "2026-09").as_dict()
    )


def test_verified_integrity_policy_requires_the_hmac(tmp_path: Path) -> None:
    a = assessed(human_dataset(tmp_path))
    policy = human_policy(require_verified_integrity=True)
    assert decide(a, policy).status is S.UNCALIBRATED  # no key at all
    assert decide(a, policy, key=KEY).status is S.UNCALIBRATED  # unsigned assessment
    signed = a.sign(KEY)
    assert decide(signed, policy, key=KEY).status is S.CALIBRATED
    assert decide(signed, policy, key=KEY).integrity == "verified"
    assert decide(signed, policy, key=b"x" * 32).status is S.UNCALIBRATED  # wrong key
    assert decide(signed, policy).status is S.UNCALIBRATED  # key not supplied


def test_the_admissible_claim_is_stated_conservatively(tmp_path: Path) -> None:
    text = decide(assessed(human_dataset(tmp_path))).explain()
    assert "not a statement about production accuracy" in text
    assert "attestation" in text
    assert "policy weaker than the starting point" in text  # the test policy is looser


# ------------------------------------------------------- not calibrated, by cause


def test_no_assessment_is_uncalibrated() -> None:
    d = decide(None)
    assert d.status is S.UNCALIBRATED and not d.admissible and d.integrity == "absent"


def test_a_measured_violation_is_uncalibrated_not_insufficient(tmp_path: Path) -> None:
    ds = human_dataset(tmp_path)
    outcomes = {
        k: ("PASS" if k.startswith(("f", "a")) else v)
        for k, v in perfect_outcomes(ds).items()
    }
    d = decide(assessed(ds, runs(outcomes)))
    assert d.status is S.UNCALIBRATED
    assert "fnr_effective" in names(d, "violated")


def test_not_provably_good_is_insufficient_evidence_not_failing(tmp_path: Path) -> None:
    ds = human_dataset(tmp_path)
    outcomes = perfect_outcomes(ds)
    flipped = [k for k in outcomes if k.startswith("f")][:6]  # 6 of 12 defects passed
    for k in flipped:
        outcomes[k] = "PASS"
    d = decide(assessed(ds, runs(outcomes)))
    assert d.status is S.INSUFFICIENT_REFERENCE_EVIDENCE
    assert "fnr_effective" in names(d, "inconclusive")
    assert not names(d, "violated")  # nothing is *measured* to be out of bounds


def test_an_undefined_rate_is_inconclusive(tmp_path: Path) -> None:
    ds = human_dataset(tmp_path)
    outcomes = perfect_outcomes(ds)
    for k in list(outcomes):
        if k.startswith("p"):
            outcomes[k] = (
                "UNKNOWN"  # never commits on a good run: fpr_conditional undefined
            )
    d = decide(assessed(ds, runs(outcomes)))
    assert "fpr_conditional" in names(d, "inconclusive")
    assert d.status is S.INSUFFICIENT_REFERENCE_EVIDENCE


def test_synthetic_labels_never_calibrate_under_a_human_policy(tmp_path: Path) -> None:
    ds = load(tmp_path, {"heldout": heldout_cases()})
    d = decide(assessed(ds, runs(perfect_outcomes(ds))))
    assert d.status is S.INSUFFICIENT_REFERENCE_EVIDENCE
    assert names(d, "violated") == {"label_provenance_accepted"}


def test_a_demonstration_policy_can_only_demonstrate(tmp_path: Path) -> None:
    synthetic = load(tmp_path / "s", {"heldout": heldout_cases()})
    a = assessed(synthetic, runs(perfect_outcomes(synthetic)))
    d = decide(a, demo_policy())
    assert d.status is S.DEMONSTRATION and not d.admissible
    human = human_dataset(tmp_path / "h")
    d2 = decide(
        assessed(human),
        demo_policy(
            accepted_label_provenance=frozenset(
                {
                    *demo_policy().accepted_label_provenance,
                    *human_policy().accepted_label_provenance,
                }
            )
        ),
    )
    assert d2.status is S.DEMONSTRATION  # even on human data


def test_too_few_examples_or_a_thin_class_is_insufficient(tmp_path: Path) -> None:
    ds = human_dataset(tmp_path)
    a = assessed(ds, runs(perfect_outcomes(ds)))
    d = decide(a, human_policy(min_examples=24, min_per_class=12))  # exactly enough
    assert d.status is S.CALIBRATED
    d = decide(a, human_policy(min_examples=25, min_per_class=8))
    assert (
        d.status is S.INSUFFICIENT_REFERENCE_EVIDENCE
        and "labelled_examples" in names(d, "violated")
    )
    d = decide(a, human_policy(min_examples=20, min_per_class=13))
    assert "support_fail" in names(d, "violated")


def test_no_repeat_runs_means_insufficient_repeatability_evidence(
    tmp_path: Path,
) -> None:
    ds = human_dataset(tmp_path)
    d = decide(assessed(ds, perfect_outcomes(ds)))  # one run each
    assert d.status is S.INSUFFICIENT_REFERENCE_EVIDENCE
    assert "repeat_cases" in names(d, "violated")


def test_indeterminate_heavy_data_is_insufficient(tmp_path: Path) -> None:
    docs = heldout_cases(provenance="human_multi", multi=True)
    docs += [
        case_doc(f"u{i}", "unknown", provenance="human_multi",
                 labels=[("rev-a", "unknown"), ("rev-b", "unknown")])
        for i in range(60)
    ]  # fmt: skip
    ds = load(tmp_path, {"heldout": docs}, provenance={"heldout": "human_multi"})
    d = decide(assessed(ds, runs(perfect_outcomes(ds))))
    assert d.status is S.INSUFFICIENT_REFERENCE_EVIDENCE
    assert "indeterminate_fraction" in names(d, "violated")


def test_inter_labeler_agreement_below_the_floor_is_insufficient(
    tmp_path: Path,
) -> None:
    docs = heldout_cases(provenance="human_adjudicated", multi=True)
    for doc in docs[:10]:  # labelers disagreed, adjudicated to the stated label
        doc["labels"] = [{"labeler": "rev-a", "label": doc["human_label"]},
                         {"labeler": "rev-b", "label": "pass" if doc["human_label"] == "fail" else "fail"}]  # fmt: skip
        doc["adjudication"] = {"method": "third_reviewer"}
    for doc in docs[10:]:
        doc["adjudication"] = {"method": "majority"}
    ds = load(tmp_path, {"heldout": docs}, provenance={"heldout": "human_adjudicated"})
    a = assessed(ds, runs(perfect_outcomes(ds)))
    assert (
        decide(a, human_policy(min_inter_labeler_agreement=0.5)).status is S.CALIBRATED
    )
    d = decide(a, human_policy(min_inter_labeler_agreement=0.95))
    assert (
        d.status is S.INSUFFICIENT_REFERENCE_EVIDENCE
        and "inter_labeler_agreement" in names(d, "violated")
    )


def test_split_leakage_makes_the_dataset_insufficient(tmp_path: Path) -> None:
    held = heldout_cases(provenance="human_multi", multi=True)
    train = [dict(held[0], case_id="t0")]  # exact content duplicate of a held-out case
    ds = load(
        tmp_path,
        {"heldout": held, "train": train},
        provenance={"heldout": "human_multi", "train": "human_multi"},
    )
    d = decide(assessed(ds, runs(perfect_outcomes(ds))))
    assert (
        d.status is S.INSUFFICIENT_REFERENCE_EVIDENCE
        and "no_split_leakage" in names(d, "violated")
    )


def test_adversarial_defect_passes_are_a_count_criterion(tmp_path: Path) -> None:
    ds = human_dataset(tmp_path)
    outcomes = perfect_outcomes(ds)
    for k in [k for k in outcomes if k.startswith("a")][:2]:
        outcomes[k] = "PASS"
    a = assessed(ds, runs(outcomes))
    assert (
        decide(a, human_policy(max_adversarial_pass_on_fail=2)).status is S.CALIBRATED
    )
    d = decide(a, human_policy(max_adversarial_pass_on_fail=1))
    assert d.status is S.UNCALIBRATED and "adversarial_defects_passed" in names(
        d, "violated"
    )


# ---------------------------------------------------------------------- time


def test_expiry_and_stale_datasets(tmp_path: Path) -> None:
    a = assessed(human_dataset(tmp_path))
    created = a.created_at
    assert decide(a, now=created + timedelta(days=90)).status is S.CALIBRATED
    expired = decide(a, now=created + timedelta(days=91))
    assert expired.status is S.CALIBRATION_EXPIRED and not expired.admissible
    stale = decide(
        a, human_policy(max_dataset_age_days=10), now=created + timedelta(days=30)
    )
    assert stale.status is S.CALIBRATION_EXPIRED and "dataset_current" in names(
        stale, "violated"
    )


def test_a_future_dated_assessment_never_calibrates(tmp_path: Path) -> None:
    a = assessed(human_dataset(tmp_path))
    d = decide(a, now=a.created_at - timedelta(days=2))
    assert d.status is S.UNCALIBRATED and "not_future_dated" in names(d, "violated")
    assert (
        decide(a, now=a.created_at - timedelta(seconds=30)).status is S.CALIBRATED
    )  # skew


# ------------------------------------------------------------ compatibility


def test_a_different_model_declaration_or_behaviour_is_incompatible(
    tmp_path: Path,
) -> None:
    a = assessed(human_dataset(tmp_path))
    other_version = fingerprint(
        model=ModelDeclaration("local", "llama-3-8b-q4", "2026-10")
    )
    d = decide(a, fp=other_version)
    assert d.status is S.INCOMPATIBLE and "fingerprint_equivalent" in names(
        d, "violated"
    )
    other_label = fingerprint("local-b")  # configuration_id differs
    assert decide(a, fp=other_label).status is S.INCOMPATIBLE


def test_an_sdk_patch_release_does_not_force_recalibration(tmp_path: Path) -> None:
    a = assessed(human_dataset(tmp_path))
    patched = dataclasses.replace(fingerprint(), implementation_version="9.9.9")
    assert decide(a, fp=patched).status is S.CALIBRATED
    assert "implementation_version" in a.fingerprint.diff(patched)


def test_a_template_or_limits_change_is_incompatible(tmp_path: Path) -> None:
    a = assessed(human_dataset(tmp_path))
    for field in (
        "template_digest",
        "limits_digest",
        "rubric_fingerprint",
        "min_confidence",
    ):
        changed = dataclasses.replace(
            fingerprint(),
            **{
                field: "0" * 64
                if "digest" in field or "fingerprint" in field
                else "high"
            },
        )
        assert decide(a, fp=changed).status is S.INCOMPATIBLE, field


def test_a_dataset_built_for_another_rubric_version_is_incompatible(
    tmp_path: Path,
) -> None:
    ds = human_dataset(tmp_path)
    ds = dataclasses.replace(ds, rubric_version="2099-01.r9")
    d = decide(assessed(ds, runs(perfect_outcomes(ds))))
    assert d.status is S.INCOMPATIBLE and "rubric_matches_dataset" in names(
        d, "violated"
    )


# ----------------------------------------------------------------- integrity


def test_a_tampered_assessment_is_uncalibrated(tmp_path: Path) -> None:
    a = assessed(human_dataset(tmp_path))
    document = a.document
    document["metrics"]["headline"]["counts"]["fn"] = 0
    document["metrics"]["headline"]["counts"]["tp"] += 1
    tampered = CalibrationAssessment(document)  # digest no longer matches
    assert not tampered.digest_matches
    d = decide(tampered)
    assert d.status is S.UNCALIBRATED and d.integrity == "mismatch"


def test_a_forged_digest_without_the_key_fails_a_verified_policy(
    tmp_path: Path,
) -> None:
    a = assessed(human_dataset(tmp_path)).sign(KEY)
    document = a.document
    document["metrics"]["headline"]["counts"]["fn"] += 1
    forged = CalibrationAssessment(document)
    assert not forged.verify(KEY)
    assert (
        decide(forged, human_policy(require_verified_integrity=True), key=KEY).status
        is S.UNCALIBRATED
    )


def test_only_the_held_out_split_may_be_assessed(tmp_path: Path) -> None:
    ds = load(tmp_path, {"heldout": heldout_cases(), "calibration": [case_doc("c1")]})
    for split in (Split.CALIBRATION, Split.TRAIN):
        with pytest.raises(AssessmentError, match="held-out"):
            build_assessment(ds, split, table({"c1": "PASS"}), now=NOW)


def test_a_table_naming_foreign_examples_is_refused(tmp_path: Path) -> None:
    ds = load(tmp_path, {"heldout": heldout_cases()})
    with pytest.raises(AssessmentError, match="outside"):
        build_assessment(ds, Split.HELDOUT, table({"nope": "PASS"}), now=NOW)


# ------------------------------------------------- determinism & serialisation


def test_assessment_and_decision_are_deterministic_and_round_trip(
    tmp_path: Path,
) -> None:
    ds = human_dataset(tmp_path)
    a1, a2 = assessed(ds), assessed(ds)
    assert a1 == a2 and a1.digest == a2.digest and a1.to_json() == a2.to_json()
    again = CalibrationAssessment.from_json(a1.to_json())
    assert again == a1 and again.digest_matches
    d1, d2 = decide(a1), decide(again)
    assert d1.as_dict() == d2.as_dict()
    assert json.dumps(d1.as_dict())  # JSON-able


def test_signing_requires_a_real_key_and_hmac_survives_serialisation(
    tmp_path: Path,
) -> None:
    a = assessed(human_dataset(tmp_path))
    with pytest.raises(AssessmentError):
        a.sign(b"short")
    signed = CalibrationAssessment.from_json(a.sign(KEY).to_json())
    assert signed.verify(KEY) and not signed.verify(b"y" * 32) and not a.verify(KEY)


def test_hostile_assessment_json_is_rejected() -> None:
    for text in ('{"schema": "x"}', "[]", '{"a":1,"a":2}', "not json", "{" * 500):
        with pytest.raises(AssessmentError):
            CalibrationAssessment.from_json(text)


def test_heldout_attempt_is_recorded_and_validated(tmp_path: Path) -> None:
    ds = human_dataset(tmp_path)
    a = assessed(ds, heldout_attempt=3)
    assert a.document["heldout_attempt"] == 3
    with pytest.raises(AssessmentError):
        assessed(ds, heldout_attempt=0)


# --------------------------------------------------------------------- drift


def test_drift_indicators_are_advisory_and_deterministic(tmp_path: Path) -> None:
    a = assessed(human_dataset(tmp_path))
    policy = human_policy()
    clear = assess_drift(a, fingerprint(), policy, a.created_at + timedelta(days=1))
    assert [
        clear[k]["state"]
        for k in ("fingerprint_changed", "calibration_expired", "dataset_stale")
    ] == ["clear"] * 3
    drifted = assess_drift(
        a,
        fingerprint("local-b"),
        policy,
        a.created_at + timedelta(days=400),
    )
    assert drifted["fingerprint_changed"]["state"] == "indicated"
    assert "configuration_id" in drifted["fingerprint_changed"]["differing_components"]
    assert drifted["calibration_expired"]["state"] == "indicated"
    assert drifted["dataset_stale"]["state"] == "indicated"
    assert drifted["advisory"] is True
    assert "decision_mix_shift" in drifted["deferred"]


# ------------------------------------------------------------------- privacy


def test_no_artefact_contains_case_content(tmp_path: Path) -> None:
    ds = human_dataset(tmp_path)
    a = assessed(ds)
    d = decide(a)
    blobs = [
        a.to_json(), repr(a), json.dumps(d.as_dict()), d.explain(), repr(d),
        repr(ds), json.dumps(ds.leakage.as_dict()), repr(fingerprint()),
        json.dumps(a.document["fingerprint"]),
    ]  # fmt: skip
    for blob in blobs:
        assert CANARY not in blob
