"""Hygiene checks for the public external-evaluation documents.

These documents are written for people outside the project, so they must not
carry internal tracking identifiers, private repository names, local paths,
e-mail addresses or secret-shaped strings, and every relative link must resolve.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
DOCS = [
    ROOT / "docs" / "EXTERNAL_EVALUATION.md",
    ROOT / "docs" / "external-evaluation" / "FEEDBACK_TEMPLATE.md",
    ROOT / "docs" / "external-evaluation" / "EVALUATION_CHECKLIST.md",
]
FORBIDDEN = {
    "roadmap or decision id": re.compile(
        r"\b(?:RM-[A-Z]+-\d+|D-S\d+|S\d+[A-Z]?-OD-\d+)\b"
    ),
    "private platform repository": re.compile(
        r"agent-reliability-" + "plat" + "form", re.I
    ),
    "local path": re.compile(r"/(?:Users|home)/[A-Za-z0-9._-]+|[A-Za-z]:\\Users\\"),
    "e-mail address": re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"),
    "secret-shaped value": re.compile(
        r"AKIA[0-9A-Z]{16}|gh[pousr]_[A-Za-z0-9]{20,}|sk-[A-Za-z0-9]{20,}"
        r"|-{5}BEGIN [A-Z ]*PRIV"
        r"ATE KE"
        r"Y-{5}|eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"
    ),
    "internal gate language": re.compile(
        r"\b(?:NO-GO|design[- ]partner|Phase B)\b", re.I
    ),
}
LINK = re.compile(r"\]\(([^)#\s]+)(?:#[^)]*)?\)")


@pytest.mark.parametrize("path", DOCS, ids=lambda p: p.name)
def test_public_doc_has_no_internal_or_sensitive_content(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    for label, pattern in FORBIDDEN.items():
        assert pattern.search(text) is None, f"{path.name}: {label}"


@pytest.mark.parametrize(
    "path",
    [*DOCS, ROOT / "examples" / "support_agent_evaluation" / "README.md"],
    ids=lambda p: p.name,
)
def test_relative_links_resolve(path: Path) -> None:
    for target in LINK.findall(path.read_text(encoding="utf-8")):
        if "://" in target or target.startswith("mailto:"):
            continue
        assert (path.parent / target).exists(), f"{path.name}: broken link {target}"


def test_guide_documents_private_security_reporting_and_synthetic_label() -> None:
    text = DOCS[0].read_text(encoding="utf-8")
    assert "Report a vulnerability" in text
    assert "synthetic validation" in text.lower()


def test_guide_snippet_runs_and_prints_the_documented_output() -> None:
    text = DOCS[0].read_text(encoding="utf-8")
    code = re.search(r"```python\n(.*?)```", text, re.S)
    expected = re.search(r"```text\n(Indicator:.*?)```", text, re.S)
    assert code is not None and expected is not None
    done = subprocess.run(
        [sys.executable, "-I", "-c", code.group(1)],
        capture_output=True,
        text=True,
        check=True,
        timeout=60,
    )
    assert done.stdout.strip() == expected.group(1).strip()
