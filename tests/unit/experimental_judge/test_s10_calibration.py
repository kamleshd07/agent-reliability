"""P29-S10: local calibration harness (content-free reports, hand-computed metrics)."""

from __future__ import annotations

import ast
import asyncio
import copy
import dataclasses
import json
import pathlib
import re
import socket
from datetime import UTC, datetime
from fractions import Fraction
from typing import Any

import pytest

import agent_reliability.experimental.judge as namespace
from agent_reliability.experimental.judge import (
    CalibrationCase,
    CalibrationReport,
    CallableProvider,
    CallableSyncProvider,
    JudgeLimits,
    JudgePolicy,
    JudgeProviderUnavailableError,
    LLMJudge,
    ProviderReply,
    SyncLLMJudge,
    compare_reports,
    load_cases,
    run_calibration,
    run_calibration_async,
)
from agent_reliability.experimental.judge._jsonschema import SchemaViolation, validate
from agent_reliability.experimental.judge.calibration import (
    MATRIX_CELLS,
    load_schema,
    wilson_interval,
)
from agent_reliability.experimental.judge.testing import judge_reply
from tests.fakes.p29_judge import SECRET, load_fixture, named_rubrics

pytestmark = pytest.mark.unit

FIXTURE = load_fixture("calibration_known_confusion.json")
AC = named_rubrics()["ac"]
NOW = datetime(2026, 10, 16, 12, 0, tzinfo=UTC)
REPLIES = {
    "PASS": judge_reply("pass", "consistent_with_reference", "high"),
    "FAIL": judge_reply("fail", "contradicts_reference", "high"),
    "UNKNOWN": judge_reply("unknown", "reference_insufficient", "high"),
}


def by_case(script: dict[str, str], seen: list[str] | None = None) -> Any:
    def complete(call: Any) -> ProviderReply:
        case_id = re.search(r"\[([a-z]\d\d)\]", call.user).group(1)  # type: ignore[union-attr]
        if seen is not None:
            seen.append(case_id)
        decision = script[case_id]
        if decision == "FAILURE":
            raise JudgeProviderUnavailableError
        return ProviderReply(REPLIES[decision], input_tokens=10, output_tokens=2)

    return CallableSyncProvider(complete, provider_label="by-case", reports_tokens=True)


def make_judge(script: dict[str, str] | None = None, **kw: Any) -> SyncLLMJudge:
    kw.setdefault("jitter", lambda: 0.0)
    kw.setdefault("sleep", lambda _s: None)
    return SyncLLMJudge(
        rubric=AC,
        provider=by_case(script or FIXTURE["script"]),
        model_label="fixture-model",
        **kw,
    )


def cases() -> list[CalibrationCase]:
    return [CalibrationCase.from_dict(c) for c in FIXTURE["cases"]]


def report(**kw: Any) -> CalibrationReport:
    return run_calibration(
        make_judge(), cases(), dataset_id="synthetic.v1", now=lambda: NOW, **kw
    )


# ------------------------------------------------------------------ AC01 schemas


def test_p29_s10_ac01_case_documents_validate_against_the_case_schema() -> None:
    schema = load_schema("calibration-case")
    for doc in FIXTURE["cases"]:
        validate(doc, schema)
        CalibrationCase.from_dict(doc)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda d: d.pop("case_id"),
        lambda d: d.update(case_id="bad id"),
        lambda d: d.update(case_id="x" * 129),
        lambda d: d.update(schema="gentlity.calibration-case/2"),
        lambda d: d.update(dimension="toxicity"),
        lambda d: d.update(parts=[]),
        lambda d: d.update(parts=[{"role": "answer", "text": "t"}] * 33),
        lambda d: d.update(parts=[{"role": "tool", "text": "t"}]),
        lambda d: d.update(parts=[{"role": "answer"}]),
        lambda d: d.update(parts=[{"role": "answer", "text": "t", "extra": 1}]),
        lambda d: d.update(human_label="maybe"),
        lambda d: d.update(difficulty="hard"),
        lambda d: d.update(extra="x"),
        lambda d: d.update(labels=[{"labeler": "a b", "label": "pass"}]),
        lambda d: d.update(source="s" * 201),
    ],
)
def test_p29_s10_ac01_invalid_case_documents_are_rejected(mutate: Any) -> None:
    doc = copy.deepcopy(FIXTURE["cases"][0])
    mutate(doc)
    with pytest.raises(ValueError):
        CalibrationCase.from_dict(doc)


