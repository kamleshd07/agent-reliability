"""Static policy checks for the GitHub Actions workflows (no hosted run is implied).

These pin what the repository controls: pinned actions, least privilege, no secret
use in the pull-request workflow, tag-only release triggers that must come from
`main`, and job time limits. Branch protection, environment approvals and
trusted-publisher settings live in GitHub and cannot be checked here.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

WORKFLOWS = Path(__file__).resolve().parents[2] / ".github" / "workflows"
pytestmark = pytest.mark.skipif(
    not (WORKFLOWS / "ci.yml").is_file(), reason="workflow files are not in the sdist"
)


def _text(name: str) -> str:
    return (WORKFLOWS / name).read_text(encoding="utf-8").replace("\r\n", "\n")


def _jobs(text: str) -> dict[str, str]:
    body = text.split("\njobs:\n", 1)[1]
    parts = re.split(r"^  ([a-z][a-z0-9-]*):\n", body, flags=re.MULTILINE)
    return dict(zip(parts[1::2], parts[2::2], strict=True))


@pytest.mark.parametrize("name", ["ci.yml", "release.yml"])
def test_every_action_is_pinned_to_a_full_commit_sha(name: str) -> None:
    uses = re.findall(r"^\s+(?:- )?uses:\s*(\S+)", _text(name), flags=re.MULTILINE)
    assert uses
    for reference in uses:
        assert re.fullmatch(r"[\w./-]+@[0-9a-f]{40}", reference), reference


def test_ci_is_read_only_and_never_uses_secrets_or_privileged_triggers() -> None:
    text = _text("ci.yml")
    assert re.search(r"^permissions:\n  contents: read\n", text, re.MULTILINE)
    for forbidden in ("secrets.", "pull_request_target", "id-token", "contents: write"):
        assert forbidden not in text, forbidden
    assert "workflow_dispatch" not in text


def test_every_ci_job_has_a_time_limit() -> None:
    for job, body in _jobs(_text("ci.yml")).items():
        assert "timeout-minutes:" in body, job


def test_ci_runs_the_independent_node_reference_without_dependencies() -> None:
    body = _jobs(_text("ci.yml"))["reference-vectors"]
    assert "node scripts/verify_p28_reference.mjs" in body
    assert "npm install" not in body and "npm ci" not in body


def test_ci_covers_all_supported_pythons_and_the_gates() -> None:
    text = _text("ci.yml")
    assert '["3.11", "3.12", "3.13"]' in text
    for step in (
        "ruff check .",
        "ruff format --check .",
        "mypy src",
        "scripts/verify_p28_fixtures.py",
        "pytest --cov",
        "python -m build",
        "scripts/verify_release_artifacts.py",
    ):
        assert step in text, step


def test_release_is_tag_triggered_only_and_must_come_from_main() -> None:
    text = _text("release.yml")
    assert re.search(
        r'^on:\n  push:\n    tags: \["v\*\.\*\.\*"\]\n', text, re.MULTILINE
    )
    assert "workflow_dispatch" not in text and "pull_request" not in text
    assert "fetch-depth: 0" in text
    guard = re.search(
        r'if ! git merge-base --is-ancestor "\$GITHUB_SHA" origin/main; then\n'
        r"\s+echo [^\n]*>&2\n\s+exit 1\n\s+fi\n",
        text,
    )
    assert guard, "ancestry guard must fail the job when the commit is not on main"
    assert "|| true" not in text and "continue-on-error" not in text
    for job, body in _jobs(text).items():
        assert "timeout-minutes:" in body, job
    assert text.index("is-ancestor") < text.index("Install package and build tooling")


def test_release_privileges_are_scoped_to_the_jobs_that_need_them() -> None:
    text = _text("release.yml")
    assert re.search(r"^permissions:\n  contents: read\n", text, re.MULTILINE)
    jobs = _jobs(text)
    assert "id-token: write" not in jobs["build"]
    assert "contents: write" not in jobs["build"]
    assert "id-token: write" in jobs["publish"] and "environment:" in jobs["publish"]
    assert (
        "needs: build" in jobs["publish"] and "needs: publish" in jobs["github-release"]
    )
    assert "contents: write" in jobs["github-release"]
    assert "scripts/verify_release_artifacts.py" in jobs["build"]
