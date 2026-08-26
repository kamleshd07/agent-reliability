"""Contracts for package-index-safe links in the root README."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.contract

ROOT = Path(__file__).resolve().parents[2]
INLINE_TARGET = re.compile(r"!?\[[^\]]*\]\(\s*(?P<target><[^>]+>|[^)\s]+)")
REFERENCE_TARGET = re.compile(
    r"^\s*\[[^\]]+\]:\s*(?P<target><[^>]+>|\S+)", re.MULTILINE
)
SAFE_PREFIXES = ("#", "https://", "http://", "mailto:")


def _readme_targets(readme: str) -> list[str]:
    matches = (*INLINE_TARGET.finditer(readme), *REFERENCE_TARGET.finditer(readme))
    return [match.group("target").strip("<>") for match in matches]


def _is_package_index_safe(target: str) -> bool:
    return target.startswith(SAFE_PREFIXES)


def test_root_readme_links_are_package_index_safe() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    unsafe = [
        target
        for target in _readme_targets(readme)
        if not _is_package_index_safe(target)
    ]

    assert unsafe == [], f"README contains package-index-relative links: {unsafe}"


@pytest.mark.parametrize("target", ["docs/GUIDE.md", "examples/example.py", "LICENSE"])
def test_repository_relative_targets_are_unsafe(target: str) -> None:
    assert not _is_package_index_safe(target)


@pytest.mark.parametrize(
    "target",
    ["#architecture", "https://example.com/guide", "mailto:security@example.com"],
)
def test_portable_targets_are_safe(target: str) -> None:
    assert _is_package_index_safe(target)
