# ruff: noqa: E501 -- long strings and narrative lines read best unbroken.
"""Human-labelling and calibration preparation tooling for the P29 semantic evaluation (stdlib only).

PREPARATION ONLY. This tool exports a blind sheet, validates and compares sheets that humans have filled in, and merges adjudicated
labels into the shipped calibration dataset format. It performs no labelling, calls no model, reads no network or environment, and
invents no data: every label that reaches a dataset must come from a supplied sheet.

    python scripts/p29_human_calibration.py export    --out-dir DIR --key-out PRIVATE_KEY.json [--seed S] [--salt-file F]
    python scripts/p29_human_calibration.py validate  --blank DIR/blank_sheet.json --sheet FILLED.(csv|json)
    python scripts/p29_human_calibration.py agreement --blank B --sheet-a A --sheet-b B [--adjudication-template OUT.csv]
    python scripts/p29_human_calibration.py merge     --blank B --sheet-a A --sheet-b B --adjudication ADJ.csv --key KEY.json
                                                      --split heldout --dataset-id ID --dataset-version V --created-at ISO
                                                      --license L --confirmed-thresholds-sha256 H --out-dir OUT

The key file maps opaque item ids back to golden-set case ids. It must be withheld from labellers (docs/p29-calibration/human-calibration).
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import random
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
HERE_DOCS = ROOT / "docs" / "p29-calibration" / "human-calibration"
DEFAULT_THRESHOLDS = HERE_DOCS / "PREDECLARED_THRESHOLDS.json"

SHEET_SCHEMA = "p29-human-calibration-sheet/1"
KEY_SCHEMA = "p29-human-calibration-key/1"
DEFAULT_SEED = "p29-human-calibration-blind-v1"
DIMENSIONS = ("groundedness", "relevance")
LABELS = ("PASS", "FAIL", "UNKNOWN")
CONFIDENCE = ("LOW", "MEDIUM", "HIGH")
# Rubric vocabulary (judge-groundedness@2026-10.r1, judge-answer-relevance@2026-11.r1), restricted to codes a human can use, plus one
# labeller-only code for "this dimension cannot be applied to this answer". A test pins these against the shipped rubric files.
REASONS: dict[str, dict[str, tuple[str, ...]]] = {
    "groundedness": {
        "PASS": ("supported_by_context",),
        "FAIL": ("unsupported_claim", "contradicted_by_context"),
        "UNKNOWN": (
            "context_insufficient",
            "low_confidence",
            "dimension_not_applicable",
        ),
    },
    "relevance": {
        "PASS": ("addresses_question",),
        "FAIL": ("off_topic", "evasive_or_non_answer"),
        "UNKNOWN": ("question_missing", "low_confidence", "dimension_not_applicable"),
    },
}
RUBRICS = {
    "groundedness": {
        "rubric_id": "judge-groundedness",
        "rubric_version": "2026-10.r1",
        "dimension": "groundedness",
    },
    "relevance": {
        "rubric_id": "judge-answer-relevance",
        "rubric_version": "2026-11.r1",
        "dimension": "answer-relevance",
    },
}
FIXED = ("item_id", "question", "context", "answer")
LABEL_COLUMNS = (
    "groundedness_label",
    "groundedness_reason",
    "groundedness_confidence",
    "relevance_label",
    "relevance_reason",
    "relevance_confidence",
    "note",
    "labeller_id",
)
COLUMNS = FIXED + LABEL_COLUMNS
NOTE_COLUMNS = ("note", "labeller_id")
#: Labeller-only reason (owner-approved for the labelling tooling only). It is never an SDK verdict, is never mapped to UNKNOWN in a
#: merged dataset, and items settled as not applicable are excluded from class-level counts and reported separately.
NOT_APPLICABLE = "dimension_not_applicable"
MIN_PER_CLASS = 30  # PREDECLARED_THRESHOLDS.json adjudicated_set.min_cases_per_class_for_any_calibration_claim


def columns_for(dimensions: tuple[str, ...]) -> tuple[str, ...]:
    """Sheet columns for a round that labels only ``dimensions`` (default: both)."""
    labels = tuple(
        f"{d}_{part}" for d in dimensions for part in ("label", "reason", "confidence")
    )
    return FIXED + labels + NOTE_COLUMNS


def dimensions_of(row: dict[str, Any]) -> tuple[str, ...]:
    """The dimensions a sheet row carries, in canonical order."""
    return tuple(d for d in DIMENSIONS if f"{d}_label" in row)


ADJ_COLUMNS = (
    "item_id",
    "dimension",
    "question",
    "context",
    "answer",
    "labeller_a_label",
    "labeller_a_reason",
    "labeller_b_label",
    "labeller_b_reason",
    "adjudicated_label",
    "adjudicated_reason",
    "rationale",
    "adjudicator_id",
)
ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
PLACEHOLDER_WORDS = (
    "example",
    "placeholder",
    "synthetic",
    "sample",
    "dummy",
    "todo",
    "tbd",
    "fake",
    "test",
    "xxx",
    "changeme",
)
MAX_NOTE = 2000
PROVENANCE_ORDER = ("synthetic", "human_single", "human_multi", "human_adjudicated")


class ToolError(ValueError):
    """A refusal. Messages name rules and item ids, never labelled content."""


# ------------------------------------------------------------------ helpers


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def is_placeholder(identifier: str) -> bool:
    low = identifier.strip().lower()
    return not low or any(word in low for word in PLACEHOLDER_WORDS)


def canonical_json(document: Any) -> bytes:
    return json.dumps(
        document, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def thresholds_digest(document: dict[str, Any]) -> str:
    """SHA-256 over the canonical JSON of the thresholds, excluding the digest member itself."""
    body = {k: v for k, v in document.items() if k != "thresholds_sha256"}
    return _sha256_bytes(canonical_json(body))


def load_thresholds(path: Path = DEFAULT_THRESHOLDS) -> dict[str, Any]:
    document = json.loads(Path(path).read_text(encoding="utf-8"))
    if document.get("thresholds_sha256") != thresholds_digest(document):
        raise ToolError("thresholds file does not match its recorded thresholds_sha256")
    return document


def wilson(successes: int, total: int) -> tuple[float, float] | None:
    """95% Wilson score interval."""
    if total <= 0:
        return None
    z2 = 1.959963984540054**2
    p = successes / total
    denom = 1 + z2 / total
    centre = (p + z2 / (2 * total)) / denom
    half = (
        1.959963984540054 * math.sqrt(p * (1 - p) / total + z2 / (4 * total**2)) / denom
    )
    return max(0.0, centre - half), min(1.0, centre + half)


# ------------------------------------------------------------------- export


def golden_items() -> list[dict[str, Any]]:
    """The golden set's content fields and provenance. Labels, corrections and difficulty are deliberately not read."""
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from examples.semantic_shopping_evaluation.golden import cases

    return [
        {
            "case_id": c["case_id"],
            "source": c["source"],
            "question": c["question"],
            "context": list(c["context"]),
            "answer": c["answer"],
        }
        for c in cases()
    ]