def test_p29_s10_ac01_report_validates_and_rejects_content_members() -> None:
    schema = load_schema("calibration-report")
    doc = report().document
    validate(doc, schema)
    assert doc["schema"] == "gentlity.calibration-report/1"
    for mutate in (
        lambda d: d.update(text="raw content"),
        lambda d: d["per_case"][0].update(reason="free text"),
        lambda d: d["headline"].update(reason="free text"),
        lambda d: d.update(schema="gentlity.calibration-report/2"),
        lambda d: d["rubric"].update(fingerprint="xyz"),
        lambda d: d["per_case"][0].update(decision="MAYBE"),
        lambda d: d["failures_by_class"].update({"free text": 1}),
        lambda d: d["dataset"]["by_dimension"].update({"toxicity": 1}),
    ):
        broken = copy.deepcopy(doc)
        mutate(broken)
        with pytest.raises(SchemaViolation):
            validate(broken, schema)
        with pytest.raises(ValueError):
            CalibrationReport(broken)


def test_p29_s10_schema_validator_rejects_unsupported_keywords() -> None:
    with pytest.raises(ValueError):
        validate({}, {"oneOf": []})


def test_p29_s10_schemas_are_valid_json_with_ids() -> None:
    for name, ident in (
        ("calibration-case", "gentlity.calibration-case/1"),
        ("calibration-report", "gentlity.calibration-report/1"),
    ):
        schema = load_schema(name)
        assert schema["$id"] == ident and schema["additionalProperties"] is False
    with pytest.raises(ValueError):
        load_schema("other")


# ------------------------------------------------------------------ AC02 metrics


def test_p29_s10_ac02_metrics_match_hand_computed_values() -> None:
    doc = report().document
    want = FIXTURE["expected"]["headline"]
    got = doc["headline"]
    assert got["n"] == want["n"] == 17
    assert got["insufficient_for_rates"] is False
    assert got["matrix"] == want["matrix"]
    assert (got["false_negatives"], got["false_positives"], got["over_confident"]) == (
        1,
        1,
        1,
    )

    def nd(rate: dict[str, Any]) -> tuple[int, int]:
        return rate["numerator"], rate["denominator"]

    for key in ("abstention", "accuracy_on_answered"):
        assert nd(got[key]) == (want[key]["numerator"], want[key]["denominator"])
    for human in ("pass", "fail", "unknown"):
        assert nd(got["abstention_by_human"][human]) == (
            want["abstention_by_human"][human]["numerator"],
            want["abstention_by_human"][human]["denominator"],
        )
    for cls in ("pass", "fail"):
        for metric in ("precision", "recall"):
            assert nd(got[metric][cls]) == (
                want[metric][cls]["numerator"],
                want[metric][cls]["denominator"],
            )
    assert got["agreement"]["decided"] == 16
    assert nd(got["agreement"]["raw"]) == (11, 16)
    assert got["agreement"]["kappa"] == pytest.approx(float(Fraction(17, 33)), abs=1e-6)
    assert nd(got["confidence_accuracy"]["high"]) == (9, 12)
    assert nd(got["confidence_accuracy"]["medium"]) == (0, 0)
    assert got["confidence_accuracy"]["medium"]["rate"] is None
    # rates are the exact quotients (rounded to 6 places) and carry Wilson intervals
    rate = got["abstention"]
    assert rate["rate"] == round(4 / 17, 6) and rate["method"] == "wilson-95"
    assert rate["wilson_low"] < rate["rate"] < rate["wilson_high"]
    assert got["precision"]["pass"]["rate"] == round(5 / 7, 6)
    assert got["recall"]["fail"]["rate"] == 0.8


def test_p29_s10_ac02_execution_failures_are_a_separate_column_never_a_decision() -> (
    None
):
    doc = report().document
    assert doc["headline"]["matrix"]["pass"]["FAILURE"] == 1
    assert doc["failures_by_class"] == FIXTURE["expected"]["failures_by_class"]
    p08 = next(c for c in doc["per_case"] if c["case_id"] == "p08")
    assert p08["decision"] == "FAILURE"
    assert "p08" not in doc["misjudged_case_ids"]
    # excluded from agreement, abstention numerator and answered
    assert doc["headline"]["agreement"]["decided"] == 16
    assert doc["headline"]["abstention"]["numerator"] == 4


