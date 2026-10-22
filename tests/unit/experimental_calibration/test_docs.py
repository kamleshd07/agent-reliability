"""The calibration documents exist, link to real files, and quote the code's numbers."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from agent_reliability.experimental.calibration import CalibrationPolicy
from agent_reliability.experimental.calibration.dataset import (
    MAX_CASES_PER_SPLIT,
    MAX_DATASET_BYTES,
    MAX_LINE_BYTES,
    MAX_MANIFEST_BYTES,
    MAX_SPLIT_BYTES,
)

pytestmark = pytest.mark.unit

DOCS = Path(__file__).resolve().parents[3] / "docs" / "p29-calibration"
LINK = re.compile(r"\]\((?!https?://|#)([^)#\s]+)(?:#[^)]*)?\)")


def _pages() -> list[Path]:
    return sorted(DOCS.glob("*.md"))


def test_the_expected_documents_exist() -> None:
    names = {p.name for p in _pages()}
    assert {
        "README.md", "ARCHITECTURE.md", "DATASET_SCHEMA.md", "PROVENANCE_SPEC.md",
        "SECURITY_AND_PRIVACY.md", "PERFORMANCE.md", "PLATFORM_PROPOSAL.md",
        "GAP_ASSESSMENT.md",
    } <= names  # fmt: skip


@pytest.mark.parametrize("page", _pages(), ids=lambda p: p.name)
def test_relative_links_resolve(page: Path) -> None:
    for target in LINK.findall(page.read_text(encoding="utf-8")):
        assert (page.parent / target).resolve().exists(), f"{page.name} -> {target}"


def test_the_preset_numbers_in_the_architecture_match_the_code() -> None:
    text = (DOCS / "ARCHITECTURE.md").read_text(encoding="utf-8")
    p = CalibrationPolicy.starting_point()
    for needle in (
        f"min_examples {p.min_examples}",
        f"min_per_class {p.min_per_class}",
        f"min_adversarial_fail {p.min_adversarial_fail}",
        f"`max_fnr` {p.max_fnr:.2f}",
        f"`max_fpr` {p.max_fpr:.2f}",
        f"validity {p.validity_days} days",
        f"dataset age {p.max_dataset_age_days} days",
    ):
        assert needle in text, needle


def test_the_documented_limits_match_the_code() -> None:
    text = (DOCS / "DATASET_SCHEMA.md").read_text(encoding="utf-8")
    assert f"manifest {MAX_MANIFEST_BYTES // 1024} KiB" in text
    assert f"{MAX_SPLIT_BYTES // (1024 * 1024)} MiB per split file" in text
    assert f"{MAX_DATASET_BYTES // (1024 * 1024)} MiB per dataset" in text
    assert f"{MAX_CASES_PER_SPLIT:,}".replace(",", " ") in text
    assert f"{MAX_LINE_BYTES // 1024} KiB per" in text


def test_no_document_claims_production_accuracy_or_readiness() -> None:
    forbidden = re.compile(
        r"\b(production[- ]ready|customer[- ]ready|is accurate|guarantees? accuracy)\b",
        re.I,
    )
    for page in _pages():
        for line in page.read_text(encoding="utf-8").split("\n\n"):
            if forbidden.search(line):
                lowered = line.lower()
                assert any(
                    w in lowered for w in ("not", "no ", "never", "without", "non-goal")
                ), (
                    page.name,
                    line,
                )


def test_internal_reports_are_excluded_from_the_sdist() -> None:
    import tomllib

    project = tomllib.loads(
        (DOCS.parents[1] / "pyproject.toml").read_text(encoding="utf-8")
    )
    excluded = set(project["tool"]["hatch"]["build"]["targets"]["sdist"]["exclude"])
    for internal in (
        "GAP_ASSESSMENT.md", "PLATFORM_PROPOSAL.md", "TRACEABILITY_MATRIX.md",
        "COMPATIBILITY_REPORT.md", "GO_NO_GO.md", "OWNER_DECISIONS_S4.md",
        "FUTURE_CALIBRATION_PLAN.md",
    ):  # fmt: skip
        assert f"/docs/p29-calibration/{internal}" in excluded
    assert "/docs/p29-calibration/reviews" in excluded
