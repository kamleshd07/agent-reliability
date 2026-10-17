# P29 test evidence (author-run, 2026-10-16)

All results below were produced by the implementing agent in `<workspace>/agent-reliability-p29` and are **not independently verified**. Nothing is committed, merged, published or deployed.
Environment: macOS (Darwin 25.5.0, arm64), uv 0.13.1, CPython 3.11.17 / 3.12.15 / 3.13.16 (venvs under `~/.venvs-p29/py3.XX`, created with
`uv venv --python 3.XX` and `uv pip install -e ".[dev,otel-test,http]"`), ruff 0.17.1, mypy 2.4.0, pytest 9.1.1, hatchling 1.32.4 (build). The baseline before any P29 change and its construction are in `docs/P29_WORKSPACE_BASELINE.md`.

## 1. Gate commands (from the workspace root; `V=~/.venvs-p29/py3.XX/bin`)

```sh
$V/ruff check .
$V/ruff format --check .
$V/mypy src
P29_PLATFORM_ROOT=<workspace>/agent-reliability-platform-integration \
P29_PLATFORM_PYTHON=<scratch venv with pydantic/fastapi>/bin/python \
  $V/python -m pytest -q -p no:cacheprovider --junitxml=<scratch>/junit-3.XX.xml     # platform check enabled
$V/python -m pytest -q -p no:cacheprovider                                          # default (platform check skipped)
```

| Python | ruff check | ruff format --check | mypy src (strict) | pytest, platform check enabled | pytest, default |
|---|---|---|---|---|---|
| 3.11.17 | All checks passed | 239 files already formatted | no issues, 65 source files | 1548 passed | 1547 passed, 1 skipped |
| 3.12.15 | All checks passed | 239 files already formatted | no issues, 65 source files | 1548 passed | 1547 passed, 1 skipped |
| 3.13.16 | All checks passed | 239 files already formatted | no issues, 65 source files | 1548 passed | 1547 passed, 1 skipped |

The one skipped test in a default run is `test_p29_s09_ac03_payloads_validate_against_platform_v2_models` (NOT_EXERCISED without the two environment variables). Baseline was 856 passed on each Python;
P29 added 692 tests (part 1: 466, part 2: 201, review remediation: 25). Raw run log: reproduced in section 6.

## 2. Existing regression suite

Command: the full suite with every P29 test file ignored or deselected (`--ignore=tests/unit/experimental_judge`, plus `--deselect` of the P29 contract, compat, security and property files):
**856 passed** on 3.11, 3.12 and 3.13, identical to the pre-P29 baseline count. No existing test file was modified (existing compat snapshots are hash-guarded by `tests/compat/test_experimental_judge_api.py`).

## 3. Concurrency and stress determinism

`tests/unit/experimental_judge/test_s05_recording_gate.py`, `test_s05_coordinator.py`, `test_s07_s08_optional.py`, `test_s11_pilot_artifacts.py` and `test_review_remediation.py` (82 tests, including 64 asyncio evaluations, 64 `evaluate_sync` calls from 8 threads, a mixed run,
a 2 ms sink inside the gate, drain timeouts and a late-completion thread) were run **three times on each Python**: 82 passed every time (9 of 9 runs). The overlap counters (handle wrapper, sink spy) were 0 in every run.
This is a determinism check over nine repetitions, not a proof of freedom from races, and not a load test (none was run).

## 4. Packaging

```sh
$V/python -m build --outdir <scratch>/dist .                     # python 3.11; sdist + wheel, outside the tree
python scripts/verify_release_artifacts.py --wheel <scratch>/dist/agent_reliability-1.2.1-py3-none-any.whl \
                                           --sdist <scratch>/dist/agent_reliability-1.2.1.tar.gz
```

Result: "artifact metadata and contents: ok (1.2.1)", base wheel and offline examples ok (base wheel installed with `--no-deps`; the judge package and the five reference rubrics load from the installed wheel),
sdist install ok, HTTP-extra installed-wheel mocked delivery ok, OTel-extra ok, installed-wheel downstream strict mypy ok. The wheel contains `agent_reliability/experimental/judge/` (19 modules), the five
`rubrics/*.json` and the two `schemas/*.schema.json` data files, requires no dependency beyond the existing extras, and still declares `dependencies = []`. The script check `required_wheel` was extended to demand them.
Nothing was uploaded or published; artifacts exist only in the scratch directory. `scripts/verify_p28_fixtures.py`: "4 fixture hashes verified; platform comparison: False".

