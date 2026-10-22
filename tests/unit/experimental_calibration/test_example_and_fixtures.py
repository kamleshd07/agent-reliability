# ruff: noqa: E501 -- long assertion and data lines are kept readable.
"""The offline walkthrough runs deterministically; the committed demo data is reproducible."""

from __future__ import annotations

import filecmp
import hashlib
import importlib.util
import runpy
from pathlib import Path

import pytest

from agent_reliability.experimental.calibration import (
    LabelProvenance,
    Split,
    load_reference_dataset,
)

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[3]
DEMO = ROOT / "tests" / "fixtures" / "p29_calibration" / "demo"
PINNED_MANIFEST_SHA256 = (
    "110dc52d2a85d7ffbf13d2a9519753b4f18cd3645460ca98cd36efe7ad28a174"
)


def _generator():  # type: ignore[no-untyped-def]
    spec = importlib.util.spec_from_file_location(
        "p29_calibration_demo_data", ROOT / "scripts" / "p29_calibration_demo_data.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_committed_demo_data_is_byte_identical_to_its_generator(tmp_path: Path) -> None:
    _generator().build(tmp_path)
    for name in ("manifest.json", "train.jsonl", "calibration.jsonl", "heldout.jsonl"):
        assert filecmp.cmp(DEMO / name, tmp_path / name, shallow=False), name
    assert (
        hashlib.sha256((DEMO / "manifest.json").read_bytes()).hexdigest()
        == PINNED_MANIFEST_SHA256
    )


def test_demo_dataset_is_synthetic_clean_and_labelled_as_such() -> None:
    ds = load_reference_dataset(
        DEMO / "manifest.json", expected_manifest_sha256=PINNED_MANIFEST_SHA256
    )
    assert ds.leakage.clean
    assert all(p is LabelProvenance.SYNTHETIC for p in ds.split_provenance.values())
    assert "SYNTHETIC" in (DEMO / "manifest.json").read_text()
    assert set(ds.splits) == {Split.TRAIN, Split.CALIBRATION, Split.HELDOUT}


def test_the_walkthrough_runs_offline_and_is_deterministic(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    import socket

    def refuse(*args: object, **kwargs: object) -> None:
        raise AssertionError("the walkthrough must not open a network connection")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    outputs = []
    for _ in range(2):
        with pytest.raises(SystemExit) as exit_info:
            runpy.run_path(
                str(ROOT / "examples" / "judge_calibration_offline.py"),
                run_name="__main__",
            )
        assert exit_info.value.code == 0
        outputs.append(capsys.readouterr().out)
    assert outputs[0] == outputs[1]
    text = outputs[0]
    for expected in (
        "status=demonstration  admissible=False",
        "status=uncalibrated  admissible=False",
        "skipped_by_admission",
        "SYNTHETIC",
        "Not production accuracy",
        "borderline stratum : reported only",
    ):
        assert expected in text
    assert "calibrated  admissible=True" not in text
