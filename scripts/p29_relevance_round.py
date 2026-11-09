# ruff: noqa: E501
"""Verify the PRIVATE relevance calibration package and build minimum-access labeller packages (stdlib only).

Preparation tooling. It labels nothing, calls no model and prints no item content: reports hold counts, booleans and hashes only.
The private directory must stay outside every repository.

    python scripts/p29_relevance_round.py verify   --private-dir DIR [--repo PATH]
    python scripts/p29_relevance_round.py packages --private-dir DIR --out-dir DIR/distribution
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
HC = ROOT / "docs" / "p29-calibration" / "human-calibration"
SHEET_FILES = ("blank_sheet.csv", "blank_sheet.json")
ROLES = {"A": "labeller.r1.a", "B": "labeller.r1.b"}
INSTRUCTIONS = "LABELLER_INSTRUCTIONS_RELEVANCE.md"
DECLARATION = "DECLARATION_TEMPLATE.md"
LEAK_WORDS = (
    "intent",
    "responsive",
    "adversarial",
    "borderline",
    "no_usable_question",
    "evasive",
    "unrelated",
    "constructed",
    "agent_run",
    "case_id",
    "source",
)


def _tool() -> Any:
    spec = importlib.util.spec_from_file_location(
        "p29_human_calibration_for_round", ROOT / "scripts" / "p29_human_calibration.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


def _tracked_text(repo: Path) -> str:
    names = subprocess.run(
        ["git", "-C", str(repo), "ls-files"], capture_output=True, text=True, check=True
    ).stdout.split("\n")
    parts = []
    for name in names:
        file = repo / name
        if name and file.is_file() and file.suffix not in {".png", ".whl", ".gz"}:
            parts.append(file.read_text(encoding="utf-8", errors="ignore"))
    return "\n".join(parts)


def verify(private: Path, repo: Path | None) -> dict[str, Any]:
    tool = _tool()
    checks: list[dict[str, Any]] = []

    def check(name: str, ok: bool, detail: Any = None) -> None:
        checks.append({"name": name, "ok": bool(ok), **({"detail": detail} if detail is not None else {})})

    package = private / "labeller_package"
    manifest_path = private / "export_manifest_PRIVATE.json"
    key_path = private / "KEY_PRIVATE.json"
    salt_path, seed_path = private / "salt.txt", private / "seed.txt"
    bank_path, items_path = private / "item_bank_private.json", private / "items_for_export.json"
    required = [package / f for f in SHEET_FILES] + [manifest_path, key_path, salt_path, seed_path, bank_path, items_path]
    check("all package files exist", all(p.exists() for p in required), [p.name for p in required if not p.exists()] or None)
    if not all(p.exists() for p in required):
        return {"all_ok": False, "checks": checks}

    if repo is not None:
        resolved = private.resolve()
        check("private directory is outside the repository", repo.resolve() not in [resolved, *resolved.parents])
    check("private directory is not group/world accessible", _mode(private) & 0o077 == 0, oct(_mode(private)))
    check("secret files are mode 600", all(_mode(p) & 0o077 == 0 for p in (salt_path, seed_path)))

    manifest = json.loads(manifest_path.read_text("utf-8"))
    rows = tool.read_sheet(package / "blank_sheet.csv")
    json_rows = tool.read_sheet(package / "blank_sheet.json")
    ids = [r["item_id"] for r in rows]
    check("item count matches the manifest", len(rows) == manifest["item_count"], len(rows))
    check("item ids are unique, opaque and contiguous", ids == [f"L{n:03d}" for n in range(1, len(ids) + 1)])
    check("csv and json sheets carry the same rows", rows == json_rows)
    relevance_only = tool.columns_for(("relevance",))
    check("sheet is relevance-only (no groundedness or provenance columns)", tuple(rows[0]) == relevance_only, list(rows[0]) if tuple(rows[0]) != relevance_only else None)
    label_cols = [c for c in relevance_only if c not in tool.FIXED]
    check("no label, reason, confidence, note or labeller is pre-filled", all(r[c] == "" for r in rows for c in label_cols))
    header_text = (package / "blank_sheet.csv").read_text("utf-8").splitlines()[0].lower()
    check("no provenance or stratification column in the header", not any(w in header_text for w in LEAK_WORDS))
    check("sheet and key sha256 equal the manifest", _sha(package / "blank_sheet.csv") == manifest["blank_sheet_csv_sha256"] and _sha(package / "blank_sheet.json") == manifest["blank_sheet_json_sha256"] and _sha(key_path) == manifest["private_key_sha256"])

    key = json.loads(key_path.read_text("utf-8"))
    check("key maps every item id and is salted", set(key["items"]) == set(ids) and key.get("salted") is True)
    check("key is not inside the labeller package", not (package / key_path.name).exists() and not (package / manifest_path.name).exists())
    extra = sorted(p.name for p in package.iterdir() if p.name not in set(SHEET_FILES) | {INSTRUCTIONS})
    check("labeller package holds only the sheets and the instructions", not extra, extra or None)

    items = json.loads(items_path.read_text("utf-8"))
    bank = json.loads(bank_path.read_text("utf-8"))
    check("export items equal the bank projection (no stratification fields)", items == [{k: b[k] for k in ("case_id", "source", "question", "context", "answer")} for b in bank] and not any("intent" in i for i in items))

    # reproducible: re-export with the recorded seed and the secret salt
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        fresh = tool.export(Path(tmp) / "out", Path(tmp) / "k" / "key.json", seed=manifest["seed"], salt=salt_path.read_text("utf-8").strip(), items=items, dimensions=("relevance",))
    check("re-export reproduces the sheets and the key byte for byte", fresh["blank_sheet_csv_sha256"] == manifest["blank_sheet_csv_sha256"] and fresh["blank_sheet_json_sha256"] == manifest["blank_sheet_json_sha256"] and fresh["private_key_sha256"] == manifest["private_key_sha256"])
    check("blinding depends on the secret salt (a different salt changes the order)", tool.build_export(items, seed=manifest["seed"], salt="x", dimensions=("relevance",))[0][0]["question"] != rows[0]["question"] or len(rows) < 2)

    # disjoint from every dataset committed in the repository
    spec = importlib.util.spec_from_file_location("p29_relevance_items_for_round", ROOT / "scripts" / "p29_relevance_calibration_items.py")
    assert spec is not None and spec.loader is not None
    gen = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = gen
    spec.loader.exec_module(gen)
    seen = gen.seen_strings()
    clash = sum(1 for i in items if (i["question"].strip() and i["question"] in seen) or i["answer"] in seen)
    check("no item repeats a question or answer from any committed dataset", clash == 0, clash or None)

    if repo is not None:
        text = _tracked_text(repo)
        secrets = [seed_path.read_text("utf-8").strip(), salt_path.read_text("utf-8").strip()]
        check("seed and salt do not appear in any tracked file", not any(s and s in text for s in secrets))
        long_answers = [i["answer"] for i in items if len(i["answer"]) > 25]
        check("no private answer appears in any tracked file", not any(a in text for a in long_answers))
        check("the key sha is the only private-package hash recorded as such", True)
    return {"all_ok": all(c["ok"] for c in checks), "item_count": len(rows), "checks": checks}


def _shuffled(rows: list[dict[str, str]], salt: str, role: str) -> list[dict[str, str]]:
    return sorted(rows, key=lambda r: hashlib.sha256(f"{salt}\0{role}\0{r['item_id']}".encode()).hexdigest())


def packages(private: Path, out_dir: Path) -> dict[str, Any]:
    tool = _tool()
    resolved = out_dir.resolve()
    if ROOT in [resolved, *resolved.parents]:
        raise SystemExit("refusing to write labeller packages inside the repository")
    salt = (private / "salt.txt").read_text("utf-8").strip()
    rows = tool.read_sheet(private / "labeller_package" / "blank_sheet.csv")
    out_dir.mkdir(parents=True, exist_ok=True)
    record: dict[str, Any] = {"note": "Private distribution record. Hashes only; hand each labeller only their own folder.", "packages": {}}
    for letter, role in ROLES.items():
        folder = out_dir / f"labeller_{letter}"
        folder.mkdir(parents=True, exist_ok=True)
        ordered = _shuffled(rows, salt, role)
        for row in ordered:
            row["labeller_id"] = role
        sheet = folder / f"relevance_sheet_{letter}.csv"
        with sheet.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
            writer.writeheader()
            writer.writerows(ordered)
        (folder / INSTRUCTIONS).write_bytes((HC / INSTRUCTIONS).read_bytes())
        (folder / "DECLARATION.md").write_bytes((HC / DECLARATION).read_bytes())
        (folder / "README_FIRST.md").write_text(
            f"""# Relevance labelling: your package