## 5. Import isolation and no new dependency

* `pyproject.toml` is unmodified (`dependencies = []`, no new extra); `tests/compat/test_experimental_judge_api.py::test_core_dependencies_remain_empty_and_no_entry_points`.
* A static AST scan of `src/agent_reliability/experimental/judge/*.py` finds **no third-party import**; importing the namespace (and its `testing` module) in a fresh `python -I` process loads **no non-stdlib module outside `agent_reliability`**
  (`test_importing_the_namespace_loads_no_third_party_module`) and none of httpx, requests, aiohttp, urllib3, http.client, urllib.request, openai, anthropic, opentelemetry or the exporter (`test_pg3_importing_...`).
* `examples/judge_providers.py` uses `urllib` (standard library) and is never imported by the package; `examples/judge_pilot_demo.py` needs `httpx` (the existing `http` extra) and is example code.

## 6. Cross-repository (read-only) platform check

`test_p29_s09_ac03_payloads_validate_against_platform_v2_models` ran the platform's `EvidenceEnvelopeV2` model over every envelope produced by the 16 wire vectors (including all ten failure classes and both contract section 11 examples).
Platform tree: `<workspace>/agent-reliability-platform-integration/src` (read-only; imported by a separate scratch venv with `PYTHONDONTWRITEBYTECODE=1` and `python -B`; no platform file was written: its `git status --porcelain` line count was 51 before and after).
Scratch venv packages: pydantic, fastapi, pydantic-settings, sqlalchemy[asyncio], PyJWT[crypto], alembic, asyncpg, uvicorn (public packages, installed from the package index). Result: all envelopes validated. This says nothing about delivery, authentication or aggregation on a platform.

## 7. Not run

* Any benchmark, load, soak or memory-under-load test (S12-AC01): **NOT RUN**.
* Independent review (S12-AC02) and release gate (S12-AC05): not performed / blocked.
* Any real model, provider or network call (the example providers use a fake transport); the manual local-model walkthrough (S06-AC05).
* Any run against a platform, shared TEST or production; platform reads P3/P4/P6/P7 (S11-AC02, AC03, AC05, AC10); live HTTP delivery and exporter TLS handling (the D-1 fix is in the uncommitted working tree; no P29 test exercises real TLS).
* `mypy` on `tests/` and `examples/` (CI runs `mypy src` only; the pre-existing `examples/builtin_evaluators_quickstart.py` has typing gaps unrelated to P29).
* The CI workflow file itself.

## 8. Source-tree drift note

While part 2 ran, another session added `docs/P28_SDK_D1_INDEPENDENT_REVIEW.md` and `docs/P28_SDK_D1_REMEDIATION_REPORT.md` to the original SDK tree and changed `docs/HTTP_EXPORTER.md` and `tests/unit/test_http_exporter_tls_real.py` there
(P28 D-1 remediation work by someone else; this work never wrote to that tree). (Superseded by section 11: the overlay was re-synced.) The P29 workspace baseline predated those edits; merging the P29 work onto a D-1-fixed exporter needs a re-run of this evidence.

## 9. Review remediation re-run (after docs/P29_INDEPENDENT_REVIEW.md)

The independent reviewer returned APPROVE_WITH_REQUIRED_CORRECTIONS (no BLOCKER/HIGH). Findings were fixed in the workspace (see `docs/P29_REVIEW_REMEDIATION_REPORT.md`) and everything above was re-run: the table in section 1 and the
stress repeats in section 3 are the **post-remediation** numbers (the pre-remediation run was 1523 / 1522 + 1 skipped and 66 stress tests).

* Mutation checks of the new regression tests: 13 mutants (see the remediation report) were applied in place with `PYTHONDONTWRITEBYTECODE=1` and then restored; all 13 were KILLED, 0 survivors. A first pass was confused by a stale `.pyc`
  (a same-size mutant written in the same second as the original compile); every `__pycache__` was cleared and the suite re-run before any result was trusted.