def _context_text(blocks: list[str]) -> str:
    return "\n\n".join(f"[{i}] {b}" for i, b in enumerate(blocks, start=1))


def build_export(
    items: list[dict[str, Any]],
    *,
    seed: str = DEFAULT_SEED,
    salt: str = "",
    dimensions: tuple[str, ...] = DIMENSIONS,
) -> tuple[list[dict[str, str]], dict[str, Any]]:
    """Deterministic blind rows plus the private key document. Order and ids depend only on seed, salt and case id."""
    if len({i["case_id"] for i in items}) != len(items):
        raise ToolError("duplicate case ids in the source set")

    def rank(item: dict[str, Any]) -> str:
        return _sha256_bytes(f"{seed}\0{salt}\0{item['case_id']}".encode())

    ordered = sorted(items, key=rank)
    rows: list[dict[str, str]] = []
    mapping: dict[str, dict[str, str]] = {}
    for index, item in enumerate(ordered, start=1):
        item_id = f"L{index:03d}"
        row = dict.fromkeys(columns_for(dimensions), "")
        row.update(
            item_id=item_id,
            question=item["question"],
            context=_context_text(item["context"]),
            answer=item["answer"],
        )
        rows.append(row)
        mapping[item_id] = {"case_id": item["case_id"], "source": item["source"]}
    key = {
        "schema": KEY_SCHEMA,
        "WITHHOLD_FROM_LABELLERS": (
            "This file reveals which items are real agent runs and which are constructed. Give it only to the person who "
            "merges adjudicated labels, after all labelling and adjudication is finished."
        ),
        "seed": seed,
        "salted": bool(salt),
        "items": mapping,
    }
    return rows, key


def render_csv(
    rows: list[dict[str, str]], columns: tuple[str, ...] | None = None
) -> str:
    import io

    if columns is None:
        columns = tuple(rows[0]) if rows else COLUMNS

    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=list(columns), lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue()


