"""The safeguard record stays honest and its evidence mapping stays real."""

from __future__ import annotations

import importlib.util
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[3]
DOC = (ROOT / "docs/P29_PILOT_SAFEGUARDS.md").read_text(encoding="utf-8")


def _script() -> object:
    spec = importlib.util.spec_from_file_location(
        "p29_sg_evidence", ROOT / "scripts/p29_sg_evidence.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_every_safeguard_is_documented_not_satisfied_with_a_role_and_a_template() -> (
    None
):
    for gate in ("SG-1", "SG-2", "SG-3", "SG-4", "SG-5", "SG-6"):
        row = DOC.split(f"| {gate} |", 1)[1].split("\n", 1)[0]
        assert "NOT SATISFIED" in row, gate
        assert "SATISFIED" not in row.replace("NOT SATISFIED", ""), gate
        assert "owner" in row.lower(), gate  # a responsible role is named
    assert "no person holds any of them" in DOC
    for template in (
        "**A. SG-1",
        "**B. SG-2",
        "**C. SG-3",
        "**D. SG-4",
        "**E. SG-5",
        "**F. SG-6",
    ):
        assert template in DOC


def test_evidence_script_maps_only_existing_tests_for_all_six_safeguards() -> None:
    module = _script()
    mapping = module.SAFEGUARDS  # type: ignore[attr-defined]
    assert set(mapping) == {"SG-1", "SG-2", "SG-3", "SG-4", "SG-5", "SG-6"}
    for nodes in mapping.values():
        assert nodes
        for node in nodes:
            path, _, name = node.partition("::")
            assert f"def {name}(" in (ROOT / path).read_text(encoding="utf-8"), node


def test_no_pilot_or_calibration_claim_is_made() -> None:
    lowered = " ".join(DOC.lower().split())
    assert "no customer pilot has been started" in lowered
    assert "no accuracy or calibration claim" in lowered
