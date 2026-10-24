"""Public-repository hygiene: no machine paths, private references or relocated records.

Documentation and fixtures in this repository are public. These checks keep personal
machine paths, private-repository names and internal governance records that were moved
to a private archive out of the tracked tree, and keep secret-shaped literals to the
documented example form. They never print a matched value.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TEXT_SUFFIXES = {".py", ".md", ".txt", ".json", ".toml", ".yml", ".yaml", ".sha256", ""}
HOME_PATH = re.compile(r"/(?:Users|home)/([A-Za-z0-9._<>*-]+)")
GENERIC_HOME_NAMES = {"ubuntu", "runner", "user", "name", "<user>", "<name>"}
PRIVATE_REPO = re.compile("agent-reliability-" + "plat" + "form")
AWS_SHAPED = re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")
AWS_DOCUMENTED_EXAMPLE = "AKIAIOSFODNN7EXAMPLE"
# Immutable historical baseline documents (byte-identical checks) are exempt from the
# private-repository rule; they are the subject of a separate disposition.
BASELINE_PROTECTED = re.compile(r"^docs/(P28_|P29_|p29-calibration/|p30/)")


def _tracked_text_files() -> list[Path]:
    names = subprocess.run(
        ["git", "ls-files"], cwd=ROOT, check=True, capture_output=True, text=True
    ).stdout.splitlines()
    return [
        ROOT / n
        for n in names
        if (ROOT / n).suffix in TEXT_SUFFIXES and (ROOT / n).is_file()
    ]


FILES = _tracked_text_files()


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def test_no_personal_home_path_is_tracked() -> None:
    offenders = []
    for path in FILES:
        for match in HOME_PATH.finditer(_read(path)):
            if match.group(1).lower() not in GENERIC_HOME_NAMES and match.group(
                1
            ) not in {"..."}:
                offenders.append(str(path.relative_to(ROOT)))
                break
    assert offenders == []


def test_private_repository_name_is_not_referenced_outside_protected_history() -> None:
    offenders = [
        str(p.relative_to(ROOT))
        for p in FILES
        if not BASELINE_PROTECTED.match(str(p.relative_to(ROOT)))
        and PRIVATE_REPO.search(_read(p))
    ]
    # This test file itself builds the name from pieces, so it is not listed.
    assert offenders == []


def test_relocated_governance_records_stay_out_of_the_tree() -> None:
    manifest = json.loads(
        (
            ROOT / "tests/fixtures/documentation/relocated-governance-records.json"
        ).read_text()
    )["records"]
    assert len(manifest) >= 20
    assert [name for name in manifest if (ROOT / name).exists()] == []


def test_aws_shaped_literals_are_the_documented_example_only() -> None:
    offenders = [
        str(path.relative_to(ROOT))
        for path in FILES
        if any(
            m.group(0) != AWS_DOCUMENTED_EXAMPLE
            for m in AWS_SHAPED.finditer(_read(path))
        )
    ]
    assert offenders == []
