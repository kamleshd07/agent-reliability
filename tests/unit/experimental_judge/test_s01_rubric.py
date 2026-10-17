"""P29-S01-AC01 / AC05: rubric loading, vectors, immutability, fingerprint."""

from __future__ import annotations

import copy
import dataclasses
import json
from typing import Any

import pytest

from agent_reliability.experimental.judge import (
    Confidence,
    ContentRole,
    JudgeDimension,
    Rubric,
)
from tests.fakes.p29_judge import load_fixture

pytestmark = pytest.mark.unit

_VALID = load_fixture("rubric_valid.json")["cases"]
_INVALID = load_fixture("rubric_invalid.json")["cases"]


@pytest.mark.parametrize("case", _VALID, ids=[c["id"] for c in _VALID])
def test_p29_s01_ac01_valid_rubric_cases_load(case: dict[str, Any]) -> None:
    rubric = Rubric.from_dict(case["input"])
    assert rubric.rubric_id == case["input"]["rubric_id"]
    if "min_confidence" in case["expected"]:
        assert rubric.min_confidence.value == case["expected"]["min_confidence"]


@pytest.mark.parametrize("case", _INVALID, ids=[c["id"] for c in _INVALID])
def test_p29_s01_ac01_invalid_rubric_cases_raise_value_error(
    case: dict[str, Any],
) -> None:
    with pytest.raises(ValueError):
        Rubric.from_dict(case["input"])


@pytest.mark.parametrize("case", _INVALID[:6], ids=[c["id"] for c in _INVALID[:6]])
def test_p29_s01_ac01_invalid_rubric_json_text_raises_value_error(
    case: dict[str, Any],
) -> None:
    with pytest.raises(ValueError):
        Rubric.from_json(json.dumps(case["input"]))


def test_p29_s01_ac01_defaults_are_materialized() -> None:
    doc = _VALID[0]["input"]
    rubric = Rubric.from_dict(doc)
    assert rubric.dimension is JudgeDimension.ANSWER_CORRECTNESS
    assert rubric.min_confidence is Confidence.MEDIUM
    assert rubric.require_citations is False
    assert rubric.missing_input_codes == (
        (ContentRole.REFERENCE, "reference_insufficient"),
    )
    assert rubric.missing_code_for(ContentRole.REFERENCE) == "reference_insufficient"
    assert rubric.missing_code_for(ContentRole.CONTEXT) is None


def test_p29_s01_ac01_json_loader_rejects_duplicates_and_non_finite() -> None:
    base = json.dumps(_VALID[0]["input"])
    with pytest.raises(ValueError):
        Rubric.from_json(base[:-1] + ', "rubric_id": "other"}')
    with pytest.raises(ValueError):
        Rubric.from_json(base[:-1] + ', "x": NaN}')
    with pytest.raises(ValueError):
        Rubric.from_json("not json")
    with pytest.raises(ValueError):
        Rubric.from_json("[" * 50000)


def test_p29_s01_ac01_json_file_loader(tmp_path: Any) -> None:
    path = tmp_path / "rubric.json"
    path.write_text(json.dumps(_VALID[0]["input"]), encoding="utf-8")
    assert Rubric.from_json_file(path) == Rubric.from_dict(_VALID[0]["input"])
    assert Rubric.from_json_file(str(path)).rubric_id == "judge-answer-correctness"


def test_p29_s01_ac01_loaded_rubric_is_immutable() -> None:
    rubric = Rubric.from_dict(_VALID[0]["input"])
    with pytest.raises(dataclasses.FrozenInstanceError):
        rubric.rubric_id = "other"  # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        rubric.criteria[0].text = "other"  # type: ignore[misc]
    assert isinstance(rubric.criteria, tuple)
    assert isinstance(rubric.inputs_required, tuple)
    assert isinstance(rubric.reason_codes.fail, tuple)
    assert hash(rubric) == hash(Rubric.from_dict(_VALID[0]["input"]))
    # Mutating the source document after load cannot change the rubric.
    source = copy.deepcopy(_VALID[0]["input"])
    loaded = Rubric.from_dict(source)
    source["criteria"][0]["text"] = "changed"
    source["reason_codes"]["pass"].append("extra")
    assert loaded.criteria[0].text == "Criterion one."
    assert loaded.reason_codes.pass_ == ("consistent_with_reference",)


def test_p29_s01_ac05_fingerprint_stable_across_key_order_and_whitespace() -> None:
    doc = _VALID[1]["input"]
    reordered = dict(reversed(list(doc.items())))
    reordered["reason_codes"] = dict(reversed(list(doc["reason_codes"].items())))
    a = Rubric.from_dict(doc).fingerprint()
    b = Rubric.from_json(json.dumps(reordered, indent=4)).fingerprint()
    c = Rubric.from_json(json.dumps(doc, separators=(",", ":"))).fingerprint()
    assert a == b == c
    assert len(a) == 64


def test_p29_s01_ac05_fingerprint_equal_for_explicit_default_members() -> None:
    doc = copy.deepcopy(_VALID[0]["input"])
    explicit = copy.deepcopy(doc)
    explicit["require_citations"] = False
    explicit["min_confidence"] = "medium"
    explicit["missing_input_codes"] = {"reference": "reference_insufficient"}
    assert (
        Rubric.from_dict(doc).fingerprint() == Rubric.from_dict(explicit).fingerprint()
    )


def test_p29_s01_ac05_fingerprint_changes_with_content() -> None:
    doc = copy.deepcopy(_VALID[0]["input"])
    changed = copy.deepcopy(doc)
    changed["criteria"][0]["text"] = "Criterion one!"
    assert (
        Rubric.from_dict(doc).fingerprint() != Rubric.from_dict(changed).fingerprint()
    )
    changed_order = copy.deepcopy(doc)
    changed_order["reason_codes"]["fail"] = [
        "missing_required_facts",
        "contradicts_reference",
    ]
    assert (
        Rubric.from_dict(doc).fingerprint()
        != Rubric.from_dict(changed_order).fingerprint()
    )


def test_p29_s01_ac05_pinned_fingerprint_match_and_mismatch() -> None:
    doc = _VALID[0]["input"]
    pin = Rubric.from_dict(doc).fingerprint()
    assert Rubric.from_dict(doc, pinned_fingerprint=pin).fingerprint() == pin
    assert Rubric.from_json(json.dumps(doc), pinned_fingerprint=pin).rubric_id
    edited = copy.deepcopy(doc)
    edited["criteria"][0]["text"] = "silently edited, same rubric_version"
    with pytest.raises(ValueError, match="pinned_fingerprint"):
        Rubric.from_dict(edited, pinned_fingerprint=pin)
    for bad in ("", "abc", pin.upper(), pin[:-1], 5):
        with pytest.raises(ValueError):
            Rubric.from_dict(doc, pinned_fingerprint=bad)  # type: ignore[arg-type]


def test_p29_s01_ac05_fingerprint_is_local_and_not_in_message() -> None:
    doc = _VALID[0]["input"]
    pin = Rubric.from_dict(doc).fingerprint()
    edited = copy.deepcopy(doc)
    edited["criteria"][0]["text"] = "edited"
    with pytest.raises(ValueError) as caught:
        Rubric.from_dict(edited, pinned_fingerprint=pin)
    assert pin not in str(caught.value)
    assert "fingerprint" not in Rubric.from_dict(doc).as_document()
