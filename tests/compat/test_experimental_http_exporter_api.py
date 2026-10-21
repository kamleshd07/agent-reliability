"""Snapshot of the EXPERIMENTAL HTTP exporter entry points (docs/GA_CONTRACT.md).

The exporter classes, delivery status types, local exceptions and the optional
``HealthEvidenceSink`` capability are public and documented but EXPERIMENTAL in 1.3:
they may change in a minor release with release notes (docs/VERSIONING.md). This file
makes any change visible. The ``_http_*`` implementation modules and the ``_transport``
test seam are INTERNAL and deliberately not snapshotted.
"""

from __future__ import annotations

import dataclasses
import enum
import inspect

import pytest

import agent_reliability.adapters.http_event_sink as sink_module
from agent_reliability.ports import event_sink as ports

pytestmark = pytest.mark.contract

_CONSTRUCTOR = (
    "endpoint",
    "credential_provider",
    "deployment_id",
    "expected_agent",
    "proxy",
    "ca_bundle",
    "max_queue_records",
    "max_queue_bytes",
    "retry_max_attempts",
    "active_delivery_seconds",
    "maximum_residence_seconds",
    "max_throttle_responses",
    "max_active_run_age",
    "closure_reserve_records",
    "closure_reserve_bytes",
    "provider_timeout",
    "indicator_allowlist",
)
_DEFAULTS = {
    "proxy": None,
    "ca_bundle": None,
    "max_queue_records": 1000,
    "max_queue_bytes": 4194304,
    "retry_max_attempts": 3,
    "active_delivery_seconds": 75,
    "maximum_residence_seconds": 900,
    "max_throttle_responses": 3,
    "max_active_run_age": None,
    "closure_reserve_records": 50,
    "closure_reserve_bytes": 3145728,
    "provider_timeout": 60,
    "indicator_allowlist": None,
}
_METHODS = (
    "close",
    "emit",
    "flush",
    "release_run",
    "resume_auth",
    "resume_deployment",
    "resume_endpoint",
    "resume_schema",
    "submit_evaluation_failure",
    "submit_measurement_health",
)
_DISPOSITIONS = {
    "QUEUED": "queued",
    "SENT": "sent",
    "COMMITTED": "committed",
    "DUPLICATE": "duplicate",
    "RETRY_SCHEDULED": "retry_scheduled",
    "RATE_LIMITED": "rate_limited",
    "AUTH_PAUSED": "auth_paused",
    "SCHEMA_PAUSED": "schema_paused",
    "DEPLOYMENT_UNAVAILABLE": "deployment_unavailable",
    "ENDPOINT_PAUSED": "endpoint_paused",
    "CONFIGURATION_FAILED": "configuration_failed",
    "RETRY_EXHAUSTED": "retry_exhausted",
    "PERMANENTLY_FAILED": "permanently_failed",
    "INDETERMINATE": "indeterminate",
    "OVERFLOWED": "overflowed",
    "CANCELLED": "cancelled",
}
_SNAPSHOT_FIELDS = (
    "queue_depth",
    "high_water_mark",
    "counts_by_disposition",
    "oldest_queued_age",
    "recent_records",
    "pause_reason",
    "resume_not_before",
    "active_binding_count",
    "oldest_binding_age",
    "unclassified_422_count",
    "closure_reserve_rejections",
    "late_response_discarded",
    "late_credential_result_discarded",
    "provider_call_outstanding",
    "exhausted_may_have_committed",
    "terminal_tombstone_count",
    "tombstones_evicted",
    "sink_state",
)
_RECORD_FIELDS = ("event_id", "disposition", "error_code", "may_have_committed")


def test_module_exports_are_the_documented_entry_points() -> None:
    assert sink_module.__all__ == [
        "AsyncHTTPEventSink",
        "ConfigurationError",
        "ConfigurationFailedError",
        "DeliveryDisposition",
        "DeliveryRecordStatus",
        "DeliveryStatusSnapshot",
        "EventDeliveryRejected",
        "ExporterClosed",
        "HTTPEventSink",
    ]


@pytest.mark.parametrize("cls", ["HTTPEventSink", "AsyncHTTPEventSink"])
def test_constructor_is_keyword_only_with_the_documented_names_and_defaults(
    cls: str,
) -> None:
    parameters = {
        name: parameter
        for name, parameter in inspect.signature(
            getattr(sink_module, cls).__init__
        ).parameters.items()
        if name not in ("self", "_transport")  # _transport is an internal test seam
    }
    assert tuple(parameters) == _CONSTRUCTOR
    assert all(p.kind is inspect.Parameter.KEYWORD_ONLY for p in parameters.values())
    for name, default in _DEFAULTS.items():
        assert parameters[name].default == default, name
    for name in ("endpoint", "credential_provider", "deployment_id", "expected_agent"):
        assert parameters[name].default is inspect.Parameter.empty, name


@pytest.mark.parametrize("cls", ["HTTPEventSink", "AsyncHTTPEventSink"])
def test_public_methods_and_status_property(cls: str) -> None:
    sink_class = getattr(sink_module, cls)
    public = tuple(
        sorted(
            name
            for name in dir(sink_class)
            if not name.startswith("_") and callable(getattr(sink_class, name))
        )
    )
    assert public == _METHODS
    assert isinstance(inspect.getattr_static(sink_class, "status"), property)


def test_delivery_disposition_values_are_stable_strings() -> None:
    assert issubclass(sink_module.DeliveryDisposition, enum.Enum)
    assert {m.name: m.value for m in sink_module.DeliveryDisposition} == _DISPOSITIONS


def test_status_snapshot_and_record_fields() -> None:
    assert dataclasses.is_dataclass(sink_module.DeliveryStatusSnapshot)
    assert (
        tuple(f.name for f in dataclasses.fields(sink_module.DeliveryStatusSnapshot))
        == _SNAPSHOT_FIELDS
    )
    assert (
        tuple(f.name for f in dataclasses.fields(sink_module.DeliveryRecordStatus))
        == _RECORD_FIELDS
    )


def test_local_exceptions_form_the_documented_hierarchy() -> None:
    assert issubclass(sink_module.ConfigurationError, Exception)
    assert issubclass(sink_module.EventDeliveryRejected, Exception)
    assert issubclass(
        sink_module.ConfigurationFailedError, sink_module.EventDeliveryRejected
    )
    assert issubclass(sink_module.ExporterClosed, sink_module.EventDeliveryRejected)
    assert not issubclass(
        sink_module.ConfigurationError, sink_module.EventDeliveryRejected
    )


def test_optional_health_capability_is_a_protocol_with_the_documented_methods() -> None:
    capability = ports.HealthEvidenceSink
    methods = {
        name: tuple(inspect.signature(getattr(capability, name)).parameters)
        for name in (
            "release_run",
            "submit_evaluation_failure",
            "submit_measurement_health",
        )
    }
    assert methods == {
        "release_run": ("self", "run_id"),
        "submit_evaluation_failure": (
            "self",
            "failure",
            "run_id",
            "indicator",
            "evaluation_id",
            "occurred_at",
        ),
        "submit_measurement_health": (
            "self",
            "report",
            "run_id",
            "measurement_id",
            "observed_at",
        ),
    }