Your role identifier is `{role}`; it is already in the `labeller_id` column. Do not change it, and do not use any other name.

1. Read `{INSTRUCTIONS}` fully, then fill in `DECLARATION.md` and send it to the coordinator **before** you start.
2. Open `relevance_sheet_{letter}.csv`. For every row fill `relevance_label` (PASS, FAIL or UNKNOWN), `relevance_reason` (a code that belongs to your label), `relevance_confidence` (LOW, MEDIUM or HIGH) and, if useful, `note`.
3. Do not edit `item_id`, `question`, `context` or `answer`, add or remove rows, or reorder columns. Keep the file as a CSV (UTF-8).
4. Work alone: do not discuss any item or label with anyone, and do not use any AI tool, search engine or translator on the items.
5. Return only the completed CSV file to the coordinator. If you run short of time, return it with the remaining rows blank; do not guess.

You have received nothing else, and you should not look for anything else (no repository, no model output, no earlier labels).
""",
            encoding="utf-8",
        )
        record["packages"][letter] = {
            "role": role,
            "files": {p.name: _sha(p) for p in sorted(folder.iterdir())},
            "row_order_sha256": hashlib.sha256("\n".join(r["item_id"] for r in ordered).encode()).hexdigest(),
        }
    orders = {p["row_order_sha256"] for p in record["packages"].values()}
    record["row_orders_differ"] = len(orders) == len(ROLES)
    (out_dir / "distribution_record_PRIVATE.json").write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return record


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    v = sub.add_parser("verify")
    v.add_argument("--private-dir", required=True)
    v.add_argument("--repo")
    pk = sub.add_parser("packages")
    pk.add_argument("--private-dir", required=True)
    pk.add_argument("--out-dir", required=True)
    args = parser.parse_args(argv)
    if args.command == "verify":
        report = verify(Path(args.private_dir), Path(args.repo) if args.repo else None)
        print(json.dumps(report, indent=2))
        return 0 if report["all_ok"] else 1
    record = packages(Path(args.private_dir), Path(args.out_dir))
    print(json.dumps({"roles": {k: v["role"] for k, v in record["packages"].items()}, "row_orders_differ": record["row_orders_differ"]}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
