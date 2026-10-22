"""Property tests: metric invariants hold for arbitrary labelled sets and outcomes."""

from __future__ import annotations

import json
import math
from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from agent_reliability.experimental.calibration import (
    DISAGREEMENT_CATEGORIES,
    compare_judges,
    repeatability,
    split_metrics,
)
from agent_reliability.experimental.calibration.dataset import (
    LabelProvenance,
    ReferenceCase,
    _parse_case,
)
from agent_reliability.experimental.judge import JudgeDimension
from tests.fakes.p29_calibration import case_doc, fingerprint, table

pytestmark = pytest.mark.property

OUTCOMES = ["PASS", "FAIL", "UNKNOWN", "FAILURE", "MISSING"]
FP_A, FP_B = fingerprint("prop-a"), fingerprint("prop-b")


def _cases(labels: list[tuple[str, str]]) -> list[ReferenceCase]:
    return [
        _parse_case(
            case_doc(f"c{i:03d}", label, difficulty=difficulty),
            LabelProvenance.SYNTHETIC,
            JudgeDimension.ANSWER_CORRECTNESS,
        )
        for i, (label, difficulty) in enumerate(labels)
    ]


labelled = st.lists(
    st.tuples(
        st.sampled_from(["pass", "fail", "unknown"]),
        st.sampled_from(["clear", "ambiguous", "borderline", "adversarial"]),
    ),
    min_size=0,
    max_size=40,
)


@st.composite
def scenario(draw: st.DrawFn) -> tuple[list[ReferenceCase], dict[str, Any]]:
    cases = _cases(draw(labelled))
    outcomes = {c.case_id: draw(st.sampled_from(OUTCOMES)) for c in cases}
    return cases, outcomes


def _walk(value: Any):  # type: ignore[no-untyped-def]
    if isinstance(value, dict):
        for v in value.values():
            yield from _walk(v)
    elif isinstance(value, (list, tuple)):
        for v in value:
            yield from _walk(v)
    else:
        yield value


@given(scenario())
@settings(max_examples=150, deadline=None)
def test_counts_partition_and_rates_are_consistent(
    data: tuple[list[ReferenceCase], dict[str, Any]],
) -> None:
    cases, outcomes = data
    metrics = split_metrics(cases, table(outcomes, fp=FP_A))
    for block in (metrics["headline"], *metrics["strata"].values()):
        c, r = block["counts"], block["rates"]
        assert (
            c["answered"] + c["abstained"] + c["failed"] + c["missing"]
            == block["n_labelled"]
        )
        assert c["tp"] + c["fn"] + c["fp"] + c["tn"] == c["answered"]
        assert c["tp"] + c["fn"] <= c["support_fail"]
        assert c["support_fail"] + c["support_pass"] == block["n_labelled"]
        for rate in r.values():
            assert (
                0 <= rate["numerator"] <= rate["denominator"]
                or rate["denominator"] == 0
            )
            value = rate["value"]
            assert value is None or 0.0 <= value <= 1.0
            assert (value is None) == ("undefined_reason" in rate)
        cov, verdict = r["committed_coverage"]["value"], r["verdict_rate"]["value"]
        if cov is not None and verdict is not None:
            assert cov <= verdict + 1e-9
        eff, cond = r["fnr_effective"]["value"], r["fnr_conditional"]["value"]
        if eff is not None and cond is not None:
            assert eff >= cond - 1e-9
        rec = r["recall_fail"]["value"]
        if rec is not None and cond is not None:
            assert rec == pytest.approx(1 - cond, abs=1e-6)
        ae, ac = r["accuracy_effective"]["value"], r["accuracy_conditional"]["value"]
        if ae is not None and ac is not None:
            assert ae <= ac + 1e-9
    for leaf in _walk(metrics):
        if isinstance(leaf, float):
            assert math.isfinite(leaf)
    json.dumps(metrics, allow_nan=False)  # strict JSON: no NaN, no Infinity


@given(scenario(), st.randoms(use_true_random=False))
@settings(max_examples=60, deadline=None)
def test_metrics_do_not_depend_on_case_order(
    data: tuple[list[ReferenceCase], dict[str, Any]], rnd: Any
) -> None:
    cases, outcomes = data
    shuffled = list(cases)
    rnd.shuffle(shuffled)
    t = table(outcomes, fp=FP_A)
    assert split_metrics(cases, t) == split_metrics(shuffled, t)


@given(scenario(), scenario())
@settings(max_examples=60, deadline=None)
def test_every_example_is_in_exactly_one_disagreement_category(
    first: tuple[list[ReferenceCase], dict[str, Any]],
    second: tuple[list[ReferenceCase], dict[str, Any]],
) -> None:
    cases, a = first
    b = {k: second[1].get(k, "PASS") for k in a}
    report = compare_judges(cases, table(a, fp=FP_A), table(b, fp=FP_B))
    assert sum(report["categories"].values()) == len(cases)
    assert set(report["categories"]) == set(DISAGREEMENT_CATEGORIES)
    assert report["shared_errors"] >= 0


@given(
    st.lists(
        st.lists(st.sampled_from(OUTCOMES[:4]), min_size=1, max_size=4),
        min_size=0,
        max_size=15,
    )
)
@settings(max_examples=100, deadline=None)
def test_repeatability_accounts_for_every_multi_run_case(
    runs: list[list[str]],
) -> None:
    cases = _cases([("pass", "clear")] * len(runs))
    t = table({c.case_id: r for c, r in zip(cases, runs, strict=True)}, fp=FP_A)
    report = repeatability(cases, t)
    multi = sum(1 for r in runs if len(r) >= 2)
    assert report["cases_compared"] + report["excluded_for_failures"] == multi
    assert report["unstable"] <= report["cases_compared"]
    worst = report["unstable_rate_worst_case"]
    assert worst["numerator"] == report["unstable"] + report["excluded_for_failures"]
