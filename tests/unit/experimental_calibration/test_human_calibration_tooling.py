# ruff: noqa: E501 -- long strings and narrative lines read best unbroken.
"""Tests for scripts/p29_human_calibration.py.

Every labelled sheet here is a SYNTHETIC EXAMPLE built inside the test from a fixed pattern. None of it is, or may be read as, a human
label. The example-labeller escape hatch is a private test-only parameter of ``merge``; the command line cannot reach it.
"""

from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest

from agent_reliability.experimental.calibration import dataset as ds

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[3]
DOC_DIR = ROOT / "docs" / "p29-calibration" / "human-calibration"
PINNED_THRESHOLDS_SHA256 = (
    "31fb3e7a87ae4e287ff68854ba7fe145be76fa7d883cbdec0377057d5c561263"
)


def _tool() -> Any:
    spec = importlib.util.spec_from_file_location(
        "p29_human_calibration_under_test",
        ROOT / "scripts" / "p29_human_calibration.py",
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


T = _tool()


def _golden() -> Any:
    import sys

    sys.path.insert(0, str(ROOT))
    from examples.semantic_shopping_evaluation import golden

    return golden


@pytest.fixture(scope="module")
def export_rows() -> tuple[list[dict[str, str]], dict[str, Any]]:
    return T.build_export(T.golden_items())


# ------------------------------------------------------------ blind export


def test_export_is_deterministic_and_matches_the_committed_blank_sheet(
    tmp_path: Path,
) -> None:
    first = T.export(tmp_path / "a", tmp_path / "k1" / "key.json")
    second = T.export(tmp_path / "b", tmp_path / "k2" / "key.json")
    assert first == second
    for name in ("blank_sheet.csv", "blank_sheet.json", "export_manifest.json"):
        assert (tmp_path / "a" / name).read_bytes() == (
            tmp_path / "b" / name
        ).read_bytes()
        assert (tmp_path / "a" / name).read_bytes() == (
            DOC_DIR / "blank-sheet" / name
        ).read_bytes()


def test_a_different_seed_or_salt_changes_the_order_and_the_key() -> None:
    base, _ = T.build_export(T.golden_items())
    other, _ = T.build_export(T.golden_items(), seed="another-seed")
    salted, key = T.build_export(T.golden_items(), salt="owner-secret")
    assert [r["answer"] for r in base] != [r["answer"] for r in other]
    assert [r["answer"] for r in base] != [r["answer"] for r in salted]
    assert key["salted"] is True and "owner-secret" not in json.dumps(key)


def test_the_key_must_not_be_written_beside_the_sheet(tmp_path: Path) -> None:
    with pytest.raises(T.ToolError):
        T.export(tmp_path, tmp_path / "key.json")


def test_blank_sheet_leaks_no_label_verdict_correction_or_provenance(
    export_rows: tuple[list[dict[str, str]], dict[str, Any]], tmp_path: Path
) -> None:
    rows, _ = export_rows
    golden = _golden()
    T.export(tmp_path / "s", tmp_path / "k" / "key.json")
    text = "\n".join(
        (tmp_path / "s" / n).read_text(encoding="utf-8")
        for n in ("blank_sheet.csv", "blank_sheet.json")
    )
    lowered = text.lower()
    # provenance and assistant-authored material
    for forbidden in (
        "constructed",
        "agent_run",
        "difficulty",
        "correction",
        "ambiguous",
        "verdict",
        "expected",
    ):
        assert forbidden not in lowered, forbidden
    for (_case_id, _), (_, _, why) in golden.CORRECTIONS.items():
        assert why not in text
    for reason in golden.AMBIGUOUS.values():
        assert reason not in text
    # golden case ids and the recorded verdict files
    for case in golden.cases():
        assert f"{case['case_id']}," not in text.replace("\n", ",")
        assert f'"{case["case_id"]}"' not in text
    for verdict_file in (ROOT / "examples/semantic_shopping_evaluation/expected").glob(
        "*.json"
    ):
        doc = json.loads(verdict_file.read_text(encoding="utf-8"))
        for row in doc["rows"][:5]:
            assert row["case_id"] not in {r["item_id"] for r in rows}
    # the only filled columns are the content fields
    for row in rows:
        assert all(row[c] == "" for c in T.LABEL_COLUMNS)
    assert set(rows[0]) == set(T.COLUMNS)


def test_order_and_ids_do_not_reveal_the_source(
    export_rows: tuple[list[dict[str, str]], dict[str, Any]],
) -> None:
    rows, key = export_rows
    sources = [key["items"][r["item_id"]]["source"] for r in rows]
    assert [r["item_id"] for r in rows] == [
        f"L{i:03d}" for i in range(1, len(rows) + 1)
    ]
    assert sources != sorted(sources) and sources != sorted(sources, reverse=True)
    assert len(rows) == 53
    assert all(
        i["case_id"] not in r["item_id"]
        for r, i in zip(rows, key["items"].values(), strict=False)
    )


def test_export_reads_only_content_fields_not_labels() -> None:
    items = T.golden_items()
    assert set(items[0]) == {"case_id", "source", "question", "context", "answer"}


# ------------------------------------------------- thresholds and vocabulary


def test_thresholds_are_pinned_and_self_consistent() -> None:
    doc = json.loads(
        (DOC_DIR / "PREDECLARED_THRESHOLDS.json").read_text(encoding="utf-8")
    )
    assert doc["thresholds_sha256"] == PINNED_THRESHOLDS_SHA256
    assert T.thresholds_digest(doc) == PINNED_THRESHOLDS_SHA256
    assert "PROPOSED" in doc["status"] and "NONE RECORDED" in doc["owner_confirmation"]
    doc["inter_labeller"]["min_cohens_kappa_point"] = 0.5
    assert T.thresholds_digest(doc) != PINNED_THRESHOLDS_SHA256


def test_reason_vocabulary_comes_from_the_shipped_rubrics() -> None:
    rubric_dir = ROOT / "src/agent_reliability/experimental/judge/rubrics"
    for dimension, name in (
        ("groundedness", "judge-groundedness"),
        ("relevance", "judge-answer-relevance"),
    ):
        codes = json.loads((rubric_dir / f"{name}.json").read_text(encoding="utf-8"))[
            "reason_codes"
        ]
        for label, key in (("PASS", "pass"), ("FAIL", "fail"), ("UNKNOWN", "unknown")):
            extra = set(T.REASONS[dimension][label]) - set(codes[key])
            assert extra <= {"dimension_not_applicable"}
        assert T.RUBRICS[dimension]["rubric_id"] == name


# --------------------------------------------------- example sheet builders


def _example_sheet(
    blank: list[dict[str, str]],
    labeller: str,
    *,
    flips: tuple[int, ...] = (),
    note: str = "SYNTHETIC EXAMPLE",
) -> list[dict[str, str]]:
    cycle = ("PASS", "PASS", "FAIL", "UNKNOWN", "PASS", "FAIL")
    out = []
    for index, base in enumerate(blank):
        row = dict(base)
        for shift, dim in enumerate(T.DIMENSIONS):
            label = cycle[(index + shift) % len(cycle)]
            if index in flips and dim == "groundedness":
                label = "FAIL" if label != "FAIL" else "PASS"
            row[f"{dim}_label"] = label
            row[f"{dim}_reason"] = T.REASONS[dim][label][0]
            row[f"{dim}_confidence"] = "MEDIUM"
        row["note"] = note
        row["labeller_id"] = labeller
        out.append(row)
    return out


def _write(path: Path, rows: list[dict[str, str]]) -> Path:
    path.write_text(T.render_csv(rows), encoding="utf-8")
    return path


@pytest.fixture
def blank(
    export_rows: tuple[list[dict[str, str]], dict[str, Any]],
) -> list[dict[str, str]]:
    return export_rows[0]


# --------------------------------------------------------------- validation


def test_a_blank_sheet_is_not_valid(blank: list[dict[str, str]]) -> None:
    _, errors = T.validate_sheet(blank, blank)
    assert any("label missing" in e for e in errors)
    assert any("labeller_id" in e for e in errors)


def test_a_complete_example_sheet_validates_only_with_the_example_allowance(
    blank: list[dict[str, str]],
) -> None:
    sheet = _example_sheet(blank, "example-labeller-a")
    assert T.validate_sheet(sheet, blank, allow_example=True)[1] == []
    errors = T.validate_sheet(sheet, blank)[1]
    assert any("placeholder" in e for e in errors) and any(
        "example marker" in e for e in errors
    )


@pytest.mark.parametrize(
    "mutate,expected",
    [
        (lambda rows: rows.pop(), "missing from the sheet"),
        (lambda rows: rows.append(dict(rows[0])), "duplicate item_id"),
        (lambda rows: rows[0].update(groundedness_label="MAYBE"), "groundedness_label"),
        (
            lambda rows: rows[0].update(relevance_reason="supported_by_context"),
            "relevance_reason",
        ),
        (lambda rows: rows[0].update(relevance_confidence=""), "relevance_confidence"),
        (lambda rows: rows[0].update(answer="edited"), "answer differs"),
        (lambda rows: rows[1].update(labeller_id="role-b"), "identical on every row"),
        (lambda rows: rows[0].update(item_id="L999"), "unknown item_id"),
    ],
)
def test_validation_rejects_malformed_sheets(
    blank: list[dict[str, str]], mutate: Any, expected: str
) -> None:
    sheet = _example_sheet(blank, "example-labeller-a")
    mutate(sheet)
    errors = T.validate_sheet(sheet, blank, allow_example=True)[1]
    assert any(expected in e for e in errors), errors


def test_validation_messages_never_contain_case_content(
    blank: list[dict[str, str]],
) -> None:
    sheet = _example_sheet(blank, "example-labeller-a")
    sheet[0]["answer"] = "edited"
    sheet[1]["groundedness_label"] = "nope"
    for message in T.validate_sheet(sheet, blank, allow_example=True)[1]:
        assert not any(r["answer"] in message for r in blank if len(r["answer"]) > 12)


def test_csv_and_json_round_trip(blank: list[dict[str, str]], tmp_path: Path) -> None:
    sheet = _example_sheet(blank, "example-labeller-a")
    as_csv = _write(tmp_path / "example_sheet.csv", sheet)
    as_json = tmp_path / "example_sheet.json"
    as_json.write_text(T.render_json(sheet), encoding="utf-8")
    assert T.read_sheet(as_csv) == T.read_sheet(as_json)
    (tmp_path / "bad.csv").write_text("a,b\n1,2\n", encoding="utf-8")
    with pytest.raises(T.ToolError):
        T.read_sheet(tmp_path / "bad.csv")


# ---------------------------------------------------------------- agreement


def test_kappa_known_values() -> None:
    assert T.cohens_kappa(list("PPFF"), list("PPFF")) == 1.0
    assert T.cohens_kappa(list("PPPP"), list("PPPP")) is None
    # po = 0.5, pe = 0.5 -> kappa 0
    assert T.cohens_kappa(list("PPFF"), list("PFPF")) == 0.0
    # 2x2 textbook: 20/5/10/15 -> po 0.7, pe 0.5, kappa 0.4
    a = ["Y"] * 25 + ["N"] * 25
    b = ["Y"] * 20 + ["N"] * 5 + ["Y"] * 10 + ["N"] * 15
    assert T.cohens_kappa(a, b) == pytest.approx(0.4)


def test_wilson_matches_known_interval() -> None:
    low, high = T.wilson(48, 53)
    assert (round(low, 3), round(high, 3)) == (0.797, 0.959)


def test_agreement_report_lists_disagreements_by_item_id_only(
    blank: list[dict[str, str]],
) -> None:
    a = T.validate_sheet(
        _example_sheet(blank, "example-labeller-a"), blank, allow_example=True
    )[0]
    b = T.validate_sheet(
        _example_sheet(blank, "example-labeller-b", flips=(1, 7)),
        blank,
        allow_example=True,
    )[0]
    report = T.agreement_report(a, b, resamples=200)
    assert report["disagreement_count"] == 2
    assert {d["item_id"] for d in report["disagreements"]} == {
        blank[1]["item_id"],
        blank[7]["item_id"],
    }
    g = report["dimensions"]["groundedness"]
    assert (
        g["agree"] == 51 and g["percent_agreement_wilson95"][0] < g["percent_agreement"]
    )
    assert (
        g["kappa_bootstrap_ci95"]["lower"] is not None
        and report["dimensions"]["relevance"]["agree"] == 53
    )
    assert T.agreement_report(a, b, resamples=200) == report


# -------------------------------------------------------------------- merge


def _prepare(
    blank: list[dict[str, str]],
    key: dict[str, Any],
    tmp_path: Path,
    *,
    flips: tuple[int, ...] = (1, 7, 20),
) -> dict[str, Any]:
    a = _example_sheet(blank, "example-labeller-a")
    b = _example_sheet(blank, "example-labeller-b", flips=flips)
    pa, pb = (
        _write(tmp_path / "example_a.csv", a),
        _write(tmp_path / "example_b.csv", b),
    )
    na, nb = (
        T.validate_sheet(a, blank, allow_example=True)[0],
        T.validate_sheet(b, blank, allow_example=True)[0],
    )
    report = T.agreement_report(na, nb, resamples=200)
    template = T.adjudication_template(blank, na, nb, report)
    rows = list(csv.DictReader(template.splitlines(keepends=True)))
    for row in rows:
        row.update(
            adjudicated_label="UNKNOWN",
            adjudicated_reason="low_confidence",
            rationale="SYNTHETIC EXAMPLE adjudication rationale",
            adjudicator_id="example-adjudicator",
        )
    adj = tmp_path / "example_adjudication.csv"
    adj.write_text(T.render_csv(rows, T.ADJ_COLUMNS), encoding="utf-8")
    thresholds = json.loads(
        (DOC_DIR / "PREDECLARED_THRESHOLDS.json").read_text(encoding="utf-8")
    )
    return {
        "blank_rows": blank,
        "sheet_a": pa,
        "sheet_b": pb,
        "adjudication_path": adj,
        "key": key,
        "split": "heldout",
        "dataset_id": "example-p29-tooling-selftest",
        "dataset_version": "1",
        "created_at": "2026-11-08T00:00:00+00:00",
        "license_id": "CC0-1.0",
        "confirmed_thresholds_sha256": thresholds["thresholds_sha256"],
        "out_dir": tmp_path / "out",
        "_allow_example_labellers": True,
    }


def test_merge_writes_loadable_datasets_without_inventing_labels(
    export_rows: tuple[list[dict[str, str]], dict[str, Any]], tmp_path: Path
) -> None:
    blank, key = export_rows
    kwargs = _prepare(blank, key, tmp_path)
    result = T.merge(**kwargs)
    assert set(result) == set(T.DIMENSIONS)
    for dimension, info in result.items():
        loaded = ds.load_reference_dataset(
            info["manifest"], expected_manifest_sha256=info["manifest_sha256"]
        )
        cases = loaded.splits[ds.Split.HELDOUT]
        assert len(cases) == 53
        text = (Path(info["manifest"]).parent / "heldout.jsonl").read_text(
            encoding="utf-8"
        )
        assert "SYNTHETIC EXAMPLE" in Path(info["manifest"]).read_text(encoding="utf-8")
        docs = [json.loads(line) for line in text.splitlines()]
        sheet_a = {r["item_id"]: r for r in T.read_sheet(kwargs["sheet_a"])}
        for doc in docs:
            if doc["adjudication"]["method"] == "none":
                assert (
                    doc["human_label"]
                    == sheet_a[doc["case_id"]][f"{dimension}_label"].lower()
                )
            else:
                assert doc["human_label"] == "unknown"
            assert doc["label_provenance"] in ("human_multi", "human_adjudicated")
        assert {d["source"] for d in docs} <= {"agent_run", "constructed"}
        # The labeller-only reason code never reaches the shipped dataset contract.
        assert "dimension_not_applicable" not in text
    manifest = json.loads(
        Path(result["groundedness"]["manifest"]).read_text(encoding="utf-8")
    )
    assert manifest["splits"]["heldout"]["label_provenance"] == "human_multi"
    assert manifest["rubric"]["rubric_id"] == "judge-groundedness"


def test_merge_is_deterministic(
    export_rows: tuple[list[dict[str, str]], dict[str, Any]], tmp_path: Path
) -> None:
    blank, key = export_rows
    first_dir, second_dir = tmp_path / "x", tmp_path / "y"
    first_dir.mkdir()
    second_dir.mkdir()
    one = T.merge(**_prepare(blank, key, first_dir))
    two = T.merge(**_prepare(blank, key, second_dir))
    assert {k: v["manifest_sha256"] for k, v in one.items()} == {
        k: v["manifest_sha256"] for k, v in two.items()
    }


def test_merge_refuses_example_labellers_without_the_private_allowance(
    export_rows: tuple[list[dict[str, str]], dict[str, Any]], tmp_path: Path
) -> None:
    blank, key = export_rows
    kwargs = _prepare(blank, key, tmp_path)
    kwargs["_allow_example_labellers"] = False
    with pytest.raises(T.ToolError, match="not valid"):
        T.merge(**kwargs)
    assert not (tmp_path / "out").exists()


def test_the_command_line_cannot_enable_the_example_allowance() -> None:
    import inspect

    assert "_allow_example" not in inspect.getsource(T.main)


def test_merge_refuses_incomplete_sheets_and_a_blank_sheet(
    export_rows: tuple[list[dict[str, str]], dict[str, Any]], tmp_path: Path
) -> None:
    blank, key = export_rows
    kwargs = _prepare(blank, key, tmp_path)
    _write(kwargs["sheet_b"], _example_sheet(blank, "example-labeller-b")[:-1])
    with pytest.raises(T.ToolError, match="missing from the sheet"):
        T.merge(**kwargs)
    _write(kwargs["sheet_b"], blank)
    with pytest.raises(T.ToolError, match="not valid"):
        T.merge(**kwargs)


def test_merge_refuses_wrong_thresholds_digest_and_same_labeller(
    export_rows: tuple[list[dict[str, str]], dict[str, Any]], tmp_path: Path
) -> None:
    blank, key = export_rows
    kwargs = _prepare(blank, key, tmp_path)
    with pytest.raises(T.ToolError, match="thresholds digest"):
        T.merge(**{**kwargs, "confirmed_thresholds_sha256": "0" * 64})
    _write(kwargs["sheet_b"], _example_sheet(blank, "example-labeller-a"))
    with pytest.raises(T.ToolError, match="same labeller_id"):
        T.merge(**kwargs)


def test_merge_refuses_below_the_kappa_floor_and_does_not_relax_it(
    export_rows: tuple[list[dict[str, str]], dict[str, Any]], tmp_path: Path
) -> None:
    blank, key = export_rows
    kwargs = _prepare(blank, key, tmp_path, flips=tuple(range(0, 53, 2)))
    with pytest.raises(T.ToolError, match=r"kappa|agreement"):
        T.merge(**kwargs)


def test_merge_refuses_missing_or_extra_adjudication_and_a_non_independent_adjudicator(
    export_rows: tuple[list[dict[str, str]], dict[str, Any]], tmp_path: Path
) -> None:
    blank, key = export_rows
    kwargs = _prepare(blank, key, tmp_path)
    adj = Path(kwargs["adjudication_path"])
    rows = list(
        csv.DictReader(adj.read_text(encoding="utf-8").splitlines(keepends=True))
    )
    adj.write_text(T.render_csv(rows[:-1], T.ADJ_COLUMNS), encoding="utf-8")
    with pytest.raises(T.ToolError, match="no adjudication"):
        T.merge(**kwargs)
    same = [{**r, "adjudicator_id": "example-labeller-a"} for r in rows]
    adj.write_text(T.render_csv(same, T.ADJ_COLUMNS), encoding="utf-8")
    with pytest.raises(T.ToolError, match="different role"):
        T.merge(**kwargs)
    nor = [{**r, "rationale": ""} for r in rows]
    adj.write_text(T.render_csv(nor, T.ADJ_COLUMNS), encoding="utf-8")
    with pytest.raises(T.ToolError, match="rationale"):
        T.merge(**kwargs)
    extra = [*rows, {**rows[0], "item_id": blank[40]["item_id"]}]
    adj.write_text(T.render_csv(extra, T.ADJ_COLUMNS), encoding="utf-8")
    with pytest.raises(T.ToolError, match="labellers agreed"):
        T.merge(**kwargs)


def test_merge_refuses_a_naive_timestamp_bad_split_and_foreign_key(
    export_rows: tuple[list[dict[str, str]], dict[str, Any]], tmp_path: Path
) -> None:
    blank, key = export_rows
    kwargs = _prepare(blank, key, tmp_path)
    with pytest.raises(T.ToolError, match="UTC offset"):
        T.merge(**{**kwargs, "created_at": "2026-11-08T00:00:00"})
    with pytest.raises(T.ToolError, match="split"):
        T.merge(**{**kwargs, "split": "everything"})
    with pytest.raises(T.ToolError, match="key"):
        T.merge(**{**kwargs, "key": {**key, "items": {}}})


def test_cli_exports_and_validates(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert (
        T.main(
            [
                "export",
                "--out-dir",
                str(tmp_path / "s"),
                "--key-out",
                str(tmp_path / "k" / "key.json"),
            ]
        )
        == 0
    )
    blank_json = tmp_path / "s" / "blank_sheet.json"
    assert (
        T.main(["validate", "--blank", str(blank_json), "--sheet", str(blank_json)])
        == 1
    )
    out = capsys.readouterr().out
    assert '"valid": false' in out
    key_hash = hashlib.sha256((tmp_path / "k" / "key.json").read_bytes()).hexdigest()
    committed = json.loads(
        (DOC_DIR / "blank-sheet" / "export_manifest.json").read_text(encoding="utf-8")
    )
    assert key_hash == committed["private_key_sha256"]


def test_labeller_only_reason_code_is_not_in_any_shipped_source_or_rubric() -> None:
    root = Path(__file__).resolve().parents[3]
    shipped = list((root / "src").rglob("*"))
    offenders = [
        str(p)
        for p in shipped
        if p.is_file()
        and p.suffix in {".py", ".json"}
        and "dimension_not_applicable" in p.read_text(encoding="utf-8")
    ]
    assert offenders == []


# --- relevance-only round (items-file + dimensions) -------------------------


def _relevance_items(n: int = 6) -> list[dict[str, Any]]:
    return [
        {
            "case_id": f"src-{i}",
            "source": "constructed",
            "question": f"Question {i}?",
            "context": [] if i % 2 else [f"block {i}"],
            "answer": f"Answer {i}.",
        }
        for i in range(n)
    ]


def test_relevance_only_export_has_no_groundedness_columns(tmp_path: Path) -> None:
    T.export(
        tmp_path / "out",
        tmp_path / "key" / "k.json",
        seed="s",
        salt="secret",
        items=_relevance_items(),
        dimensions=("relevance",),
    )
    header = (tmp_path / "out" / "blank_sheet.csv").read_text().splitlines()[0]
    assert "relevance_label" in header and "groundedness" not in header
    doc = json.loads((tmp_path / "out" / "blank_sheet.json").read_text())
    assert list(doc["allowed"]["reason"]) == ["relevance"]
    for row in doc["rows"]:
        assert row["relevance_label"] == ""  # the tool never writes a label


def test_relevance_only_sheet_validates_and_agreement_covers_one_dimension(
    tmp_path: Path,
) -> None:
    T.export(
        tmp_path / "out",
        tmp_path / "key" / "k.json",
        seed="s",
        salt="secret",
        items=_relevance_items(),
        dimensions=("relevance",),
    )
    blank = T.read_sheet(tmp_path / "out" / "blank_sheet.json")

    def filled(who: str) -> list[dict[str, str]]:
        rows = []
        for r in blank:
            r = dict(r)
            r.update(
                relevance_label="PASS",
                relevance_reason="addresses_question",
                relevance_confidence="HIGH",
                note="SYNTHETIC EXAMPLE",
                labeller_id=who,
            )
            rows.append(r)
        return rows

    a, errors = T.validate_sheet(filled("role-a"), blank, allow_example=True)
    assert errors == []
    b, errors = T.validate_sheet(filled("role-b"), blank, allow_example=True)
    assert errors == []
    report = T.agreement_report(a, b)
    assert list(report["dimensions"]) == ["relevance"]
    # a groundedness column in a relevance-only sheet is a schema mismatch
    bad = [{**r, "groundedness_label": ""} for r in filled("role-a")]
    _, errors = T.validate_sheet(bad, blank, allow_example=True)
    assert errors


def test_salt_changes_the_blind_order_and_ids_stay_opaque(tmp_path: Path) -> None:
    rows1, key1 = T.build_export(
        _relevance_items(), seed="s", salt="one", dimensions=("relevance",)
    )
    rows2, _ = T.build_export(
        _relevance_items(), seed="s", salt="two", dimensions=("relevance",)
    )
    assert [r["question"] for r in rows1] != [r["question"] for r in rows2]
    assert all(r["item_id"].startswith("L") for r in rows1)
    assert key1["salted"] is True
