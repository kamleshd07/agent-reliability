"""Internal P28 protocol primitives; no transport or credential access.

Canonicalization accepts already wire-validated envelopes. It is not an
envelope validator. No runtime exporter policy is selected by this module.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any, Literal

_UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
_MEMBERS = {
    "run_lifecycle": ("status", "occurred_at", "exception_type"),
    "evaluation_outcome": (
        "evaluation_id",
        "indicator",
        "outcome",
        "recorded_at",
        "provenance",
        "reason_code",
    ),
    "evaluation_execution_failure": (
        "evaluation_id",
        "indicator",
        "stage",
        "exception_type",
        "occurred_at",
        "evaluator_name",
        "evaluator_version",
        "evaluator_configuration_id",
    ),
    "measurement_health": ("measurement_id", "health", "reasons", "observed_at"),
}


def _instant(value: str) -> str:
    instant = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if instant.tzinfo is None:
        raise ValueError("timestamp_timezone_required")
    instant = instant.astimezone(UTC)
    # strftime year padding differs across operating systems for years <1000.
    result = (
        f"{instant.year:04d}-{instant.month:02d}-{instant.day:02d}T"
        f"{instant.hour:02d}:{instant.minute:02d}:{instant.second:02d}"
    )
    if instant.microsecond:
        result += f".{instant.microsecond:06d}"
    return result + "+00:00"


def canonical_bytes(envelope: Mapping[str, Any]) -> bytes:
    """Contract 15.2/15.2a bytes for a validated v1 or v2 envelope."""
    version = envelope["schema_version"]
    if type(version) is not int or version not in (1, 2):
        raise ValueError("unsupported_schema_version")
    wire = envelope["payload"]
    payload = {key: wire.get(key) for key in _MEMBERS[wire["kind"]]}
    for key in ("occurred_at", "recorded_at", "observed_at"):
        if key in payload:
            payload[key] = _instant(payload[key])
    if "reasons" in payload:
        payload["reasons"] = ",".join(sorted(set(payload["reasons"])))
    if payload.get("provenance") is not None:
        provenance = payload["provenance"]
        payload["provenance"] = {
            key: provenance.get(key)
            for key in ("name", "version", "configuration_id", "deterministic")
        }
    result = {
        key: envelope[key]
        for key in (
            "schema_version",
            "source",
            "event_id",
            "producer_run_id",
            "deployment_id",
        )
    }
    result.update(
        producer_timestamp=_instant(envelope["producer_timestamp"]),
        parent_producer_run_id=envelope.get("parent_producer_run_id"),
        payload=payload,
    )
    if version == 2:
        result["producer_identity"] = {
            key: envelope["producer_identity"][key]
            for key in ("agent_id", "environment", "version")
        }
    return json.dumps(
        result,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def canonical_digest(envelope: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_bytes(envelope)).hexdigest()


def _invalid_constant(_token: str) -> Any:
    raise ValueError("invalid_json_constant")


def classify_acknowledgement(status: int, body: bytes, event_id: str) -> str:
    """Bounded strict UTF-8 acknowledgement parser, Contract 15.1 and D1.

    Diagnostics contain fixed labels only, never response content.
    """
    if status not in (200, 201):
        return "other_2xx_transient"
    if len(body) > 65536:
        return "not_ack:response_unparseable"
    try:
        decoded = body.decode("utf-8", errors="strict")
        if decoded.startswith("\ufeff"):
            return "not_ack:response_unparseable"
        value = json.loads(decoded, parse_constant=_invalid_constant)
    except (ValueError, RecursionError):
        return "not_ack:response_unparseable"
    if not isinstance(value, dict):
        return "not_ack:response_unparseable"
    if (
        value.get("event_id") == event_id
        and isinstance(value.get("run_id"), str)
        and _UUID.fullmatch(value["run_id"])
        and value.get("status") == ("accepted" if status == 201 else "duplicate")
        and value.get("durability") == "committed"
    ):
        return "ack:COMMITTED" if status == 201 else "ack:DUPLICATE"
    return "not_ack:acknowledgement_mismatch"


def retry_after(
    field_lines: Sequence[str], *, grammar: Literal["RA-a", "RA-b"]
) -> int | None:
    """Both documented alternatives; caller must select an approved grammar."""
    if len(field_lines) != 1:
        return None
    value = field_lines[0]
    if not value or any(char < "0" or char > "9" for char in value):
        return None
    if grammar == "RA-a" and len(value) > 10:
        return None
    # Avoid integer conversion limits and fixed-width overflow, including zeros.
    significant = value.lstrip("0") or "0"
    if len(significant) > 10 or (len(significant) == 10 and significant > "4294967295"):
        return None
    return int(significant)


def _authority(url: str, scheme: str) -> tuple[str, str | None] | None:
    if not url.startswith(scheme + "://"):
        return None
    if any(not "!" <= char <= "~" for char in url) or "\\" in url or "#" in url:
        return None
    authority = re.split(r"[/ ?]", url[len(scheme) + 3 :], maxsplit=1)[0]
    if not authority or "@" in authority or "%" in authority:
        return None
    if authority.startswith("["):
        close = authority.find("]")
        if close < 0:
            return None
        host, tail = authority[1:close], authority[close + 1 :]
        if not host or not re.fullmatch(r"[0-9A-Fa-f:.]+", host):
            return None
        if tail and not tail.startswith(":"):
            return None
        port = tail[1:] if tail else None
        host = "[" + host + "]"
    else:
        if "[" in authority or "]" in authority or authority.count(":") > 1:
            return None
        host, separator, suffix = authority.partition(":")
        port = suffix if separator else None
    if not host:
        return None
    if port is not None and (
        not re.fullmatch(r"[1-9][0-9]{0,4}", port) or int(port) > 65535
    ):
        return None
    return host, port


def valid_https_endpoint(url: str) -> bool:
    """Exact A-https-1 syntax, not DNS resolution or TLS peer verification."""
    return _authority(url, "https") is not None


def loopback_url(url: str, *, literal_only: bool) -> str:
    """Base fixture rule plus explicit A2-3 policy; never consult DNS."""
    if url.startswith("https://"):
        return "not_a_plaintext_case"
    authority = _authority(url, "http")
    if authority is None:
        return "reject"
    host, _port = authority
    if host == "[::1]":
        return "accept"
    if host.lower() == "localhost":
        return "reject" if literal_only else "accept"
    octets = host.split(".")
    if len(octets) != 4 or octets[0] != "127":
        return "reject"
    if all(
        re.fullmatch(r"0|[1-9][0-9]{0,2}", octet) and int(octet) <= 255
        for octet in octets
    ):
        return "accept"
    return "reject"
