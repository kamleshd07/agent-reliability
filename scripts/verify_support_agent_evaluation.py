"""Run the support-agent evaluation against an INSTALLED wheel in a clean environment.

Language: Python. Creates a throw-away virtual environment, installs only the built
wheel (no dependencies, no network, no index), copies the example folder to an
unrelated directory, runs it there and requires its reports to equal the committed
expected reports byte for byte. Proves the example does not depend on the source
checkout, on undocumented local files or on the network.

    python scripts/verify_support_agent_evaluation.py [path/to/agent_reliability-*.whl]
"""

from __future__ import annotations

import filecmp
import shutil
import subprocess
import sys
import tempfile
import venv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "support_agent_evaluation"


def main(argv: list[str]) -> int:
    wheels = [Path(a) for a in argv] or sorted((ROOT / "dist").glob("*.whl"))
    if len(wheels) != 1:
        print("expected exactly one wheel (build with: python -m build)")
        return 2
    with tempfile.TemporaryDirectory(prefix="support-agent-eval-") as work_name:
        work = Path(work_name)
        environment = work / "venv"
        venv.EnvBuilder(with_pip=True, clear=True).create(environment)
        python = environment / "bin" / "python"
        if not python.exists():  # Windows layout
            python = environment / "Scripts" / "python.exe"
        subprocess.run(
            [
                str(python),
                "-m",
                "pip",
                "install",
                "--quiet",
                "--no-deps",
                "--no-index",
                str(wheels[0]),
            ],
            check=True,
        )
        copy = work / "elsewhere" / "support_agent_evaluation"
        shutil.copytree(EXAMPLE, copy, ignore=shutil.ignore_patterns("__pycache__"))
        out = work / "out"
        subprocess.run(
            [
                str(python),
                "-I",
                str(copy / "run_evaluation.py"),
                "--output-dir",
                str(out),
            ],
            cwd=work,
            check=True,
            capture_output=True,
        )
        for name in ("report.json", "report.md"):
            if not filecmp.cmp(out / name, EXAMPLE / "expected" / name, shallow=False):
                print(f"MISMATCH: {name} differs from expected/{name}")
                return 1
    print("support-agent evaluation: installed wheel reproduces the expected reports")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
