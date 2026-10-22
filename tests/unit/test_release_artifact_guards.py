"""The release-artifact guards must reject what they claim to reject (planted cases).

Offending strings are assembled from pieces so that this file itself never trips the
guards when it ships in the source distribution.
"""

from __future__ import annotations

import importlib.util
import io
import tarfile
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PREFIX = "agent_reliability-0.0.0/"
KEY_BLOCK = ("-----BEGIN " + "PRIVATE" + " KEY-----\nabc\n").encode()
PGP_BLOCK = ("-----BEGIN PGP " + "PRIVATE" + " KEY BLOCK-----\nabc\n").encode()
UNIX_PATH = ("see /Us" + "ers/someone/project").encode()
VAR_PATH = ("tmp at /var/fol" + "ders/ab/cd/T").encode()
TMP_PATH = ("log at /private" + "/tmp/session/out").encode()
HOME_PATH = ("config in /ho" + "me/someone/.cfg").encode()
WIN_PATH = ("C:\\Us" + "ers\\Someone\\proj").encode()
WIN_JSON = ("c:\\\\us" + "ers\\\\someone").encode()
WIN_SLASH = ("C:/Us" + "ers/Someone").encode()


def _guards():  # type: ignore[no-untyped-def]
    spec = importlib.util.spec_from_file_location(
        "verify_release_artifacts", ROOT / "scripts/verify_release_artifacts.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _wheel(path: Path, members: dict[str, bytes]) -> Path:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("agent_reliability/__init__.py", b"")
        for name, data in members.items():
            archive.writestr(name, data)
    return path


def _sdist(path: Path, members: dict[str, bytes]) -> Path:
    with tarfile.open(path, "w:gz") as archive:
        for name, data in {"pyproject.toml": b"", **members}.items():
            info = tarfile.TarInfo(PREFIX + name)
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))
    return path


@pytest.fixture
def clean(tmp_path: Path) -> tuple[Path, Path]:
    return _wheel(tmp_path / "c.whl", {}), _sdist(
        tmp_path / "c.tar.gz", {"README.md": b"x"}
    )


def test_clean_artifacts_pass_every_guard(clean: tuple[Path, Path]) -> None:
    guards = _guards()
    guards._assert_no_private_keys(*clean)
    guards._assert_no_local_paths(*clean)
    guards._assert_no_internal_files(
        {"agent_reliability/a.py"}, {PREFIX + "README.md"}, PREFIX
    )


@pytest.mark.parametrize("data", [KEY_BLOCK, PGP_BLOCK])
@pytest.mark.parametrize("target", ["wheel", "sdist"])
def test_private_key_blocks_are_rejected(
    tmp_path: Path, data: bytes, target: str
) -> None:
    wheel = _wheel(
        tmp_path / "w.whl",
        {"agent_reliability/x.txt": data} if target == "wheel" else {},
    )
    sdist = _sdist(
        tmp_path / "s.tar.gz", {"docs/x.txt": data} if target == "sdist" else {}
    )
    with pytest.raises(AssertionError, match="private key"):
        _guards()._assert_no_private_keys(wheel, sdist)


@pytest.mark.parametrize("name", ["tests/x.key", "tests/x.PEM", "a/b.pfx"])
def test_key_file_names_are_rejected(tmp_path: Path, name: str) -> None:
    sdist = _sdist(tmp_path / "s.tar.gz", {name: b"zz"})
    with pytest.raises(AssertionError, match="private key"):
        _guards()._assert_no_private_keys(_wheel(tmp_path / "w.whl", {}), sdist)


@pytest.mark.parametrize(
    "data", [UNIX_PATH, VAR_PATH, TMP_PATH, HOME_PATH, WIN_PATH, WIN_JSON, WIN_SLASH]
)
@pytest.mark.parametrize("target", ["wheel", "sdist"])
def test_local_developer_paths_are_rejected(
    tmp_path: Path, data: bytes, target: str
) -> None:
    wheel = _wheel(
        tmp_path / "w.whl",
        {"agent_reliability/x.txt": data} if target == "wheel" else {},
    )
    sdist = _sdist(
        tmp_path / "s.tar.gz", {"docs/x.md": data} if target == "sdist" else {}
    )
    with pytest.raises(AssertionError, match="local developer paths"):
        _guards()._assert_no_local_paths(wheel, sdist)


@pytest.mark.parametrize(
    "name",
    [
        "CLAUDE.md",
        "AGENTS.md",
        "docs/sub/CLAUDE.md",
        "docs/evidence/x.txt",
        "docs/P28_SOMETHING.md",
        "docs/P99_NEW_INTERNAL_REPORT.md",
        "docs/P29_ANY_OTHER_REPORT.md",
    ],
)
def test_internal_files_are_rejected_in_the_sdist(name: str) -> None:
    with pytest.raises(AssertionError, match="internal files"):
        _guards()._assert_no_internal_files(set(), {PREFIX + name}, PREFIX)


@pytest.mark.parametrize(
    "name", ["docs/x.md", "tests/x.py", "CLAUDE.md", "pkg/AGENTS.md"]
)
def test_internal_or_repository_only_files_are_rejected_in_the_wheel(name: str) -> None:
    with pytest.raises(AssertionError, match="internal files"):
        _guards()._assert_no_internal_files({name}, set(), PREFIX)


def test_the_public_milestone_documents_are_allowed() -> None:
    _guards()._assert_no_internal_files(
        set(),
        {
            PREFIX + "docs/P29_PILOT_REPORT_TEMPLATE.json",
            PREFIX + "docs/P29_PILOT_RUNBOOK.md",
            PREFIX + "docs/P29_PILOT_SAFEGUARDS.md",
        },
        PREFIX,
    )


def test_internal_instrumentation_review_directory_is_rejected() -> None:
    with pytest.raises(AssertionError, match="internal files"):
        _guards()._assert_no_internal_files(
            set(), {PREFIX + "docs/p30/reviews/report.md"}, PREFIX
        )
