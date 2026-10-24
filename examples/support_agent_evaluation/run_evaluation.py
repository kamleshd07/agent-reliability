"""Command line entry point.

Language: Python.

    python run_evaluation.py                    # both versions, console summary
    python run_evaluation.py --output-dir out   # also write report.json/report.md
    python run_evaluation.py --version v1 --case S01   # reproduce one failure
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

if __package__ in (None, ""):  # executed as a script: make the package importable
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from support_agent_evaluation.harness import VERSIONS, analyse, load_data
    from support_agent_evaluation.report import to_json, to_markdown, to_text
else:
    from .harness import VERSIONS, analyse, load_data
    from .report import to_json, to_markdown, to_text


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", choices=(*VERSIONS, "both"), default="both")
    parser.add_argument("--case", help="run only this case id (for example S01)")
    parser.add_argument(
        "--output-dir", type=Path, help="write report.json and report.md here"
    )
    parser.add_argument(
        "--format", choices=("text", "json", "markdown"), default="text"
    )
    args = parser.parse_args(argv)

    knowledge, cases = load_data()
    versions = VERSIONS if args.version == "both" else (args.version,)
    analysis = analyse(cases, knowledge, versions, args.case)
    if args.output_dir is not None:
        args.output_dir.mkdir(parents=True, exist_ok=True)
        (args.output_dir / "report.json").write_text(
            to_json(analysis), encoding="utf-8"
        )
        (args.output_dir / "report.md").write_text(
            to_markdown(analysis), encoding="utf-8"
        )
    renderers = {"text": to_text, "json": to_json, "markdown": to_markdown}
    sys.stdout.write(renderers[args.format](analysis))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
