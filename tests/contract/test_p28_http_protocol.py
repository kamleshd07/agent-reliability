"""Unmodified platform fixtures exercised against SDK protocol helpers."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from agent_reliability.adapters._http_protocol import (
    canonical_bytes,
    canonical_digest,
    classify_acknowledgement,
    loopback_url,
    retry_after,
    valid_https_endpoint,
)

FIXTURES = Path(__file__).parents[1] / "fixtures" / "p28"
OPERATIONAL = json.loads((FIXTURES / "operational_vectors.json").read_text())


def test_fixture_manifest():
    for name, entry in json.loads((FIXTURES / "manifest.json").read_text()).items():
        assert (
            hashlib.sha256((FIXTURES / name).read_bytes()).hexdigest()
            == entry["sha256"]
        )


@pytest.mark.parametrize(
    "vector",
    [
        vector
        for name in (
            "v1_digest_vectors.json",
            "v2_digest_vectors_specification_only.json",
        )
        for vector in json.loads((FIXTURES / name).read_text())["vectors"]
    ],
    ids=lambda vector: vector["id"],
)
def test_canonical_vectors(vector):
    assert canonical_bytes(vector["wire_input"]) == vector[
        "canonical_utf8_text"
    ].encode("utf-8")
    assert canonical_digest(vector["wire_input"]) == vector["sha256_lowercase_hex"]


@pytest.mark.parametrize(
    "vector",
    [
        vector
        for name in (
            "acknowledgement_vectors",
            "acknowledgement_byte_vectors",
            "acknowledgement_escape_vectors",
            "acknowledgement_extra_member_vectors",
        )
        for vector in OPERATIONAL[name]["vectors"]
    ],
    ids=lambda vector: vector["id"],
)
def test_acknowledgement_vectors(vector):
    body = (
        bytes.fromhex(vector["body_hex"])
        if "body_hex" in vector
        else vector["body_text"].encode("utf-8")
    )
    result = classify_acknowledgement(
        vector["http_status"], body, vector["sent_event_id"]
    )
    assert result in vector.get("allowed", [vector.get("expected")])


@pytest.mark.parametrize("vector", OPERATIONAL["loopback_url_vectors"])
def test_loopback_base_and_a2_3(vector):
    url = (
        vector["input"]
        if "input" in vector
        else "".join(map(chr, vector["input_code_points"]))
    )
    assert loopback_url(url, literal_only=False) == vector["expected"]
    # Preserve base vectors; apply the explicitly documented policy separately.
    expected = vector["expected"]
    if url.startswith("http://"):
        authority = url[7:].split("/", 1)[0].split("?", 1)[0]
        if authority.split(":", 1)[0].lower() == "localhost":
            expected = "reject"
    assert loopback_url(url, literal_only=True) == expected


@pytest.mark.parametrize(
    "vector", OPERATIONAL["https_endpoint_vectors_a_https_1"]["vectors"]
)
def test_https_vectors(vector):
    assert valid_https_endpoint(
        vector["input"]
        if "input" in vector
        else "".join(map(chr, vector["input_code_points"]))
    ) == (vector["expected"] == "accept")


@pytest.mark.parametrize("vector", OPERATIONAL["retry_after_vectors"])
def test_retry_after_alternatives(vector):
    lines = vector.get("field_lines")
    if lines is None:
        lines = [
            "".join(map(chr, points)) for points in vector["field_lines_code_points"]
        ]
    expected = vector["expected_delay_seconds"]
    assert retry_after(lines, grammar="RA-a") == expected
    expected_b = 60 if vector["id"] == "ra-006" else expected
    assert retry_after(lines, grammar="RA-b") == expected_b


def test_acknowledgement_size_bound():
    assert classify_acknowledgement(201, b" " * 65537, "evt_1") == (
        "not_ack:response_unparseable"
    )


def test_retry_after_large_values_without_integer_overflow():
    assert retry_after(["0" * 10000 + "60"], grammar="RA-b") == 60
    assert retry_after(["9" * 10000], grammar="RA-b") is None
