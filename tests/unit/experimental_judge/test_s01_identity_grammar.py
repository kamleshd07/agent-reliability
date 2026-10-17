"""P29-S01-AC02: identity composition satisfies both grammars (CON 2.2.1)."""

from __future__ import annotations

import re

import pytest

from agent_reliability.adapters import _http_delivery
from agent_reliability.evaluation import EvaluatorIdentity
from agent_reliability.evaluation._validation import _OPAQUE_ID as SDK_OPAQUE
from agent_reliability.experimental.judge import (
    Confidence,
    JudgePolicy,
    Rubric,
    SamplingPolicy,
    compose_configuration_id,
    compose_identity,
    validate_identity_value,
    validate_model_label,
)
from tests.fakes.p29_judge import load_fixture

pytestmark = pytest.mark.unit

# Copied from platform api/evidence_schemas.py::_OPAQUE_ID_PATTERN (read-only source).
WIRE = re.compile(r"^(?:[A-Za-z0-9](?:[A-Za-z0-9._:/-]{0,198}[A-Za-z0-9])?)$")
EXPORTER = _http_delivery._OPAQUE

#: (value, sdk, wire, exporter, p29) from contract section 2.2.1.
VECTORS = [
    ("2026-10.r1", True, True, True, True),
    ("local-llama3-8b-q4.jp1.mc-medium.rp1.ct0", True, True, True, True),
    ("a", True, True, True, True),
    ("A.b_c-1", True, True, True, True),
    ("a" * 128, True, True, True, True),
    ("1.0.0+build5", True, False, False, False),
    ("a+", False, False, False, False),
    ("v1:rc", False, True, True, False),
    ("a/b", False, True, True, False),
    ("a" * 129, False, True, True, False),
    ("a" * 200, False, True, True, False),
    ("a" * 201, False, False, False, False),
    ("-abc", False, False, False, False),
    ("abc-", False, False, False, False),
    ("", False, False, False, False),
    ("a b", False, False, False, False),
    ("café", False, False, False, False),
]


@pytest.mark.parametrize("value,sdk,wire,exporter,p29", VECTORS)
def test_p29_s01_ac02_vectors_in_each_grammar(
    value: str, sdk: bool, wire: bool, exporter: bool, p29: bool
) -> None:
    assert (SDK_OPAQUE.fullmatch(value) is not None) is sdk
    assert (WIRE.fullmatch(value) is not None) is wire
    assert (EXPORTER.fullmatch(value) is not None) is exporter
    if p29:
        assert validate_identity_value(value, "v") == value
        assert sdk and wire and exporter
    else:
        with pytest.raises(ValueError):
            validate_identity_value(value, "v")


def test_p29_s01_ac02_sdk_identity_accepts_what_p29_accepts() -> None:
    for value, _sdk, _wire, _exporter, p29 in VECTORS:
        if p29:
            EvaluatorIdentity("judge-x", value, value)


def _rubric(version: str = "2026-10.r1") -> Rubric:
    doc = load_fixture("rubric_valid.json")["cases"][0]["input"]
    return Rubric.from_dict({**doc, "rubric_version": version})


def test_p29_s01_ac02_composed_identity_satisfies_every_grammar() -> None:
    identity = compose_identity(
        _rubric("a" * 128), model_label="local-llama3-8b-q4", policy=JudgePolicy()
    )
    assert identity.name == "judge-answer-correctness"
    assert identity.version == "a" * 128
    assert identity.configuration_id == "local-llama3-8b-q4.jp1.mc-medium.rp1.ct0"
    for value in (identity.version, identity.configuration_id):
        assert value is not None
        assert SDK_OPAQUE.fullmatch(value)
        assert WIRE.fullmatch(value)
        assert EXPORTER.fullmatch(value)
        assert len(value) <= 128


def test_p29_s01_ac02_exporter_precheck_accepts_composed_values() -> None:
    identity = compose_identity(
        _rubric(), model_label="m" * 64, policy=JudgePolicy(repeats=3)
    )
    assert identity.configuration_id is not None
    assert len(identity.configuration_id) <= 128
    assert EXPORTER.fullmatch(identity.configuration_id)
    assert identity.configuration_id.endswith(".jp1.mc-medium.rp3.ct0")


@pytest.mark.parametrize(
    "label",
    ["", "a" * 65, "x+y", "host:8080", "a/b", "-a", "a-", "a b", "café", "http://h"],
)
def test_p29_s01_ac02_bad_model_label_raises(label: str) -> None:
    with pytest.raises(ValueError):
        validate_model_label(label)
    with pytest.raises(ValueError):
        compose_identity(_rubric(), model_label=label)


def test_p29_s01_ac02_model_label_boundaries() -> None:
    assert validate_model_label("a") == "a"
    assert validate_model_label("a" * 64) == "a" * 64
    with pytest.raises(ValueError):
        validate_model_label(5)


@pytest.mark.parametrize("version", ["1.0.0+build5", "v1:rc", "a/b", "a" * 129])
def test_p29_s01_ac02_rubric_version_outside_intersection_rejected(
    version: str,
) -> None:
    with pytest.raises(ValueError):
        _rubric(version)


def test_p29_s01_ac02_salt_in_intersection_grammar() -> None:
    assert SamplingPolicy(salt="").salt == ""
    for salt in ("a", "A.b_c-1", "s" * 64):
        assert SamplingPolicy(salt=salt).salt == salt
        assert WIRE.fullmatch(salt) and SDK_OPAQUE.fullmatch(salt)
    for salt in ("s" * 65, "a+b", "v1:rc", "a/b", "-a", "a-", "a b"):
        with pytest.raises(ValueError):
            SamplingPolicy(salt=salt)


def test_p29_s01_ac02_configuration_id_encodes_effective_policy() -> None:
    rubric = _rubric()
    base = {"model_label": "m", "require_citations": False}
    assert (
        compose_configuration_id(min_confidence=Confidence.HIGH, repeats=2, **base)  # type: ignore[arg-type]
        == "m.jp1.mc-high.rp2.ct0"
    )
    assert (
        compose_identity(
            rubric, model_label="m", policy=JudgePolicy(min_confidence=Confidence.LOW)
        ).configuration_id
        == "m.jp1.mc-low.rp1.ct0"
    )
    with pytest.raises(ValueError):
        compose_configuration_id(
            model_label="m",
            min_confidence=Confidence.LOW,
            repeats=4,
            require_citations=False,
        )
