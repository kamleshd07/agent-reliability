# Compatibility report (author-run; independent re-execution is the validator's, see `reviews/`)

Head under test: see the PR. Baseline: SDK `origin/main` b887999 (1802 passed, 1 skipped on Python 3.11 before any change).

## What changed in existing code (all additive, all Experimental)

Only files under `src/agent_reliability/experimental/judge/`: `coordinator.py` (admission hook, disposition, report kind, counters), `behaviour.py` (new),
`judge.py` and `sync.py` (a read-only `behaviour` property), `__init__.py` (new exports). `tests/compat/test_experimental_judge_api.py` gains snapshot entries
for the new names; no existing snapshot entry was changed. No stable module, `pyproject.toml` dependency list, P28 fixture, HTTP exporter, schema or wire
member was touched. `EvaluatorIdentity`, `EvaluationRecorded`, `MeasurementHealth` and the prompt template `jp1` are unchanged.

## Results observed by the author

| Check | Result |
|---|---|
| SDK suite, Python 3.11 / 3.12 / 3.13 | 1985 / 1983+ / 1983+ passed, 1 skipped each (see the final run recorded in `GO_NO_GO.md`) |
| `ruff check .`, `ruff format --check .`, `mypy src` | clean |
| `python -m build`; `scripts/verify_release_artifacts.py` (sdist + wheel install, HTTP/LangChain/OTel extras, strict downstream mypy) | passed; schemas are shipped in the wheel |
| Clean install of the built wheel with no extras | `requires` lists only extra-conditional requirements; calibration package and schemas import |
| `node scripts/verify_p28_reference.mjs` | 76 canonical vectors; 74 acknowledgement vectors passed |
| `scripts/verify_p28_fixtures.py --platform-root <platform main>` | 4 fixture hashes verified; platform comparison True |
| Platform `origin/main` 805b9c7 with this SDK installed editable (fresh disposable PostgreSQL database): `test_oss_evidence`, `test_oss_v1_1_contract`, `test_oss_e2e`, `test_postgres_p28_pc1`, `test_postgres_p28_pc2`, Session 2 `operational_semantics` / `operational_loop` | 140 passed, 1 xfailed |
| Platform unit + contracts trees with this SDK | only the 6 known default-settings tests fail, and only when `ARE_*` variables are exported (same on unmodified platform `main`) |
| Existing HTTP exporter regression tests and P29 contract vectors | part of the full SDK suite; unchanged and passing |

A first platform run against a *reused* local database failed 17 Session 2 tests with `column "redrive_count" does not exist`: the database had been
migrated by an earlier branch of the platform, not by `main`. A fresh database passes. This is an environment artefact unrelated to the SDK.

## Compatibility statements

* Default behaviour of every existing `IndicatorBinding`/`JudgeCoordinator` use is unchanged (the new field defaults to `None`; the new counters
  default to 0; `describe()` output gains three counters at the end).
* The Session 2 platform guard sees the same evaluator identity and the same evidence. A calibration gate that skips a judge produces *missing*
  evidence, which the guard already treats as no-data/insufficient-data and never as recovery.
* No new HTTP contract or fixture is introduced; the three file formats have published JSON Schemas for non-Python readers. A change to any of them
  would need its own version decision.