def test_p29_s10_wilson_interval_known_values_and_bounds() -> None:
    low, high = wilson_interval(5, 10)  # type: ignore[misc]
    assert (round(low, 4), round(high, 4)) == (0.2366, 0.7634)
    assert wilson_interval(0, 0) is None
    low, high = wilson_interval(0, 10)  # type: ignore[misc]
    assert low == 0.0 and 0 < high < 0.35
    low, high = wilson_interval(10, 10)  # type: ignore[misc]
    assert high == 1.0 and low > 0.65


def test_p29_s10_small_datasets_are_flagged_and_report_counts_only() -> None:
    assert MATRIX_CELLS == 12
    doc = report().document
    for name in ("borderline", "adversarial"):
        assert doc[name]["insufficient_for_rates"] is True
        assert doc[name]["abstention"]["rate"] is None
        assert doc[name]["abstention"]["denominator"] == 2  # raw counts stay
        assert doc[name]["agreement"]["kappa"] is None


# ------------------------------------------------------------------ AC03 slices


def test_p29_s10_ac03_adversarial_and_borderline_are_reported_separately() -> None:
    doc = report().document
    assert doc["headline"]["n"] == 17  # clear + ambiguous only
    assert (
        doc["borderline"]["matrix"]["pass"]
        == FIXTURE["expected"]["borderline"]["matrix"]["pass"]
    )
    assert doc["borderline"]["false_positives"] == 1 and doc["borderline"]["n"] == 2
    assert (
        doc["adversarial"]["matrix"]["fail"]
        == FIXTURE["expected"]["adversarial"]["matrix"]["fail"]
    )
    assert doc["adversarial"]["false_negatives"] == 1
    assert doc["headline"]["false_negatives"] == 1  # the adversarial FN is not in it
    assert (
        doc["dataset"]["by_difficulty"]
        == FIXTURE["expected"]["dataset"]["by_difficulty"]
    )
    assert doc["misjudged_case_ids"] == FIXTURE["expected"]["misjudged_case_ids"]
    injected = [
        c for c in FIXTURE["cases"] if "PLANTED-INJECTION" in c["parts"][1]["text"]
    ]
    assert {c["difficulty"] for c in injected} == {
        "adversarial"
    }  # injection fixtures included


# ------------------------------------------------------------------ AC04 content-free


def test_p29_s10_ac04_report_contains_no_case_text_reason_or_raw_output() -> None:
    script = dict(FIXTURE["script"])

    def complete(call: Any) -> ProviderReply:
        case_id = re.search(r"\[([a-z]\d\d)\]", call.user).group(1)  # type: ignore[union-attr]
        decision = script[case_id]
        if decision == "FAILURE":
            raise RuntimeError(f"provider echo {SECRET} {call.user}")
        reply = REPLIES[decision]
        return ProviderReply(
            reply[:-1] + f',"reason":"model reason {SECRET}"' + "}",
            input_tokens=1,
            output_tokens=1,
        )

    judge = SyncLLMJudge(
        rubric=AC,
        provider=CallableSyncProvider(
            complete, provider_label="p", reports_tokens=True
        ),
        model_label="fixture-model",
        policy=JudgePolicy(capture_reason=True),
        jitter=lambda: 0.0,
        sleep=lambda _s: None,
    )
    result = run_calibration(judge, cases(), dataset_id="synthetic.v1", now=lambda: NOW)
    text = result.to_json() + repr(result) + repr(cases()[0])
    for token in (
        "PLANTED-INJECTION-aa11",
        SECRET,
        "refund window",
        "An answer for this case",
        "model reason",
    ):
        assert token not in text
    doc = result.document
    assert doc["rubric"]["fingerprint"] == AC.fingerprint()
    assert doc["rubric"]["rubric_id"] == AC.rubric_id
    assert doc["rubric"]["rubric_version"] == AC.rubric_version
    assert doc["model_label"] == "fixture-model" and doc["template_id"] == "jp1"
    assert doc["configuration_id"] == "fixture-model.jp1.mc-medium.rp1.ct0"
    assert doc["min_confidence"] == "medium" and doc["judge_repeats"] == 1
    assert doc["created_at"] == NOW.isoformat()


def test_p29_s10_usage_summaries_are_local_provider_reported_values() -> None:
    doc = report().document
    assert doc["usage"]["input_tokens"] == 10 * 20  # 20 successful calls x 10 tokens
    assert doc["usage"]["output_tokens"] == 2 * 20
    assert doc["usage"]["latency_ms_max"] >= 0
    unreported = run_calibration(
        SyncLLMJudge(
            rubric=AC,
            provider=CallableSyncProvider(
                lambda c: ProviderReply(REPLIES["PASS"]), provider_label="p"
            ),
            model_label="m",
        ),
        cases()[:1],
        dataset_id="d",
        now=lambda: NOW,
    ).document
    assert unreported["usage"]["input_tokens"] is None


