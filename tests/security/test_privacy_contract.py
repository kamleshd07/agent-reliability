"""Adversarial privacy checks for public failure values and diagnostics."""

from __future__ import annotations

import logging

import pytest

from agent_reliability.sdk import LoggingDiagnosticHandler, SdkDiagnostic

SECRET = "SECRET_DO_NOT_LEAK_M7_49821"


def test_diagnostic_repr_does_not_render_exception_message() -> None:
    diagnostic = SdkDiagnostic(
        component="sdk",
        operation="start",
        run_id=None,
        exception=RuntimeError(SECRET),
    )
    assert SECRET not in repr(diagnostic)
    assert diagnostic.exception.args == (SECRET,)


def test_default_diagnostic_log_contains_structure_not_secret(
    caplog: pytest.LogCaptureFixture,
) -> None:
    diagnostic = SdkDiagnostic(
        component="sdk",
        operation="start",
        run_id=None,
        exception=RuntimeError(SECRET),
    )
    with caplog.at_level(logging.WARNING, logger="agent_reliability.sdk"):
        LoggingDiagnosticHandler().handle(diagnostic)
    assert SECRET not in caplog.text
    assert "RuntimeError" in caplog.text
