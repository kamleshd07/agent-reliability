# P29 / P28 SDK reconciliation record (2026-10-16)

Status: working record of an isolated, local, uncommitted reconciliation. Nothing was committed,
pushed, released or published. P29 functionality is **not** part of the P28 release candidate.

## 1. Trees

| Tree | Path | Role | Touched? |
|---|---|---|---|
| P28 SDK (source of the verified corrections) | `<workspace>/agent-reliability` (main @ `7aa6883`, uncommitted P28 work) | read-only here (its own P28 follow-ups are recorded in `P28_P29_RELEASE_GATE_CONSOLIDATION.md` in that tree) | no |
| P29 SDK workspace (original) | `<workspace>/agent-reliability-p29` (branch `p29-sdk-v1-local` @ `7aa6883`, 17 M + 101 ?? uncommitted) | preserved | **no** (sha256 of every modified/untracked file identical before and after) |
| This tree | `<workspace>/agent-reliability-p29-reconciled` | copy of the P29 workspace (`rsync -a`, `.git` included, caches/venvs/dist excluded) plus the corrections below | yes |

## 2. Method (deterministic, per file)

For every file in the P28 SDK dirty set (`git ls-files -m -o --exclude-standard`) its sha256 was
compared with (a) the same path in the P29 workspace and (b) the P29 re-sync manifest entry
`docs/P29_WORKSPACE_BASELINE_RESYNC.sha256`, which records the pre-P29 content:

| Class | Rule | Files |
|---|---|---|
| identical | nothing to do | 30 |
| copy-forward | P29 content == manifest, i.e. P29 never edited it: replaced by the current P28 file | `.github/workflows/release.yml`, `CHANGELOG.md`, `CONTRIBUTING.md`, `docs/HTTP_EXPORTER.md`, `pyproject.toml`, `src/agent_reliability/adapters/http_event_sink.py`, `tests/unit/test_http_exporter_tls_real.py` |
| new in P28 | added | `docs/P28_SDK_EXPORTER_RELEASE_READINESS_REPORT.md`, `docs/P28_SDK_EXPORTER_RELEASE_TARGETED_VERIFICATION.md`, `tests/unit/test_http_exporter_release_regressions.py` |
| P29-edited | merged by hand | `README.md` (P29 added the experimental-judge section; P28 had no delta, so P29's file is kept as is), `scripts/verify_release_artifacts.py` (P29 added judge-file assertions; the P28 delta, the sdist-internal-files check and `import re`, was applied to P29's file and reformatted with ruff) |

`_http_delivery.py` and `_http_protocol.py` were already byte-identical. The complete P29 judge
(`src/agent_reliability/experimental/judge/`, rubrics, schemas, tests, fixtures, examples, docs,
ADR-0010) is untouched. No conflicts remained. Corrections now present that the P29 workspace
lacked: proxy CONNECT handling, response-body time budget, `ImportError` hint for the missing
extra, idle-worker snapshot fix, sdist internal-file exclusion and its guard, the stability
status section, the CHANGELOG/HTTP_EXPORTER updates, `release.yml`/`CONTRIBUTING.md` installing
the `http` extra, and the release-regression tests.

## 3. Hash-pinned P29 guards

`tests/fakes/p29_baseline.py` prefers `docs/P29_WORKSPACE_BASELINE_RESYNC.sha256`. Two guards
(`test_no_existing_source_module_is_modified_by_p29`, `test_p29_s09_ac06_p28_fixtures_and_contract_documents_are_byte_identical`)
correctly failed after the copy-forward because P28-owned files had advanced. Following the
manifest's own convention ("entries of P29-edited files keep their pre-P29 content hash"), this
tree's manifest was updated: 8 entries re-hashed, 3 entries added; no entry of a P29-owned file
was changed. For the 7 copy-forward files the new hash is the current P28 content; for the
hand-merged `scripts/verify_release_artifacts.py` it is the hash of the merged file (P28 content
plus the P29 judge assertions), because no pre-P29 copy of the P28 version exists any more. No
guard reads that file's entry. The packaging exclusion is limited to `docs/P28_*`; P29's own sdist
contents are a separate P29 decision. The previous manifest is preserved outside the tree
(`<scratch>`). Subsequent runs of both
guards pass; the guards still fail if any pinned file is changed afterwards.

## 4. Evidence (this tree)

See `P28_P29_RELEASE_GATE_CONSOLIDATION.md` (SDK repo, sections 6 and 7) for the results. In short:
suite 1,561 passed / 1 skipped on Python 3.11, 3.12 and 3.13; the previously skipped
platform-model validation (`P29_PLATFORM_ROOT`/`P29_PLATFORM_PYTHON`) passes when enabled; ruff,
format and mypy are clean; a live judge -> HTTP exporter -> real platform test passes on
PostgreSQL 16 and 17. Pilot safeguards SG-1..SG-6 remain **NOT SATISFIED**; this reconciliation
provides no pilot evidence.

## 5. Final-candidate update (2026-10-17)

This tree was copied to `agent-reliability-final` (final integration workspace). Further P28-owned
edits (owner decisions F-4/F-9/L2 recorded in `P28_SDK_EXPORTER_OWNER_DECISIONS_002.md`:
`HTTP_EXPORTER.md` stability and L2 text, `GA_CONTRACT.md` INTERNAL paragraph, `CHANGELOG.md`,
sdist exclusions in `pyproject.toml`, the P29 packaging guards in
`scripts/verify_release_artifacts.py`) changed four manifest-pinned P28-owned files; their
`P29_WORKSPACE_BASELINE_RESYNC.sha256` entries (`docs/HTTP_EXPORTER.md`, `pyproject.toml`,
`CHANGELOG.md`, `scripts/verify_release_artifacts.py`) were re-hashed by the same convention
as section 3. No P29-owned entry changed.