def render_json(rows: list[dict[str, str]]) -> str:
    dimensions = dimensions_of(rows[0]) if rows else DIMENSIONS
    document = {
        "schema": SHEET_SCHEMA,
        "allowed": {
            "label": list(LABELS),
            "confidence": list(CONFIDENCE),
            "reason": {
                d: {k: list(v) for k, v in REASONS[d].items()} for d in dimensions
            },
        },
        "rows": rows,
    }
    return json.dumps(document, indent=2, ensure_ascii=False) + "\n"


def export(
    out_dir: Path,
    key_out: Path,
    *,
    seed: str = DEFAULT_SEED,
    salt: str = "",
    items: list[dict[str, Any]] | None = None,
    dimensions: tuple[str, ...] = DIMENSIONS,
) -> dict[str, str]:
    out_dir, key_out = Path(out_dir), Path(key_out)
    if key_out.resolve().parent == out_dir.resolve():
        raise ToolError(
            "write the private key outside the directory that holds the sheet"
        )
    rows, key = build_export(
        golden_items() if items is None else items,
        seed=seed,
        salt=salt,
        dimensions=dimensions,
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    key_out.parent.mkdir(parents=True, exist_ok=True)
    csv_bytes = render_csv(rows).encode("utf-8")
    json_bytes = render_json(rows).encode("utf-8")
    key_bytes = (json.dumps(key, indent=2, sort_keys=True) + "\n").encode("utf-8")
    (out_dir / "blank_sheet.csv").write_bytes(csv_bytes)
    (out_dir / "blank_sheet.json").write_bytes(json_bytes)
    key_out.write_bytes(key_bytes)
    manifest = {
        "schema": "p29-human-calibration-export-manifest/1",
        "note": (
            "Preparation artefact. Contains no labels. Do not give this file to labellers: it records the shuffle seed."
        ),
        "seed": seed,
        "salted": bool(salt),
        "item_count": len(rows),
        "blank_sheet_csv_sha256": _sha256_bytes(csv_bytes),
        "blank_sheet_json_sha256": _sha256_bytes(json_bytes),
        "private_key_sha256": _sha256_bytes(key_bytes),
    }
    (out_dir / "export_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return {k: v for k, v in manifest.items() if k.endswith("sha256")}


# ------------------------------------------------------------ reading sheets


def read_sheet(path: Path) -> list[dict[str, str]]:
    path = Path(path)
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        document = json.loads(text)
        if not isinstance(document, dict) or document.get("schema") != SHEET_SCHEMA:
            raise ToolError("sheet JSON has the wrong schema")
        rows = document.get("rows")
        if not isinstance(rows, list):
            raise ToolError("sheet JSON has no rows list")
        return rows
    if path.suffix.lower() == ".csv":
        import io

        reader = csv.DictReader(io.StringIO(text, newline=""))
        allowed = {COLUMNS, columns_for(("relevance",)), columns_for(("groundedness",))}
        if reader.fieldnames is None or tuple(reader.fieldnames) not in allowed:
            raise ToolError("sheet CSV header does not match the expected columns")
        return [dict(r) for r in reader]
    raise ToolError("sheet must be .csv or .json")


def validate_sheet(
    rows: list[Any],
    blank_rows: list[dict[str, str]],
    *,
    allow_example: bool = False,
) -> tuple[list[dict[str, str]], list[str]]:
    """Return (normalised rows, errors). Errors name columns and item ids only."""
    errors: list[str] = []
    blank = {r["item_id"]: r for r in blank_rows}
    dimensions = dimensions_of(blank_rows[0]) if blank_rows else DIMENSIONS
    columns = columns_for(dimensions)
    seen: set[str] = set()
    normalised: list[dict[str, str]] = []
    labeller_ids: set[str] = set()
    for position, raw in enumerate(rows, start=1):
        if not isinstance(raw, dict) or set(raw) != set(columns):
            errors.append(f"row {position}: columns do not match the schema")
            continue
        row = {k: ("" if raw[k] is None else str(raw[k])) for k in columns}
        item_id = row["item_id"].strip()
        if item_id not in blank:
            errors.append(f"row {position}: unknown item_id")
            continue
        if item_id in seen:
            errors.append(f"{item_id}: duplicate item_id")
            continue
        seen.add(item_id)
        for column in FIXED:
            if row[column] != blank[item_id][column]:
                errors.append(f"{item_id}: {column} differs from the blank sheet")
        for dimension in dimensions:
            label = row[f"{dimension}_label"].strip().upper()
            reason = row[f"{dimension}_reason"].strip()
            confidence = row[f"{dimension}_confidence"].strip().upper()
            if label not in LABELS:
                errors.append(
                    f"{item_id}: {dimension}_label missing or not one of {'/'.join(LABELS)}"
                )
            elif reason not in REASONS[dimension][label]:
                errors.append(
                    f"{item_id}: {dimension}_reason is not a {label} reason code"
                )
            if confidence not in CONFIDENCE:
                errors.append(f"{item_id}: {dimension}_confidence missing or invalid")
            row[f"{dimension}_label"] = label
            row[f"{dimension}_confidence"] = confidence
            row[f"{dimension}_reason"] = reason
        note = row["note"]
        if len(note) > MAX_NOTE:
            errors.append(f"{item_id}: note is longer than {MAX_NOTE} characters")
        if not allow_example and "SYNTHETIC EXAMPLE" in note.upper():
            errors.append(f"{item_id}: note carries an example marker")
        labeller_ids.add(row["labeller_id"].strip())
        row["labeller_id"] = row["labeller_id"].strip()
        normalised.append(row)
    for missing in sorted(set(blank) - seen):
        errors.append(f"{missing}: missing from the sheet")
    if len(labeller_ids) != 1:
        errors.append("labeller_id must be filled in and identical on every row")
    else:
        lid = next(iter(labeller_ids))
        if not ID_PATTERN.fullmatch(lid):
            errors.append(
                "labeller_id must be a role identifier ([A-Za-z0-9._-], at most 64)"
            )
        elif not allow_example and is_placeholder(lid):
            errors.append("labeller_id is a placeholder or example identifier")
    return normalised, errors


def require_valid(
    path: Path, blank_rows: list[dict[str, str]], *, allow_example: bool = False
) -> list[dict[str, str]]:
    rows, errors = validate_sheet(
        read_sheet(path), blank_rows, allow_example=allow_example
    )
    if errors:
        raise ToolError(
            "sheet is not valid: "
            + "; ".join(errors[:20])
            + (" ..." if len(errors) > 20 else "")
        )
    return rows


# ---------------------------------------------------------------- agreement


def cohens_kappa(a: list[str], b: list[str]) -> float | None:
    n = len(a)
    if n == 0 or n != len(b):
        return None
    po = sum(x == y for x, y in zip(a, b, strict=True)) / n
    pe = sum((a.count(c) / n) * (b.count(c) / n) for c in set(a) | set(b))
    if pe >= 1.0:
        return None
    return (po - pe) / (1 - pe)


def _kappa_analytic_ci(a: list[str], b: list[str]) -> tuple[float, float] | None:
    n = len(a)
    k = cohens_kappa(a, b)
    if k is None:
        return None
    po = sum(x == y for x, y in zip(a, b, strict=True)) / n
    pe = sum((a.count(c) / n) * (b.count(c) / n) for c in set(a) | set(b))
    se = math.sqrt(po * (1 - po) / (n * (1 - pe) ** 2))
    return k - 1.959963984540054 * se, k + 1.959963984540054 * se


def _kappa_bootstrap_ci(
    a: list[str], b: list[str], *, resamples: int, seed: int
) -> dict[str, Any]:
    rng = random.Random(seed)
    n = len(a)
    values: list[float] = []
    undefined = 0
    for _ in range(resamples):
        idx = [rng.randrange(n) for _ in range(n)]
        k = cohens_kappa([a[i] for i in idx], [b[i] for i in idx])
        if k is None:
            undefined += 1
        else:
            values.append(k)
    if not values:
        return {
            "lower": None,
            "upper": None,
            "resamples": resamples,
            "undefined": undefined,
        }
    values.sort()
    lo = values[int(0.025 * (len(values) - 1))]
    hi = values[math.ceil(0.975 * (len(values) - 1))]
    return {"lower": lo, "upper": hi, "resamples": resamples, "undefined": undefined}


def agreement_report(
    rows_a: list[dict[str, str]],
    rows_b: list[dict[str, str]],
    *,
    resamples: int = 2000,
    bootstrap_seed: int = 20261108,
) -> dict[str, Any]:
    by_a = {r["item_id"]: r for r in rows_a}
    by_b = {r["item_id"]: r for r in rows_b}
    if set(by_a) != set(by_b):
        raise ToolError("the two sheets do not cover the same items")
    ids = sorted(by_a)
    report: dict[str, Any] = {
        "items": len(ids),
        "dimensions": {},
        "disagreements": [],
        "applicability_disagreements": [],
    }
    for dimension in dimensions_of(rows_a[0]) if rows_a else DIMENSIONS:
        la = [by_a[i][f"{dimension}_label"] for i in ids]
        lb = [by_b[i][f"{dimension}_label"] for i in ids]
        agree = sum(x == y for x, y in zip(la, lb, strict=True))
        w = wilson(agree, len(ids))
        analytic = _kappa_analytic_ci(la, lb)
        report["dimensions"][dimension] = {
            "n": len(ids),
            "agree": agree,
            "percent_agreement": agree / len(ids) if ids else None,
            "percent_agreement_wilson95": list(w) if w else None,
            "cohens_kappa": cohens_kappa(la, lb),
            "kappa_analytic_ci95": list(analytic) if analytic else None,
            "kappa_bootstrap_ci95": _kappa_bootstrap_ci(
                la, lb, resamples=resamples, seed=bootstrap_seed
            )
            if ids
            else None,
            "label_counts_a": {c: la.count(c) for c in LABELS},
            "label_counts_b": {c: lb.count(c) for c in LABELS},
            "one_labeller_unknown": sum(
                1 for x, y in zip(la, lb, strict=True) if x != y and "UNKNOWN" in (x, y)
            ),
            "not_applicable_counts": {
                "labeller_a": sum(
                    by_a[i][f"{dimension}_reason"] == NOT_APPLICABLE for i in ids
                ),
                "labeller_b": sum(
                    by_b[i][f"{dimension}_reason"] == NOT_APPLICABLE for i in ids
                ),
                "both": sum(
                    by_a[i][f"{dimension}_reason"] == NOT_APPLICABLE
                    and by_b[i][f"{dimension}_reason"] == NOT_APPLICABLE
                    for i in ids
                ),
            },
        }
        for i in ids:
            na_a = by_a[i][f"{dimension}_reason"] == NOT_APPLICABLE
            na_b = by_b[i][f"{dimension}_reason"] == NOT_APPLICABLE
            if (
                na_a != na_b
                and by_a[i][f"{dimension}_label"] == by_b[i][f"{dimension}_label"]
            ):
                # same label, but only one labeller judged the dimension inapplicable
                report["applicability_disagreements"].append(
                    {"item_id": i, "dimension": dimension}
                )
        for i, x, y in zip(ids, la, lb, strict=True):
            if x != y:
                report["disagreements"].append(
                    {
                        "item_id": i,
                        "dimension": dimension,
                        "labeller_a": x,
                        "labeller_b": y,
                    }
                )
    report["disagreement_count"] = len(report["disagreements"])
    return report


def adjudication_template(
    blank_rows: list[dict[str, str]],
    rows_a: list[dict[str, str]],
    rows_b: list[dict[str, str]],
    report: dict[str, Any],
) -> str:
    blank = {r["item_id"]: r for r in blank_rows}
    a = {r["item_id"]: r for r in rows_a}
    b = {r["item_id"]: r for r in rows_b}
    out = []
    for d in [*report["disagreements"], *report["applicability_disagreements"]]:
        i, dim = d["item_id"], d["dimension"]
        out.append(
            {
                "item_id": i,
                "dimension": dim,
                "question": blank[i]["question"],
                "context": blank[i]["context"],
                "answer": blank[i]["answer"],
                "labeller_a_label": a[i][f"{dim}_label"],
                "labeller_a_reason": a[i][f"{dim}_reason"],
                "labeller_b_label": b[i][f"{dim}_label"],
                "labeller_b_reason": b[i][f"{dim}_reason"],
                "adjudicated_label": "",
                "adjudicated_reason": "",
                "rationale": "",
                "adjudicator_id": "",
            }
        )
    return render_csv(out, ADJ_COLUMNS)


def read_adjudication(path: Path) -> list[dict[str, str]]:
    import io

    reader = csv.DictReader(
        io.StringIO(Path(path).read_text(encoding="utf-8"), newline="")
    )
    if reader.fieldnames is None or tuple(reader.fieldnames) != ADJ_COLUMNS:
        raise ToolError("adjudication CSV header does not match the expected columns")
    return [dict(r) for r in reader]


def check_adjudication(
    adjudication: list[dict[str, str]],
    report: dict[str, Any],
    labeller_ids: tuple[str, str],
    *,
    allow_example: bool = False,
) -> dict[tuple[str, str], tuple[str, str]]:
    needed = {
        (d["item_id"], d["dimension"])
        for d in [*report["disagreements"], *report["applicability_disagreements"]]
    }
    decided: dict[tuple[str, str], tuple[str, str]] = {}
    errors: list[str] = []
    adjudicators: set[str] = set()
    for row in adjudication:
        key = (row["item_id"], row["dimension"])
        if key not in needed:
            errors.append(f"{key[0]}/{key[1]}: adjudicated but the labellers agreed")
            continue
        if key in decided:
            errors.append(f"{key[0]}/{key[1]}: duplicate adjudication row")
            continue
        label = row["adjudicated_label"].strip().upper()
        reason = row["adjudicated_reason"].strip()
        if label not in LABELS or reason not in REASONS.get(key[1], {}).get(label, ()):
            errors.append(f"{key[0]}/{key[1]}: adjudicated label or reason invalid")
            continue
        if len(row["rationale"].strip()) < 10:
            errors.append(f"{key[0]}/{key[1]}: rationale is required")
            continue
        adjudicators.add(row["adjudicator_id"].strip())
        decided[key] = (label, reason)
    for key in sorted(needed - set(decided)):
        errors.append(f"{key[0]}/{key[1]}: disagreement has no adjudication")
    if len(adjudicators) != 1:
        errors.append("adjudicator_id must be filled in and identical on every row")
    else:
        adjudicator = next(iter(adjudicators))
        if not ID_PATTERN.fullmatch(adjudicator):
            errors.append("adjudicator_id must be a role identifier")
        elif adjudicator in labeller_ids:
            errors.append(
                "the adjudicator must be a different role from both labellers"
            )
        elif not allow_example and is_placeholder(adjudicator):
            errors.append("adjudicator_id is a placeholder or example identifier")
    if errors:
        raise ToolError("adjudication is not usable: " + "; ".join(errors[:20]))
    return decided


# -------------------------------------------------------------------- merge


def _require_aware(value: str) -> str:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        raise ToolError("created_at must be an ISO-8601 timestamp") from None
    if parsed.tzinfo is None:
        raise ToolError("created_at must carry a UTC offset")
    return value


def merge(
    *,
    blank_rows: list[dict[str, str]],
    sheet_a: Path,
    sheet_b: Path,
    adjudication_path: Path,
    key: dict[str, Any],
    split: str,
    dataset_id: str,
    dataset_version: str,
    created_at: str,
    license_id: str,
    confirmed_thresholds_sha256: str,
    out_dir: Path,
    thresholds_path: Path = DEFAULT_THRESHOLDS,
    _allow_example_labellers: bool = False,  # tests only; not reachable from the command line
) -> dict[str, dict[str, str]]:
    """Refuses unless everything real is present. Never fills a gap."""
    ex = _allow_example_labellers
    thresholds = load_thresholds(thresholds_path)
    if confirmed_thresholds_sha256 != thresholds["thresholds_sha256"]:
        raise ToolError(
            "the owner-confirmed thresholds digest does not match the thresholds file"
        )
    if split not in ("train", "calibration", "heldout"):
        raise ToolError("split must be train, calibration or heldout")
    _require_aware(created_at)
    if key.get("schema") != KEY_SCHEMA or set(key.get("items", {})) != {
        r["item_id"] for r in blank_rows
    }:
        raise ToolError("the private key does not match the blank sheet")
    rows_a = require_valid(sheet_a, blank_rows, allow_example=ex)
    rows_b = require_valid(sheet_b, blank_rows, allow_example=ex)
    id_a, id_b = rows_a[0]["labeller_id"], rows_b[0]["labeller_id"]
    if id_a == id_b:
        raise ToolError(
            "the two sheets carry the same labeller_id; two independent labellers are required"
        )
    report = agreement_report(rows_a, rows_b)
    floor = thresholds["inter_labeller"]
    for dimension, stats in report["dimensions"].items():
        kappa = stats["cohens_kappa"]
        if kappa is None or kappa < floor["min_cohens_kappa_point"]:
            raise ToolError(
                f"{dimension}: Cohen's kappa is below the predeclared floor or undefined; "
                "revise the rubric guidance and relabel, do not relax the floor"
            )
        if stats["percent_agreement"] < floor["min_percent_agreement"]:
            raise ToolError(
                f"{dimension}: percent agreement is below the predeclared floor"
            )
        lower = (stats["kappa_bootstrap_ci95"] or {}).get("lower")
        if lower is None or lower < floor["min_cohens_kappa_bootstrap_ci_lower"]:
            raise ToolError(
                f"{dimension}: the kappa confidence lower bound is below the predeclared floor"
            )
    decided = check_adjudication(
        read_adjudication(adjudication_path), report, (id_a, id_b), allow_example=ex
    )
    by_a = {r["item_id"]: r for r in rows_a}
    by_b = {r["item_id"]: r for r in rows_b}
    out_dir = Path(out_dir)
    result: dict[str, dict[str, str]] = {}
    for dimension in dimensions_of(rows_a[0]):
        docs = []
        provenances = []
        not_applicable_ids: list[str] = []
        for blank in sorted(blank_rows, key=lambda r: r["item_id"]):
            i = blank["item_id"]
            la, lb = by_a[i][f"{dimension}_label"], by_b[i][f"{dimension}_label"]
            adjudicated = (i, dimension) in decided
            final = decided[(i, dimension)][0] if adjudicated else la
            final_reason = (
                decided[(i, dimension)][1]
                if adjudicated
                else by_a[i][f"{dimension}_reason"]
            )
            if final_reason == NOT_APPLICABLE:
                # Not a verdict and not UNKNOWN: left out of the dataset and every class count.
                not_applicable_ids.append(i)
                continue
            parts: list[dict[str, str]] = []
            if blank["question"].strip():
                parts.append({"role": "question", "text": blank["question"]})
            parts.extend(
                {"role": "context", "text": block}
                for block in _split_context(blank["context"])
            )
            parts.append({"role": "answer", "text": blank["answer"]})
            provenance = "human_adjudicated" if adjudicated else "human_multi"
            provenances.append(provenance)
            difficulty = (
                "ambiguous"
                if final == "UNKNOWN"
                else "borderline"
                if adjudicated
                else "clear"
            )
            docs.append(
                {
                    "schema": "gentlity.reference-case/1",
                    "case_id": i,
                    "dimension": RUBRICS[dimension]["dimension"],
                    "parts": parts,
                    "human_label": final.lower(),
                    "difficulty": difficulty,
                    "labels": [
                        {"labeler": id_a, "label": la.lower()},
                        {"labeler": id_b, "label": lb.lower()},
                    ],
                    "label_provenance": provenance,
                    "adjudication": {
                        "method": "third_reviewer" if adjudicated else "none"
                    },
                    "source": key["items"][i]["source"],
                }
            )
        weakest = (
            min(provenances, key=PROVENANCE_ORDER.index)
            if provenances
            else "human_multi"
        )
        class_counts = dict.fromkeys(LABELS, 0)
        for d in docs:
            class_counts[d["human_label"].upper()] += 1
        data = ("\n".join(json.dumps(d, sort_keys=True) for d in docs) + "\n").encode(
            "utf-8"
        )
        target = out_dir / dimension
        target.mkdir(parents=True, exist_ok=True)
        (target / f"{split}.jsonl").write_bytes(data)
        description = (
            "Labels are exactly those recorded in the supplied labeller sheets and adjudication record; none were generated by this tool. "
            "Content is the synthetic shopping golden set."
        )
        if ex:
            description = "SYNTHETIC EXAMPLE (tests only). " + description
        manifest = {
            "schema": "gentlity.reference-dataset/1",
            "dataset_id": dataset_id,
            "dataset_version": dataset_version,
            "created_at": created_at,
            "license": license_id,
            "description": description,
            "rubric": RUBRICS[dimension],
            "splits": {
                split: {
                    "file": f"{split}.jsonl",
                    "sha256": _sha256_bytes(data),
                    "case_count": len(docs),
                    "label_provenance": weakest,
                }
            },
        }
        raw = (json.dumps(manifest, sort_keys=True, indent=2) + "\n").encode("utf-8")
        (target / "manifest.json").write_bytes(raw)
        merge_report = {
            "schema": "p29-human-calibration-merge-report/1",
            "dimension": dimension,
            "applicable_cases": len(docs),
            "class_counts": class_counts,
            "min_cases_per_class": MIN_PER_CLASS,
            "every_class_meets_minimum": all(
                n >= MIN_PER_CLASS for n in class_counts.values()
            ),
            "below_minimum_means": "indicative only; no calibration claim",
            "not_applicable": {
                "reason": NOT_APPLICABLE,
                "count": len(not_applicable_ids),
                "item_ids": not_applicable_ids,
                "note": "Reported separately. Excluded from the dataset and from every class count; never mapped to UNKNOWN or to any SDK verdict.",
            },
        }
        report_raw = (json.dumps(merge_report, sort_keys=True, indent=2) + "\n").encode(
            "utf-8"
        )
        (target / "merge_report.json").write_bytes(report_raw)
        result[dimension] = {
            "manifest": str(target / "manifest.json"),
            "manifest_sha256": _sha256_bytes(raw),
            "merge_report": str(target / "merge_report.json"),
        }
    return result


def _split_context(text: str) -> list[str]:
    blocks = re.split(r"\n\n(?=\[\d+\] )", text)
    return [re.sub(r"^\[\d+\] ", "", b, count=1) for b in blocks if b.strip()]


# ---------------------------------------------------------------------- CLI


def _blank(path: str) -> list[dict[str, str]]:
    return read_sheet(Path(path))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("export")
    p.add_argument("--out-dir", required=True)
    p.add_argument("--key-out", required=True)
    p.add_argument("--seed", default=DEFAULT_SEED)
    p.add_argument(
        "--items-file",
        help="JSON array of source items {case_id, source, question, context[], answer}; default is the golden set",
    )
    p.add_argument(
        "--dimensions",
        default="groundedness,relevance",
        help="comma-separated dimensions the labellers label (default both)",
    )
    p.add_argument(
        "--salt-file",
        help="file holding a secret salt kept by the owner; makes the key non-derivable from the seed",
    )
    p = sub.add_parser("validate")
    p.add_argument("--blank", required=True)
    p.add_argument("--sheet", required=True)
    p = sub.add_parser("agreement")
    p.add_argument("--blank", required=True)
    p.add_argument("--sheet-a", required=True)
    p.add_argument("--sheet-b", required=True)
    p.add_argument("--adjudication-template")
    p = sub.add_parser("merge")
    for name in (
        "blank",
        "sheet-a",
        "sheet-b",
        "adjudication",
        "key",
        "split",
        "dataset-id",
        "dataset-version",
        "created-at",
        "license",
        "confirmed-thresholds-sha256",
        "out-dir",
    ):
        p.add_argument(f"--{name}", required=True)
    p.add_argument("--thresholds", default=str(DEFAULT_THRESHOLDS))
    args = parser.parse_args(argv)
    try:
        if args.command == "export":
            salt = (
                Path(args.salt_file).read_text(encoding="utf-8").strip()
                if args.salt_file
                else ""
            )
            print(
                json.dumps(
                    export(
                        Path(args.out_dir),
                        Path(args.key_out),
                        seed=args.seed,
                        salt=salt,
                        items=(
                            json.loads(Path(args.items_file).read_text("utf-8"))
                            if args.items_file
                            else None
                        ),
                        dimensions=tuple(args.dimensions.split(",")),
                    ),
                    indent=2,
                )
            )
        elif args.command == "validate":
            _, errors = validate_sheet(read_sheet(Path(args.sheet)), _blank(args.blank))
            print(json.dumps({"valid": not errors, "errors": errors}, indent=2))
            return 0 if not errors else 1
        elif args.command == "agreement":
            blank = _blank(args.blank)
            a, b = (
                require_valid(Path(args.sheet_a), blank),
                require_valid(Path(args.sheet_b), blank),
            )
            if a[0]["labeller_id"] == b[0]["labeller_id"]:
                raise ToolError("the two sheets carry the same labeller_id")
            report = agreement_report(a, b)
            if args.adjudication_template:
                Path(args.adjudication_template).write_text(
                    adjudication_template(blank, a, b, report), encoding="utf-8"
                )
            print(json.dumps(report, indent=2))
        else:
            key = json.loads(Path(args.key).read_text(encoding="utf-8"))
            result = merge(
                blank_rows=_blank(args.blank),
                sheet_a=Path(args.sheet_a),
                sheet_b=Path(args.sheet_b),
                adjudication_path=Path(args.adjudication),
                key=key,
                split=args.split,
                dataset_id=args.dataset_id,
                dataset_version=args.dataset_version,
                created_at=args.created_at,
                license_id=args.license,
                confirmed_thresholds_sha256=args.confirmed_thresholds_sha256,
                out_dir=Path(args.out_dir),
                thresholds_path=Path(args.thresholds),
            )
            print(json.dumps(result, indent=2))
    except ToolError as error:
        print(f"refused: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
