# ruff: noqa: E501
"""Tests for scripts/p29_relevance_round.py. All data is built in a temp directory; no real private material is used."""

from __future__ import annotations

import csv
import importlib.util
import json
import os
import subprocess
from pathlib import Path
from typing import Any

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[3]


def _load(name: str) -> Any:
    spec = importlib.util.spec_from_file_location(
        f"{name}_t", ROOT / "scripts" / f"{name}.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    import sys

    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


R = _load("p29_relevance_round")
T = _load("p29_human_calibration")


def _private_dir(tmp_path: Path, n: int = 12) -> Path:
    private = tmp_path / "private"
    private.mkdir(mode=0o700)
    os.chmod(private, 0o700)
    seed, salt = "seed-" + "a" * 40, "salt-" + "b" * 40
    for name, value in (("seed.txt", seed), ("salt.txt", salt)):
        f = private / name
        f.write_text(value + "\n")
        os.chmod(f, 0o600)
    bank = [
        {
            "case_id": f"RC{i:04d}",
            "source": "constructed",
            "question": f"Zzquestion number {i} about the Qqprivate gadget?",
            "context": [],
            "answer": f"Zzanswer number {i} that is long enough to count as private text.",
            "intent": "responsive",
        }
        for i in range(n)
    ]
    (private / "item_bank_private.json").write_text(json.dumps(bank))
    items = [
        {k: b[k] for k in ("case_id", "source", "question", "context", "answer")}
        for b in bank
    ]
    (private / "items_for_export.json").write_text(json.dumps(items))
    T.export(
        private / "labeller_package",
        private / "KEY_PRIVATE.json",
        seed="round-test",
        salt=salt,
        items=items,
        dimensions=("relevance",),
    )
    (private / "labeller_package" / "export_manifest.json").rename(
        private / "export_manifest_PRIVATE.json"
    )
    (private / "labeller_package" / R.INSTRUCTIONS).write_text("instructions")
    for f in private.rglob("*"):
        if f.is_file():
            os.chmod(f, 0o600)
    return private


def _git_repo(tmp_path: Path, content: str = "nothing private") -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "README.md").write_text(content)
    for cmd in (
        ["init", "-q"],
        ["add", "-A"],
        ["-c", "user.email=a@b.c", "-c", "user.name=t", "commit", "-qm", "x"],
    ):
        subprocess.run(["git", "-C", str(repo), *cmd], check=True, capture_output=True)
    return repo


def _failed(report: dict[str, Any]) -> set[str]:
    return {c["name"] for c in report["checks"] if not c["ok"]}


def test_verify_passes_for_a_complete_blinded_reproducible_package(
    tmp_path: Path,
) -> None:
    private = _private_dir(tmp_path)
    report = R.verify(private, _git_repo(tmp_path))
    assert report["all_ok"], _failed(report)
    assert report["item_count"] == 12


def test_verify_report_contains_no_item_content(tmp_path: Path) -> None:
    private = _private_dir(tmp_path)
    text = json.dumps(R.verify(private, _git_repo(tmp_path)))
    assert (
        "Zzquestion" not in text and "Zzanswer" not in text and "Qqprivate" not in text
    )
    assert "seed-" not in text and "salt-" not in text


def test_verify_detects_a_prefilled_label_and_a_leaking_column(tmp_path: Path) -> None:
    private = _private_dir(tmp_path)
    sheet = private / "labeller_package" / "blank_sheet.csv"
    rows = list(csv.DictReader(sheet.open(newline="")))
    rows[0]["relevance_label"] = "PASS"
    with sheet.open("w", newline="") as handle:
        w = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    failed = _failed(R.verify(private, None))
    assert "no label, reason, confidence, note or labeller is pre-filled" in failed
    assert (
        "sheet and key sha256 equal the manifest" in failed
    )  # edited sheet no longer matches


def test_verify_detects_extra_files_in_the_labeller_package(tmp_path: Path) -> None:
    private = _private_dir(tmp_path)
    (private / "labeller_package" / "KEY_PRIVATE.json").write_text("{}")
    assert "key is not inside the labeller package" in _failed(R.verify(private, None))


def test_verify_detects_secrets_and_private_text_in_the_repository(
    tmp_path: Path,
) -> None:
    private = _private_dir(tmp_path)
    leaked = (
        "seed-"
        + "a" * 40
        + " and Zzanswer number 3 that is long enough to count as private text."
    )
    failed = _failed(R.verify(private, _git_repo(tmp_path, leaked)))
    assert "seed and salt do not appear in any tracked file" in failed
    assert "no private answer appears in any tracked file" in failed


def test_verify_refuses_a_private_directory_inside_the_repository(
    tmp_path: Path,
) -> None:
    import shutil

    repo = _git_repo(tmp_path)
    private = shutil.copytree(_private_dir(tmp_path), repo / "p")
    assert "private directory is outside the repository" in _failed(
        R.verify(private, repo)
    )


def test_verify_detects_loose_permissions(tmp_path: Path) -> None:
    private = _private_dir(tmp_path)
    os.chmod(private / "salt.txt", 0o644)
    assert "no private file is group/world accessible" in _failed(
        R.verify(private, None)
    )


def test_verify_detects_a_changed_item_bank_projection(tmp_path: Path) -> None:
    private = _private_dir(tmp_path)
    items = json.loads((private / "items_for_export.json").read_text())
    items[0]["answer"] = "tampered"
    (private / "items_for_export.json").write_text(json.dumps(items))
    failed = _failed(R.verify(private, None))
    assert "export items equal the bank projection (no stratification fields)" in failed
    assert "re-export reproduces the sheets and the key byte for byte" in failed