def test_p29_s10_load_cases_reads_jsonl_locally_and_hashes_the_file(
    tmp_path: pathlib.Path,
) -> None:
    path = tmp_path / "dataset.jsonl"
    path.write_text(
        "\n".join(json.dumps(c) for c in FIXTURE["cases"]) + "\n\n", "utf-8"
    )
    loaded, digest = load_cases(path)
    assert [c.case_id for c in loaded] == [c["case_id"] for c in FIXTURE["cases"]]
    import hashlib

    assert digest == hashlib.sha256(path.read_bytes()).hexdigest()
    result = run_calibration(
        make_judge(), loaded, dataset_id="d.v1", dataset_sha256=digest, now=lambda: NOW
    )
    assert result.document["dataset"]["sha256"] == digest
    bad = tmp_path / "bad.jsonl"
    bad.write_text(json.dumps(FIXTURE["cases"][0]) + "\n{not json " + SECRET + "\n")
    with pytest.raises(ValueError, match="line 2") as caught:
        load_cases(bad)
    assert SECRET not in str(caught.value)
    dup = tmp_path / "dup.jsonl"
    dup.write_text((json.dumps(FIXTURE["cases"][0]) + "\n") * 2)
    with pytest.raises(ValueError, match="unique"):
        load_cases(dup)


# ------------------------------------------------------------------ AC05 compare


def test_p29_s10_ac05_compare_reports_lists_flips_and_net_changes() -> None:
    baseline = report()
    script = dict(FIXTURE["script"])
    script["f05"] = "FAIL"  # fixes the false negative
    script["p01"] = "FAIL"  # introduces a false positive
    script["u02"] = "PASS"  # a new over-confident error
    candidate = run_calibration(
        make_judge(script), cases(), dataset_id="synthetic.v1", now=lambda: NOW
    )
    diff = compare_reports(baseline, candidate)
    assert {f.case_id: (f.from_decision, f.to_decision) for f in diff.flipped} == {
        "f05": ("PASS", "FAIL"),
        "p01": ("PASS", "FAIL"),
        "u02": ("UNKNOWN", "PASS"),
    }
    assert diff.net_false_negative_change == -1  # candidate minus baseline
    assert diff.net_false_positive_change == 1
    assert diff.net_unknown_change == -1
    assert diff.net_failure_change == 0
    assert (
        diff.common_cases == 21
        and diff.only_in_baseline == diff.only_in_candidate == ()
    )
    assert diff.rubric_fingerprint_changed is False
    assert diff.judge_agreement_raw == pytest.approx(
        17 / 20, abs=1e-6
    )  # p08 failed in both: excluded
    names = {f.name for f in dataclasses.fields(diff)}
    assert not names & {
        "verdict",
        "passed",
        "ok",
        "regression",
        "improved",
        "healthy",
        "score",
    }
    same = compare_reports(baseline, baseline)
    assert same.flipped == () and same.judge_agreement_raw == 1.0


def test_p29_s10_compare_reports_notes_missing_cases() -> None:
    full = report()
    half = run_calibration(
        make_judge(), cases()[:15], dataset_id="synthetic.v1", now=lambda: NOW
    )
    diff = compare_reports(full, half)
    assert diff.common_cases == 15
    assert set(diff.only_in_baseline) == {
        "b01",
        "b02",
        "a01",
        "a02",
        "u03",
        "u02",
    } & set(diff.only_in_baseline)
    assert len(diff.only_in_baseline) == 6 and diff.only_in_candidate == ()


# ------------------------------------------------------------------ AC06 no network