* The F-5 flake was reproduced before fixing: the old order-dependent assertions failed in 10 of 64 parallel in-process demo runs; the keyed assertions pass 64 of 64 (and in 3 further repetitions per Python).
* Packaging re-run: `python -m build --outdir <scratch>/dist .` then `scripts/verify_release_artifacts.py` in full (including sdist install, HTTP and OTel extras and the installed-wheel strict mypy): every step ok; the wheel contains 26 judge files (19 modules, 5 rubrics, 2 schemas). Nothing was published.
* Import isolation after the change: importing the namespace (and its `testing` module) loads no non-stdlib module outside `agent_reliability`; `tests/security` and `tests/compat`: 53 passed.
* Baseline-hash guard: the only workspace files that differ from `docs/P29_WORKSPACE_BASELINE.sha256` are the 8 documented documentation/script edits; no `src/` file outside `experimental/judge/` and no `pyproject.toml` change. File modes of the overlay files are identical to the original tree
  (README.md, pyproject.toml, ci.yml and verify_release_artifacts.py are 0755 in both because the uncommitted P28 work changed them from 0644; this work changed no mode).
* Original SDK tree: still only the P28 overlay set plus D-1 files added by another session (now also `docs/P28_SDK_D1_TARGETED_VERIFICATION.md`); no P29 file is present there. Platform integration worktree `git status --porcelain` line count: 51 (unchanged).
* Still **not run**: the platform check without the two environment variables (skipped in a default run), any benchmark or load test, a real model or provider, any platform or shared environment, the CI workflow, `mypy` on tests and examples.

## 10. Raw results log (post-remediation, copied from the run)

```text
=== 3.11 Python 3.11.17
ruff check: All checks passed!
ruff format --check: 239 files already formatted
mypy src: Success: no issues found in 65 source files
pytest (platform check enabled): 1548 passed in 17.29s
pytest (default, no platform): 1547 passed, 1 skipped in 16.47s
stress/concurrency repeat 1: 82 passed in 5.34s
stress/concurrency repeat 2: 82 passed in 4.78s
stress/concurrency repeat 3: 82 passed in 5.32s
existing suite only (tests minus P29 files): 856 passed, 209 deselected in 8.70s
=== 3.12 Python 3.12.15
ruff check: All checks passed!
ruff format --check: 239 files already formatted
mypy src: Success: no issues found in 65 source files
pytest (platform check enabled): 1548 passed in 17.67s
pytest (default, no platform): 1547 passed, 1 skipped in 14.88s
stress/concurrency repeat 1: 82 passed in 5.42s
stress/concurrency repeat 2: 82 passed in 4.91s
stress/concurrency repeat 3: 82 passed in 5.41s
existing suite only (tests minus P29 files): 856 passed, 209 deselected in 8.78s
=== 3.13 Python 3.13.16
ruff check: All checks passed!
ruff format --check: 239 files already formatted
mypy src: Success: no issues found in 65 source files
pytest (platform check enabled): 1548 passed in 17.65s
pytest (default, no platform): 1547 passed, 1 skipped in 16.67s
stress/concurrency repeat 1: 82 passed in 5.36s
stress/concurrency repeat 2: 82 passed in 5.85s
stress/concurrency repeat 3: 82 passed in 5.79s
existing suite only (tests minus P29 files): 856 passed, 209 deselected in 9.34s
```

Note: after the remediation report and log were added, `ruff format --check .` reports 240 files already formatted (Markdown files with Python blocks are counted); the table above is the count at the time of the run.


## 11. Re-sync of the P28-owned overlay and re-run (2026-10-16, after sections 1-10)

Sections 1 to 10 describe the tree **before** the re-sync (the state the independent reviewers examined). After the P28 overlay re-sync (`docs/P29_WORKSPACE_BASELINE.md`, section "Re-sync") everything was re-run. The numbers below are the **current**, post-re-sync, author-run results.
Independent verification status: the reviewers verified the pre-re-sync tree; the re-sync evidence is author-run.

