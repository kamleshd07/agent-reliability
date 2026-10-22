"""The engine revision pins the behaviour that the template digest cannot see."""

from __future__ import annotations

import hashlib
import inspect
import pathlib

import pytest

from agent_reliability.experimental.judge import _engine, core
from agent_reliability.experimental.judge.behaviour import ENGINE_REVISION

pytestmark = pytest.mark.unit

_PINNED_SOURCE_SHA256 = (
    "4589e4f94dc8df7c0da7b1b091e59260e41bb4428e37e29ef95cace0b78fc77b"
)
_PINNED_ENGINE_SHA256 = (
    "21202b98e53a0445489c4b843a958892e438b8b357dd2f00abb1753d1533a851"
)
_PINNED_REVISION = "1"


def test_the_parser_and_mapping_source_is_pinned_to_the_engine_revision() -> None:
    """If this fails you changed how replies are parsed, mapped or aggregated
    over repeats. That changes judge behaviour for existing calibrations: bump
    ``ENGINE_REVISION`` in ``judge/behaviour.py`` and record the new values here."""
    source = "".join(
        inspect.getsource(getattr(core, name))
        for name in (
            "parse_output",
            "interpret_reply",
            "map_verdict",
            "aggregate_repeats",
        )
    )
    digest = hashlib.sha256(source.encode()).hexdigest()
    assert (digest, ENGINE_REVISION) == (_PINNED_SOURCE_SHA256, _PINNED_REVISION)


def test_the_engine_retry_and_repair_logic_is_pinned_to_the_engine_revision() -> None:
    """Same rule for ``_engine.py`` (retries, repair, attempts, deadlines, budgets): any
    edit needs a conscious ``ENGINE_REVISION`` decision and a new pin."""
    path = pathlib.Path(_engine.__file__)
    assert hashlib.sha256(path.read_bytes()).hexdigest() == _PINNED_ENGINE_SHA256