def test_p29_s10_ac06_no_network_io_other_than_the_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def refuse(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("network access attempted")

    monkeypatch.setattr(socket, "socket", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    monkeypatch.setattr(socket, "getaddrinfo", refuse)
    assert report().document["dataset"]["case_count"] == 21
    root = pathlib.Path(namespace.__file__).parent
    tree = ast.parse((root / "calibration.py").read_text())
    modules = {
        n.module.split(".")[0]
        for n in ast.walk(tree)
        if isinstance(n, ast.ImportFrom) and n.module
    } | {
        a.name.split(".")[0]
        for n in ast.walk(tree)
        if isinstance(n, ast.Import)
        for a in n.names
    }
    assert not modules & {
        "socket",
        "urllib",
        "http",
        "httpx",
        "requests",
        "ssl",
        "asyncio",
    }


# ------------------------------------------------------------------ other behaviours


def test_p29_s10_repeatability_is_measured_by_repetitions() -> None:
    flaky: dict[str, int] = {}

    def complete(call: Any) -> ProviderReply:
        case_id = re.search(r"\[([a-z]\d\d)\]", call.user).group(1)  # type: ignore[union-attr]
        flaky[case_id] = flaky.get(case_id, 0) + 1
        decision = FIXTURE["script"][case_id]
        if decision == "FAILURE":
            raise JudgeProviderUnavailableError
        if case_id in {"p01", "f01", "u02"} and flaky[case_id] == 2:
            decision = "UNKNOWN" if decision != "UNKNOWN" else "PASS"
        return ProviderReply(REPLIES[decision])

    judge = SyncLLMJudge(
        rubric=AC,
        provider=CallableSyncProvider(complete, provider_label="p"),
        model_label="m",
        limits=JudgeLimits(max_attempts=1),
        jitter=lambda: 0.0,
    )
    doc = run_calibration(
        judge, cases(), dataset_id="d", repetitions=2, now=lambda: NOW
    ).document
    rep = doc["repeatability"]
    assert (rep["repetitions"], rep["cases_compared"], rep["changed"]) == (2, 21, 3)
    assert rep["changed_by_human"]["pass"]["numerator"] == 1  # p01
    assert rep["changed_by_human"]["fail"]["numerator"] == 1  # f01
    assert rep["changed_by_human"]["unknown"]["numerator"] == 1  # u02
    # the matrix still reflects the first repetition only
    assert doc["headline"]["matrix"] == FIXTURE["expected"]["headline"]["matrix"]
    assert report().document["repeatability"] is None
    with pytest.raises(ValueError):
        run_calibration(make_judge(), cases(), dataset_id="d", repetitions=0)
    with pytest.raises(ValueError):
        run_calibration(make_judge(), cases(), dataset_id="d", repetitions=11)


def test_p29_s10_async_twin_matches_the_sync_harness() -> None:
    async def fn(call: Any) -> ProviderReply:
        case_id = re.search(r"\[([a-z]\d\d)\]", call.user).group(1)  # type: ignore[union-attr]
        decision = FIXTURE["script"][case_id]
        if decision == "FAILURE":
            raise JudgeProviderUnavailableError
        return ProviderReply(REPLIES[decision], input_tokens=10, output_tokens=2)

    judge = LLMJudge(
        rubric=AC,
        provider=CallableProvider(fn, provider_label="p", reports_tokens=True),
        model_label="fixture-model",
        jitter=lambda: 0.0,
    )
    async_report = asyncio.run(
        run_calibration_async(
            judge, cases(), dataset_id="synthetic.v1", now=lambda: NOW
        )
    )
    sync_doc, async_doc = report().document, async_report.document
    for key in (
        "headline",
        "borderline",
        "adversarial",
        "failures_by_class",
        "per_case",
    ):
        assert async_doc[key] == sync_doc[key]


def test_p29_s10_input_validation_and_content_free_reprs() -> None:
    with pytest.raises(ValueError):
        run_calibration(make_judge(), [], dataset_id="d")
    other = copy.deepcopy(FIXTURE["cases"][0])
    other["dimension"] = "groundedness"
    with pytest.raises(ValueError, match="dimension"):
        run_calibration(
            make_judge(), [CalibrationCase.from_dict(other)], dataset_id="d"
        )
    with pytest.raises(ValueError):
        run_calibration(make_judge(), cases(), dataset_id="bad id")
    with pytest.raises(ValueError):
        run_calibration(make_judge(), cases() + cases()[:1], dataset_id="d")
    case = cases()[0]
    assert "refund" not in repr(case) and "An answer" not in repr(case)
    import copy as copy_module
    import pickle

    with pytest.raises(TypeError):
        copy_module.copy(case)
    with pytest.raises(TypeError):
        pickle.dumps(case)
    rep = report()
    assert rep == CalibrationReport.from_json(rep.to_json())
    assert hash(rep) == hash(CalibrationReport.from_json(rep.to_json()))
    rep.document["headline"]["n"] = 999  # a copy: the report is immutable
    assert rep.document["headline"]["n"] == 17
