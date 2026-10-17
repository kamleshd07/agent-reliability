"""Record the SDK-side test results mapped to P29 pilot safeguards SG-1..SG-6.

    python scripts/p29_sg_evidence.py --json evidence.json

This evidences only the SDK-side behaviour documented in
docs/P29_PILOT_SAFEGUARDS.md. It does not satisfy any pilot condition (all safeguards
remain NOT SATISFIED until a pilot exists).
"""

from __future__ import annotations

import argparse
import json
import platform
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
J = "tests/unit/experimental_judge"
P4 = f"{J}/test_phase4_measurement_integrity.py"
DOCS = f"{J}/test_s00_s12_docs.py"
SAFEGUARDS: dict[str, list[str]] = {
    "SG-1": [
        f"{P4}::test_budget_exhaustion_is_visible_in_observer_coverage_and_failure_evidence",
        f"{P4}::test_overload_shedding_is_a_failure_with_evidence_never_a_verdict",
        f"{P4}::test_sg1_defaults_are_documented_safe_not_fast_values",
    ],
    "SG-2": [
        f"{P4}::test_one_failure_marks_the_whole_run_unavailable_via_the_recorder",
        f"{DOCS}::test_p29_s11_ac08_ac09_runbook_states_path_limits_and_every_safeguard_status",
    ],
    "SG-3": [
        f"{P4}::test_coverage_report_offers_no_single_healthy_boolean",
        f"{P4}::test_ninety_nine_failures_plus_one_pass_cannot_look_healthy",
        f"{P4}::test_attempted_counts_failures_but_determinate_does_not",
    ],
    "SG-4": [f"{P4}::test_a_separate_scope_and_run_keeps_the_other_run_healthy"],
    "SG-5": [
        f"{J}/test_s05_coordinator.py::"
        "test_p29_s05_ac07_observer_exceptions_are_suppressed_and_counted",
        f"{P4}::test_budget_exhaustion_is_visible_in_observer_coverage_and_failure_evidence",
    ],
    "SG-6": [
        f"{DOCS}::test_p29_s12_ac04_user_docs_carry_privacy_pass_meaning_and_non_claims"
    ],
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", type=Path, help="write the evidence record here")
    arguments = parser.parse_args()
    record: dict[str, object] = {
        "python": platform.python_version(),
        "pilot_status": "ALL SAFEGUARDS NOT SATISFIED (no pilot exists)",
        "safeguards": {},
    }
    failed = False
    for gate, nodes in SAFEGUARDS.items():
        with tempfile.TemporaryDirectory() as directory:
            junit = Path(directory) / "junit.xml"
            subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pytest",
                    "-q",
                    "-p",
                    "no:cacheprovider",
                    f"--junitxml={junit}",
                    *nodes,
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            root = ET.parse(junit).getroot() if junit.exists() else None
        results = []
        for case in root.iter("testcase") if root is not None else []:
            outcome = (
                "failed"
                if case.find("failure") is not None or case.find("error") is not None
                else "skipped"
                if case.find("skipped") is not None
                else "passed"
            )
            results.append(
                {
                    "test": f"{case.get('classname')}::{case.get('name')}",
                    "outcome": outcome,
                }
            )
        failed = failed or not results or any(r["outcome"] != "passed" for r in results)
        record["safeguards"][gate] = {  # type: ignore[index]
            "sdk_side_results": results,
            "pilot_condition": "NOT SATISFIED",
        }
    text = json.dumps(record, indent=2) + "\n"
    if arguments.json:
        arguments.json.write_text(text)
    else:
        sys.stdout.write(text)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