Additional setup: the re-synced `pyproject.toml` adds the dev-only dependency `cryptography>=42` (P28's real-TLS tests generate their certificates); the three venvs were refreshed with `uv pip install -e ".[dev,otel-test,http]"` (cryptography 50.0.2).

| Python | ruff check | ruff format --check | mypy src (strict) | pytest, platform check enabled | pytest, default | stress set x3 | pre-existing suite alone |
|---|---|---|---|---|---|---|---|
| 3.11.17 | All checks passed | 244 files already formatted | no issues, 65 files | 1549 passed | 1548 passed, 1 skipped | 98 passed x3 | 857 passed |
| 3.12.15 | All checks passed | 244 files already formatted | no issues, 65 files | 1549 passed | 1548 passed, 1 skipped | 98 passed x3 | 857 passed |
| 3.13.16 | All checks passed | 244 files already formatted | no issues, 65 files | 1549 passed | 1548 passed, 1 skipped | 98 passed x3 | 857 passed |

* The "pre-existing suite alone" count is 857 (was 856): it now includes the D-1 real-TLS test file (the P28 remediation report states 857 passed on each Python). The stress set (98 tests) now also includes `tests/unit/test_http_exporter_tls_real.py`.
* Exporter-dependent P29 tests (S09 wire conformance including the read-only platform V2 model check, S11 demo/capture/replay): 29 passed against the D-1-fixed exporter; the exporter source was byte-identical to the baseline (the D-1 `_failure()` fix was already in the first baseline).
* Packaging: `python -m build --outdir <scratch>/dist .` and the full `scripts/verify_release_artifacts.py` (now including `_assert_no_private_keys`): every step ok; the wheel holds 26 judge files and no key or fixture file. Nothing was published.
* Import isolation: importing the namespace loads no non-stdlib module; `tests/security` and `tests/compat`: 53 passed.
* Baseline guard (`docs/P29_WORKSPACE_BASELINE_RESYNC.sha256`): the only entries that differ are the 8 documented P29 documentation/script edits. The hash-pinned `sdk/context.py`, `sdk/evaluator_runner.py` and `ports/event_sink.py` were unchanged upstream.
* Platform check ran read-only through the existing scratch venv against the integration worktree (platform dependencies were already installed; no package access was needed); that worktree's `git status --porcelain` line count is unchanged (51).
* Still not run: benchmark/load, real model or provider, any platform or shared environment, the CI workflow, `mypy` on tests/examples, the platform check without the two environment variables (skipped in a default run).

### Raw results log (post-re-sync)

```text
=== 3.11 Python 3.11.17
ruff check: All checks passed!
ruff format --check: 244 files already formatted
mypy src: Success: no issues found in 65 source files
pytest (platform check enabled): 1549 passed in 15.86s
pytest (default, no platform): 1548 passed, 1 skipped in 12.89s
stress/concurrency repeat 1: 98 passed in 8.47s
stress/concurrency repeat 2: 98 passed in 8.96s
stress/concurrency repeat 3: 98 passed in 8.79s
existing suite only (tests minus P29 files): 857 passed, 209 deselected in 6.56s
=== 3.12 Python 3.12.15
ruff check: All checks passed!
ruff format --check: 244 files already formatted
mypy src: Success: no issues found in 65 source files
pytest (platform check enabled): 1549 passed in 16.10s
pytest (default, no platform): 1548 passed, 1 skipped in 13.45s
stress/concurrency repeat 1: 98 passed in 9.55s
stress/concurrency repeat 2: 98 passed in 9.15s
stress/concurrency repeat 3: 98 passed in 9.60s
existing suite only (tests minus P29 files): 857 passed, 209 deselected in 6.70s
=== 3.13 Python 3.13.16
ruff check: All checks passed!
ruff format --check: 244 files already formatted
mypy src: Success: no issues found in 65 source files
pytest (platform check enabled): 1549 passed in 15.92s
pytest (default, no platform): 1548 passed, 1 skipped in 14.16s
stress/concurrency repeat 1: 98 passed in 10.25s
stress/concurrency repeat 2: 98 passed in 9.37s
stress/concurrency repeat 3: 98 passed in 9.45s
existing suite only (tests minus P29 files): 857 passed, 209 deselected in 6.39s
```
