"""Reference datasets: bounded, pinned, contained, provenance-checked, leak-checked."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

from agent_reliability.experimental.calibration import (
    DatasetError,
    LabelProvenance,
    Split,
    load_reference_dataset,
)
from agent_reliability.experimental.calibration import dataset as dataset_module
from tests.fakes.p29_calibration import (
    CANARY,
    case_doc,
    heldout_cases,
    load,
    write_dataset,
)

pytestmark = pytest.mark.unit


def test_a_valid_dataset_loads_with_derived_provenance_and_counts(
    tmp_path: Path,
) -> None:
    ds = load(tmp_path, {"heldout": heldout_cases()})
    assert ds.dataset_id == "synthetic-ds" and ds.dataset_version == "1"
    assert len(ds.cases(Split.HELDOUT)) == 28
    assert ds.split_provenance[Split.HELDOUT] is LabelProvenance.SYNTHETIC
    assert ds.provenance_counts(Split.HELDOUT)["synthetic"] == 28
    assert ds.leakage.clean


def test_repr_never_contains_case_content(tmp_path: Path) -> None:
    ds = load(tmp_path, {"heldout": heldout_cases()})
    assert CANARY not in repr(ds) and CANARY not in repr(ds.cases(Split.HELDOUT)[0])
    assert CANARY not in repr(ds.leakage)


def test_the_manifest_digest_must_be_pinned_by_the_caller(tmp_path: Path) -> None:
    path, digest = write_dataset(tmp_path, {"heldout": heldout_cases()})
    with pytest.raises(DatasetError, match="pin"):
        load_reference_dataset(path, expected_manifest_sha256="0" * 64)
    with pytest.raises(DatasetError):
        load_reference_dataset(path, expected_manifest_sha256="not a digest")
    load_reference_dataset(path, expected_manifest_sha256=digest)


def test_editing_a_split_after_pinning_is_detected(tmp_path: Path) -> None:
    path, digest = write_dataset(tmp_path, {"heldout": heldout_cases()})
    split_file = tmp_path / "heldout.jsonl"
    split_file.write_bytes(split_file.read_bytes().replace(b"fail", b"pass", 1))
    with pytest.raises(DatasetError, match="digest"):
        load_reference_dataset(path, expected_manifest_sha256=digest)


def test_editing_the_manifest_after_pinning_is_detected(tmp_path: Path) -> None:
    path, digest = write_dataset(tmp_path, {"heldout": heldout_cases()})
    path.write_bytes(path.read_bytes().replace(b"synthetic-ds", b"synthetic-dX"))
    with pytest.raises(DatasetError, match="pin"):
        load_reference_dataset(path, expected_manifest_sha256=digest)


def _rewrite_manifest(path: Path, mutate) -> str:  # type: ignore[no-untyped-def]
    manifest = json.loads(path.read_text())
    mutate(manifest)
    raw = json.dumps(manifest, sort_keys=True).encode()
    path.write_bytes(raw)
    return hashlib.sha256(raw).hexdigest()


@pytest.mark.parametrize(
    "mutate",
    [
        lambda m: m["splits"]["heldout"].update(file="../outside.jsonl"),
        lambda m: m["splits"]["heldout"].update(file="/etc/passwd"),
        lambda m: m["splits"]["heldout"].update(file="sub/heldout.jsonl"),
        lambda m: m["splits"]["heldout"].update(file=".."),
        lambda m: m["splits"]["heldout"].update(case_count=1),
        lambda m: m["splits"]["heldout"].update(label_provenance="human_adjudicated"),
        lambda m: m["splits"]["heldout"].update(sha256="g" * 64),
        lambda m: m.update(unknown_member=1),
        lambda m: m.update(schema="gentlity.reference-dataset/2"),
        lambda m: m.update(created_at="2026-09-01T00:00:00"),  # naive
        lambda m: m.update(dataset_id="has space"),
        lambda m: m["rubric"].update(dimension="not-a-dimension"),
        lambda m: m["splits"].update(bogus=m["splits"]["heldout"]),
    ],
)
def test_manifest_violations_are_rejected(tmp_path: Path, mutate) -> None:  # type: ignore[no-untyped-def]
    path, _ = write_dataset(tmp_path, {"heldout": heldout_cases()})
    digest = _rewrite_manifest(path, mutate)
    with pytest.raises(DatasetError):
        load_reference_dataset(path, expected_manifest_sha256=digest)


def test_a_symlinked_split_file_is_refused(tmp_path: Path) -> None:
    path, _ = write_dataset(tmp_path, {"heldout": heldout_cases()})
    target = tmp_path / "real.jsonl"
    (tmp_path / "heldout.jsonl").rename(target)
    os.symlink(target, tmp_path / "heldout.jsonl")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    with pytest.raises(DatasetError, match="symlink"):
        load_reference_dataset(path, expected_manifest_sha256=digest)


def test_size_caps_are_enforced_before_reading(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(dataset_module, "MAX_SPLIT_BYTES", 100)
    path, digest = write_dataset(tmp_path, {"heldout": heldout_cases()})
    with pytest.raises(DatasetError, match="size cap"):
        load_reference_dataset(path, expected_manifest_sha256=digest)


def test_line_and_case_count_caps(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(dataset_module, "MAX_LINE_BYTES", 120)
    path, digest = write_dataset(tmp_path, {"heldout": heldout_cases(1, 1, 0)})
    with pytest.raises(DatasetError, match="line"):
        load_reference_dataset(path, expected_manifest_sha256=digest)


@pytest.mark.parametrize(
    "line",
    [
        '{"schema":"gentlity.reference-case/1","schema":"gentlity.reference-case/1"}',
        '{"schema":"gentlity.reference-case/1","x":NaN}',
        '{"schema":"gentlity.reference-case/1","x":Infinity}',
        "not json",
        "[1,2]",
        "[" * 400 + "]" * 400,
    ],
)
def test_strict_json_rejects_hostile_lines(tmp_path: Path, line: str) -> None:
    path, digest = write_dataset(
        tmp_path, {"heldout": [case_doc("a")]}, raw_lines={"heldout": [line]}
    )
    with pytest.raises(DatasetError):
        load_reference_dataset(path, expected_manifest_sha256=digest)


def test_error_messages_never_contain_case_content(tmp_path: Path) -> None:
    bad = case_doc("x", text=f"{CANARY} secret")
    bad["human_label"] = "maybe"
    path, digest = write_dataset(tmp_path, {"heldout": [bad]})
    with pytest.raises(DatasetError) as error:
        load_reference_dataset(path, expected_manifest_sha256=digest)
    assert CANARY not in str(error.value) and CANARY not in repr(error.value)


# -------------------------------------------------------- label & provenance rules


def _ok(tmp_path: Path, docs: list[dict], prov: str = "synthetic") -> None:  # type: ignore[type-arg]
    load(tmp_path, {"heldout": docs}, provenance={"heldout": prov})


def test_unanimous_labels_must_match_human_label(tmp_path: Path) -> None:
    doc = case_doc(
        "a", "fail", provenance="human_multi", labels=[("r1", "pass"), ("r2", "pass")]
    )
    with pytest.raises(DatasetError, match="contradicts"):
        _ok(tmp_path, [doc], "human_multi")


def test_disagreeing_labels_need_an_adjudication_method(tmp_path: Path) -> None:
    doc = case_doc(
        "a", "pass", provenance="human_multi", labels=[("r1", "pass"), ("r2", "fail")]
    )
    with pytest.raises(DatasetError, match="adjudication"):
        _ok(tmp_path, [doc], "human_multi")


def test_majority_adjudication_must_pick_the_strict_majority(tmp_path: Path) -> None:
    labels = [("r1", "pass"), ("r2", "pass"), ("r3", "fail")]
    good = case_doc(
        "a",
        "pass",
        provenance="human_adjudicated",
        labels=labels,
        adjudication="majority",
    )
    _ok(tmp_path / "ok", [good], "human_adjudicated")
    bad = case_doc(
        "a",
        "fail",
        provenance="human_adjudicated",
        labels=labels,
        adjudication="majority",
    )
    with pytest.raises(DatasetError, match="majority"):
        _ok(tmp_path / "bad", [bad], "human_adjudicated")
    tie = case_doc(
        "a",
        "pass",
        provenance="human_adjudicated",
        labels=[("r1", "pass"), ("r2", "fail")],
        adjudication="majority",
    )
    with pytest.raises(DatasetError, match="majority"):
        _ok(tmp_path / "tie", [tie], "human_adjudicated")


def test_unresolved_cases_are_indeterminate_whatever_else_is_said(
    tmp_path: Path,
) -> None:
    labels = [("r1", "pass"), ("r2", "fail")]
    bad = case_doc(
        "a",
        "pass",
        provenance="human_adjudicated",
        labels=labels,
        adjudication="unresolved",
    )
    with pytest.raises(DatasetError, match="unknown"):
        _ok(tmp_path / "bad", [bad], "human_adjudicated")
    good = case_doc(
        "a",
        "unknown",
        provenance="human_adjudicated",
        labels=labels,
        adjudication="unresolved",
    )
    ds = load(
        tmp_path / "ok",
        {"heldout": [good]},
        provenance={"heldout": "human_adjudicated"},
    )
    assert ds.cases(Split.HELDOUT)[0].indeterminate


def test_human_provenance_needs_labelers_and_multi_needs_two(tmp_path: Path) -> None:
    with pytest.raises(DatasetError, match="labeler"):
        _ok(
            tmp_path / "none",
            [case_doc("a", provenance="human_single")],
            "human_single",
        )
    with pytest.raises(DatasetError, match="two"):
        _ok(
            tmp_path / "one",
            [case_doc("a", provenance="human_multi", labels=[("r1", "pass")])],
            "human_multi",
        )


def test_adjudication_without_labels_is_refused(tmp_path: Path) -> None:
    with pytest.raises(DatasetError, match="requires labeler"):
        _ok(tmp_path, [case_doc("a", adjudication="majority")])


def test_duplicate_labeler_ids_within_a_case_are_refused(tmp_path: Path) -> None:
    doc = case_doc(
        "a", provenance="human_multi", labels=[("r1", "pass"), ("r1", "pass")]
    )
    with pytest.raises(DatasetError, match="unique"):
        _ok(tmp_path, [doc], "human_multi")


def test_declared_provenance_must_equal_the_weakest_case(tmp_path: Path) -> None:
    labels = [("r1", "pass"), ("r2", "pass")]
    strong = case_doc("a", provenance="human_multi", labels=labels)
    weak = case_doc("b", provenance="synthetic")
    with pytest.raises(DatasetError, match="weakest"):
        _ok(tmp_path, [strong, weak], "human_multi")
    ds = load(
        tmp_path / "ok",
        {"heldout": [strong, weak]},
        provenance={"heldout": "synthetic"},
    )
    assert ds.split_provenance[Split.HELDOUT] is LabelProvenance.SYNTHETIC
    assert ds.provenance_counts(Split.HELDOUT)["human_multi"] == 1


def test_provenance_is_derived_per_split_not_across_the_dataset(tmp_path: Path) -> None:
    labels = [("r1", "pass"), ("r2", "pass")]
    human = [
        case_doc(f"h{i}", provenance="human_multi", labels=labels) for i in range(3)
    ]
    synth = [case_doc(f"t{i}", provenance="synthetic") for i in range(3)]
    ds = load(
        tmp_path,
        {"heldout": human, "train": synth},
        provenance={"heldout": "human_multi", "train": "synthetic"},
    )
    assert ds.split_provenance[Split.HELDOUT] is LabelProvenance.HUMAN_MULTI
    assert ds.split_provenance[Split.TRAIN] is LabelProvenance.SYNTHETIC


def test_dimension_must_match_the_manifest_rubric(tmp_path: Path) -> None:
    doc = case_doc("a")
    doc["dimension"] = "groundedness"
    with pytest.raises(DatasetError):
        _ok(tmp_path, [doc])


# ------------------------------------------------------------------- leakage


def test_leakage_is_detected_by_id_content_and_normalised_content(
    tmp_path: Path,
) -> None:
    train = [
        case_doc("t1", text="Alpha  Beta"),
        case_doc("t2", text="same text"),
        case_doc("shared"),
    ]
    heldout = [
        case_doc("h1", text="alpha beta"),  # normalised duplicate of t1
        case_doc("h2", text="same text"),  # exact duplicate of t2
        case_doc("shared", text="different"),  # same case_id across splits
        case_doc("h4", text="unique"),
    ]
    ds = load(tmp_path, {"train": train, "heldout": heldout})
    leak = ds.leakage
    assert not leak.clean and leak.cross_split
    assert ("shared", ("heldout", "train")) in leak.duplicate_case_ids
    assert ("h2", "t2") in leak.identical_content
    assert ("h1", "t1") in leak.identical_normalized
    exported = json.dumps(leak.as_dict())
    assert "h4" not in exported and CANARY not in exported
    assert {"h1", "h2", "t1", "t2", "shared"} <= set(leak.as_dict()["case_ids"])


def test_distinct_cases_are_clean(tmp_path: Path) -> None:
    ds = load(
        tmp_path, {"train": heldout_cases(2, 2, 0), "heldout": [case_doc("only")]}
    )
    assert ds.leakage.clean and not ds.leakage.cross_split