def test_packages_are_minimum_access_with_distinct_roles_and_orders(
    tmp_path: Path,
) -> None:
    private = _private_dir(tmp_path, n=30)
    out = tmp_path / "dist"
    record = R.packages(private, out)
    assert {p["role"] for p in record["packages"].values()} == {
        "labeller.r1.a",
        "labeller.r1.b",
    }
    assert record["row_orders_differ"] is True
    names = {p.name for p in (out / "labeller_A").iterdir()}
    assert names == {
        "relevance_sheet_A.csv",
        R.INSTRUCTIONS,
        "DECLARATION.md",
        "README_FIRST.md",
    }
    for letter, other in (("A", "labeller.r1.b"), ("B", "labeller.r1.a")):
        text = "".join(p.read_text() for p in (out / f"labeller_{letter}").iterdir())
        for forbidden in (
            "KEY_PRIVATE",
            "seed-",
            "salt-",
            "intent",
            "case_id",
            "RC00",
            other,
        ):
            assert forbidden not in text, (letter, forbidden)
    a_text = (out / "labeller_A" / "README_FIRST.md").read_text()
    assert "labeller.r1.a" in a_text and "labeller.r1.b" not in a_text
    b_sheet = (out / "labeller_B" / "relevance_sheet_B.csv").read_text()
    assert "labeller.r1.a" not in b_sheet


def test_packaged_sheets_validate_against_the_common_blank_sheet(
    tmp_path: Path,
) -> None:
    private = _private_dir(tmp_path, n=30)
    out = tmp_path / "dist"
    R.packages(private, out)
    blank = T.read_sheet(private / "labeller_package" / "blank_sheet.csv")
    for letter in ("A", "B"):
        rows = T.read_sheet(
            out / f"labeller_{letter}" / f"relevance_sheet_{letter}.csv"
        )
        assert {r["item_id"] for r in rows} == {r["item_id"] for r in blank}
        # unfilled: validation must refuse it (labels are blank); it must never pass as complete
        _, errors = T.validate_sheet(rows, blank)
        assert any("relevance_label missing" in e for e in errors)
        assert all(r["labeller_id"] == f"labeller.r1.{letter.lower()}" for r in rows)


def test_packages_refuse_to_write_inside_the_repository(tmp_path: Path) -> None:
    private = _private_dir(tmp_path)
    with pytest.raises(SystemExit):
        R.packages(private, ROOT / "docs" / "should-not-exist")


def test_labeller_declaration_has_no_adjudicator_or_model_wording(
    tmp_path: Path,
) -> None:
    private = _private_dir(tmp_path, n=30)
    out = tmp_path / "dist"
    R.packages(private, out)
    for letter in ("A", "B"):
        text = (out / f"labeller_{letter}" / "DECLARATION.md").read_text()
        for forbidden in (
            "Adjudicator only",
            "adjudicat",
            "Qwen",
            "agreement figures",
            "judge being calibrated",
            "model verdict" if False else "Qwen3",
        ):
            assert forbidden.lower() not in text.lower(), forbidden
        assert "I confirm that my answers" in text and "Conflict-of-interest" in text
    # the real template is stripped the same way
    real = R._labeller_declaration((R.HC / R.DECLARATION).read_text())
    assert "Qwen" not in real and "adjudicat" not in real.lower()


def test_verify_without_repo_is_not_ok(tmp_path: Path) -> None:
    report = R.verify(_private_dir(tmp_path), None)
    assert report["all_ok"] is False
    assert "repository leak scan was performed (--repo given)" in _failed(report)


def test_verify_scans_repository_history_not_only_the_working_tree(
    tmp_path: Path,
) -> None:
    private = _private_dir(tmp_path)
    repo = _git_repo(
        tmp_path, "salt-" + "b" * 40
    )  # committed, then removed from the tree
    (repo / "README.md").write_text("clean now")
    for cmd in (
        ["add", "-A"],
        ["-c", "user.email=a@b.c", "-c", "user.name=t", "commit", "-qm", "y"],
    ):
        subprocess.run(["git", "-C", str(repo), *cmd], check=True, capture_output=True)
    failed = _failed(R.verify(private, repo))
    assert "seed and salt do not appear in any tracked file" not in failed
    assert "seed and salt do not appear anywhere in the repository history" in failed


def test_export_with_private_items_refuses_a_git_work_tree_and_bad_dimensions(
    tmp_path: Path,
) -> None:
    repo = _git_repo(tmp_path)
    items = [
        {
            "case_id": "c",
            "source": "constructed",
            "question": "q",
            "context": [],
            "answer": "a",
        }
    ]
    with pytest.raises(T.ToolError, match="git work tree"):
        T.export(
            repo / "out",
            tmp_path / "k" / "key.json",
            items=items,
            dimensions=("relevance",),
        )
    with pytest.raises(T.ToolError, match="git work tree"):
        T.export(
            tmp_path / "out", repo / "key.json", items=items, dimensions=("relevance",)
        )
    with pytest.raises(T.ToolError, match="dimensions"):
        T.export(
            tmp_path / "o2",
            tmp_path / "k2" / "key.json",
            items=items,
            dimensions=("bogus",),
        )


def test_packages_are_written_owner_only(tmp_path: Path) -> None:
    private = _private_dir(tmp_path, n=30)
    out = tmp_path / "dist"
    R.packages(private, out)
    for path in [out, *out.rglob("*")]:
        assert R._mode(path) & 0o077 == 0, path.name
