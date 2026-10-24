# ruff: noqa: E501 -- long explanatory strings stay readable as sentences.
"""Command line entry point.

Language: Python.

    python run_evaluation.py                          # replay recorded model responses
    python run_evaluation.py --output-dir out         # also write report.json / report.md
    python run_evaluation.py --case Q05               # reproduce one case
    python run_evaluation.py --mode live --record     # re-run against a local Ollama model
"""

from __future__ import annotations

import argparse
import datetime
import json
import platform
import sys
from importlib import metadata
from pathlib import Path
from typing import Any

if __package__ in (None, ""):  # executed as a script: make the package importable
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from smolagents_text_to_sql_evaluation import harness
    from smolagents_text_to_sql_evaluation.report import to_json, to_markdown, to_text
else:
    from . import harness
    from .report import to_json, to_markdown, to_text


def _live_factory(model_id: str, api_base: str) -> Any:
    def make() -> Any:
        from smolagents import OpenAIServerModel

        return OpenAIServerModel(
            model_id=model_id,
            api_base=api_base,
            api_key="ollama",  # Ollama ignores the key; no real credential is used
            temperature=0,
            seed=0,
        )

    return make


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("replay", "live"), default="replay")
    parser.add_argument(
        "--tag", default=harness.DEFAULT_MODEL_TAG, help="transcript name"
    )
    parser.add_argument("--model-id", default="qwen2.5-coder:7b")
    parser.add_argument("--api-base", default="http://localhost:11434/v1")
    parser.add_argument(
        "--record", action="store_true", help="live mode: write transcripts/<tag>.json"
    )
    parser.add_argument("--case", help="run only this case id (for example Q05)")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument(
        "--format", choices=("text", "json", "markdown"), default="text"
    )
    args = parser.parse_args(argv)

    data = harness.load_cases()
    cases = data["cases"]
    if args.case:
        cases = [c for c in cases if c["id"] == args.case]
        if not cases:
            parser.error(f"no case matches {args.case!r}")
    if args.record and args.mode != "live":
        parser.error("--record needs --mode live")

    factory = (
        _live_factory(args.model_id, args.api_base) if args.mode == "live" else None
    )
    runs = harness.run_cases(
        cases,
        data["tolerance"],
        mode=args.mode,
        tag=args.tag,
        live_model_factory=factory,
    )
    if args.mode == "replay":
        meta = harness.load_transcript(args.tag)["meta"]
    else:
        meta = {
            "model_id": args.model_id,
            "runtime": "ollama (local, OpenAI-compatible endpoint)",
            "temperature": 0,
            "seed": 0,
            "max_steps": harness.MAX_STEPS,
            "smolagents_version": metadata.version("smolagents"),
            "openai_version": metadata.version("openai"),
            "agent_reliability_version": metadata.version("agent-reliability"),
            "python": platform.python_version(),
            "platform": platform.platform(),
            "recorded_at": datetime.date.today().isoformat(),
        }
    if args.record:
        transcript = {
            "meta": meta,
            "cases": {
                r.case["id"]: {
                    "steps": r.recorded_steps,
                    "duration_seconds": round(r.duration_seconds or 0.0, 3),
                    "live_state": r.agent_state,
                    "live_answer": r.answer,
                }
                for r in runs
            },
        }
        harness.TRANSCRIPT_DIR.mkdir(exist_ok=True)
        (harness.TRANSCRIPT_DIR / f"{args.tag}.json").write_text(
            json.dumps(transcript, indent=1, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )
    analysis = harness.analyse(runs, meta, harness.load_adjudication(args.tag))
    if args.output_dir is not None:
        args.output_dir.mkdir(parents=True, exist_ok=True)
        (args.output_dir / "report.json").write_text(
            to_json(analysis), encoding="utf-8", newline="\n"
        )
        (args.output_dir / "report.md").write_text(
            to_markdown(analysis), encoding="utf-8", newline="\n"
        )
    renderers = {"text": to_text, "json": to_json, "markdown": to_markdown}
    sys.stdout.write(renderers[args.format](analysis))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
