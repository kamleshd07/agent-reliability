"""The published file-format schemas, and hostile documents against the parsers."""

from __future__ import annotations

import copy
import json
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest

from agent_reliability.experimental.calibration import (
    AssessmentError,
    CalibrationAssessment,
    Split,
    assess_admission,
    build_assessment,
)
from agent_reliability.experimental.calibration._schemas import check, load_schema
from tests.fakes.p29_calibration import (
    NOW,
    case_doc,
    fingerprint,
    heldout_cases,
    human_policy,
    load,
    perfect_outcomes,
    table,
)

pytestmark = pytest.mark.unit

NAMES = ("reference-dataset", "reference-case", "calibration-assessment")


@pytest.mark.parametrize("name", NAMES)
def test_every_schema_is_published_strict_and_identified(name: str) -> None:
    schema = load_schema(name)
    assert schema["$id"] == f"gentlity.{name}/1"
    assert schema["additionalProperties"] is False
    assert "schema" in schema["required"]
    with pytest.raises(ValueError):
        load_schema("../escape")


def test_schema_loading_returns_independent_copies() -> None:
    first = load_schema("reference-case")
    first["required"].append("tampered")
    assert "tampered" not in load_schema("reference-case")["required"]


def test_case_schema_accepts_the_documented_shapes_and_rejects_extras() -> None:
    check(case_doc("ok", adjudication="none"), "reference-case")
    check(
        case_doc("ok2", "unknown", provenance="human_adjudicated",
                 labels=[("a", "pass"), ("b", "fail")], adjudication="unresolved"),
        "reference-case",
    )  # fmt: skip
    for mutate in (
        lambda d: d.update(extra=1),
        lambda d: d.update(label_provenance="gold"),
        lambda d: d.update(adjudication={"method": "vote"}),
        lambda d: d.update(adjudication={"method": "none", "by": "x"}),
        lambda d: d.update(schema="gentlity.calibration-case/1"),
        lambda d: d.update(case_id="has space"),
        lambda d: d["parts"][0].update(role="system"),
    ):
        doc = case_doc("bad")
        mutate(doc)
        with pytest.raises(ValueError):
            check(doc, "reference-case")


def _assessment(tmp_path: Path) -> CalibrationAssessment:
    ds = load(
        tmp_path,
        {"heldout": heldout_cases(provenance="human_multi", multi=True)},
        provenance={"heldout": "human_multi"},
    )
    outcomes = {k: [v] * 3 for k, v in perfect_outcomes(ds).items()}
    return build_assessment(
        ds, Split.HELDOUT, table(outcomes), now=NOW - timedelta(days=1)
    )


def _paths(value: Any, prefix: tuple[Any, ...] = ()):  # type: ignore[no-untyped-def]
    if isinstance(value, dict):
        for key, child in value.items():
            yield (*prefix, key)
            yield from _paths(child, (*prefix, key))


def _walk_set(document: Any, path: tuple[Any, ...], value: Any) -> None:
    for key in path[:-1]:
        document = document[key]
    if isinstance(value, str) and value == _DELETE:
        del document[path[-1]]
    else:
        document[path[-1]] = value


_DELETE = "<delete>"  # a plain sentinel string survives deepcopy


def test_every_generated_assessment_conforms_to_its_published_schema(
    tmp_path: Path,
) -> None:
    a = _assessment(tmp_path)
    check(a.document, "calibration-assessment")


def test_hostile_mutations_of_an_assessment_never_crash_the_parser_or_the_decision(
    tmp_path: Path,
) -> None:
    base = _assessment(tmp_path).document
    rejected = survived = 0
    for path in _paths(base):
        if path[0] == "integrity":
            continue
        for replacement in (_DELETE, "x", None, -1, [], {}, 1.5, True):
            document = copy.deepcopy(base)
            try:
                _walk_set(document, path, replacement)
                assessment = CalibrationAssessment(document)
            except AssessmentError:
                rejected += 1
                continue
            except (
                KeyError,
                TypeError,
            ) as error:  # pragma: no cover - would be a defect
                pytest.fail(f"unclassified parser failure at {path}: {error!r}")
            survived += 1
            # A document that still parses must still yield a decision, never a crash.
            decision = assess_admission(assessment, fingerprint(), human_policy(), NOW)
            assert decision.status.value
    assert rejected > survived > 0


def test_unknown_members_and_wrong_schema_ids_are_rejected(tmp_path: Path) -> None:
    document = _assessment(tmp_path).document
    for mutate in (
        lambda d: d.update(extra="x"),
        lambda d: d.update(schema="gentlity.calibration-assessment/2"),
        lambda d: d["dataset"].update(attested=False),
        lambda d: d["metrics"].update(run_index_used=1),
        lambda d: d["integrity"].update(sha256="nothex"),
    ):
        broken = copy.deepcopy(document)
        mutate(broken)
        with pytest.raises(AssessmentError):
            CalibrationAssessment(broken)


def test_oversized_assessment_text_is_refused() -> None:
    with pytest.raises(AssessmentError, match="large"):
        CalibrationAssessment.from_json(json.dumps({"x": "a" * 2_000_000}))
