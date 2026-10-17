# P29 SDK workspace baseline

Status: working record for the P29 V1 SDK implementation workspace. Local only. Nothing in this workspace is committed, pushed,
released or deployed. This file records how the baseline was built and what it contained BEFORE any P29 change. It does not
claim independent verification.

Date of construction: 2026-10-16.

## 1. Source and construction

* Source tree (READ-ONLY, never modified by this work): `<workspace>/agent-reliability`
  (SDK; branch HEAD `7aa6883b6dcc5ae171f40fae570e8ee80fe88a68` "chore(release): prepare 1.2.1"; working tree carries
  uncommitted P28 exporter work).
* Workspace: `<workspace>/agent-reliability-p29` (outside all active worktrees).
* Commands (run from `<workspace>`):

```sh
git clone --no-hardlinks -q agent-reliability agent-reliability-p29      # read-only on the source; checks out 7aa6883
cd agent-reliability-p29
git remote remove origin                                                  # the workspace cannot push anywhere
git checkout -q -b p29-sdk-v1-local                                       # local branch name only; no commit made
# overlay the uncommitted state (modified + untracked, ignore rules respected, no .git/.venv/caches/dist):
(cd ../agent-reliability && git ls-files -m -o --exclude-standard -z) | rsync -a --from0 --files-from=- ../agent-reliability/ ./
```

* The overlay therefore consists of exactly the files `git ls-files -m -o --exclude-standard` reports in the source tree
  (28 status lines at construction, 43 files because `tests/fixtures/` is a directory with 16 files). Ignored paths
  (`.venv/`, `.mypy_cache/`, `.pytest_cache/`, `.ruff_cache/`, `.hypothesis/`, `.coverage`, `dist/`, `__pycache__/`) were NOT copied.
* Overlay checksums: `shasum -a 256` of every overlaid file in the source, taken before the clone, compared with the same
  command in the workspace after the overlay: identical (diff empty).
* Manifest of the whole baseline (every tracked and untracked file, taken before any P29 edit): `docs/P29_WORKSPACE_BASELINE.sha256`
  (214 files; one self-referential line was removed). Anything that differs from that manifest, other than files listed in `docs/P29_IMPLEMENTATION_LOG.md`, is a defect of this work.

### 1.1 Overlaid files (uncommitted P28 exporter work; independent of P29; neither reverted nor counted as P29 change)

Modified (10): `.github/workflows/ci.yml`, `README.md`, `docs/ARCHITECTURE.md`, `pyproject.toml`, `scripts/verify_release_artifacts.py`,
`src/agent_reliability/adapters/event_sinks.py`, `src/agent_reliability/ports/event_sink.py`, `src/agent_reliability/sdk/client.py`,
`src/agent_reliability/sdk/context.py`, `tests/compat/test_public_api_1_1.py`.

Untracked (17 status entries): `AGENTS.md`, `CLAUDE.md`, `docs/HTTP_EXPORTER.md`, `docs/P28_SDK_EXPORTER_{IMPLEMENTATION_REPORT,INDEPENDENT_REVIEW,OWNER_DECISIONS_001,REMEDIATION_REPORT,TARGETED_VERIFICATION}.md`,
`scripts/verify_p28_fixtures.py`, `scripts/verify_p28_reference.mjs`, `src/agent_reliability/adapters/{_http_delivery,_http_protocol,http_event_sink}.py`,
`tests/contract/test_p28_http_protocol.py`, `tests/fixtures/` (16 files: `p28/`, `tls/`), `tests/unit/test_http_exporter.py`,
`tests/unit/test_http_exporter_review_regressions.py`, `tests/unit/test_http_exporter_tls_real.py`.

Per-file SHA-256 of all of these is in `docs/P29_WORKSPACE_BASELINE.sha256`.

### 1.2 Pre-P29 hashes of files P29 must not change (plan P29-S05-AC09(d); HEAD is NOT the baseline for `sdk/context.py`)

| File | SHA-256 at baseline |
|---|---|
| `src/agent_reliability/sdk/context.py` | `3687873a1bf3d2d80ce8b5820bb5052f00930c63bbc63c6cb70643a265a7d5bb` |
| `src/agent_reliability/sdk/evaluator_runner.py` | `d4354eca6fc23629ebd65b8232791f34682a02568b4b4934b3eb9f6ca841de59` |
| `src/agent_reliability/evaluation/__init__.py` | `e52fe46a651498633d15296256ded867ac4384e04144b3ac473f4d328fa433a1` |
| `src/agent_reliability/evaluation/_validation.py` | `8733f2b1f09896d3df44a313e26aabcbb2ea6b63572e81a2a4fe7bb36760dce9` |
| `src/agent_reliability/evaluation/identity.py` | `01f2ad6f7b2573445ab5ab96902d29c3e2ba1bd32ebc739a3c4181397e7880c9` |
| `src/agent_reliability/evaluation/protocols.py` | `0766e51957fa3ef0fc8e1523d719487518d9dc2e032879ab02990c3f3ef96c2d` |
| `src/agent_reliability/evaluation/result.py` | `204f021525d379d77010205f0088ce49669da5b375763168f1d27ef604371583` |
| `src/agent_reliability/ports/event_sink.py` | `9d9af2dade8121e696b96050377fef9928e9c8a0a17d379b9fae46a0357294fd` |
| `tests/compat/test_public_api_1_0.py` | `6bf6375c3998e1d00822c844d29575adcd1f0e401d858d151bfae004a09e3dec` |
| `tests/compat/test_public_api_1_1.py` | `a8ade145f2a7b36f1d96704190fa376fad10447a5da15ad29a4290eafa0607ed` |
| `tests/compat/test_public_api_1_2.py` | `3c68cae5214adc4e8325bb35f2248e0a41c5625297c9dd3e6f49964b5348cdcd` |

## 2. Source-tree protection check

Before any work, the source tree's `git status --porcelain` and the SHA-256 of every modified and untracked file were saved; after
construction and after baseline verification they were compared with the saved copies: identical (`ORIG_UNCHANGED`). The check is repeated
in the final report of this work. No `git reset`, `stash`, `checkout`, format or other write was performed in any original worktree. The
P29 design documents under `agent-reliability-platform/docs/roadmap/P29/` were only read; they were being edited concurrently by another
agent, so the text used is the snapshot read on 2026-10-16 (SHA-256 of that snapshot at the time of reading):

    0e0cbbd2fa2d229c9656c98ada259d53b205240d02eabddaed22615105785f09  P29_CALIBRATION_AND_TEST_STRATEGY.md
    ee5b1f682d3471b6b708a8d48c0b26947ff7fa50c5def751debfe6b9331fffb6  P29_CORRECTION_REPORT.md
    7bf1db28f87dc96ffa8bc5b2862d9f5ddc6e535cde4471901b9b29fa1813eb09  P29_EVALUATION_CONTRACT.md
    7e31a6ca435e2670aafefdc4d1aaacdd462c45093bc7fada6b0b38a490460951  P29_IMPLEMENTATION_PLAN.md
    9ea65b599228a713e4607c878af036bea323751d85214a114fae612652a4a8db  P29_NATIVE_EVALUATION_ARCHITECTURE.md
    30e3fea4fabb1c61a0af50d25af63764727cb67b3eccbeb4e816b5d064c6061a  P29_OPEN_DECISIONS.md
    4a6a5dbc87690b1d12f932185e3acf01ce9fe898cb614a1ae19f5c1ae6d03925  P29_OWNER_DECISIONS_001.md
    e8f0c9d70d5317f4e6fdc9f5cd6d3509a72eb84e4f5dc1af1c294c7de75ada48  P29_SECURITY_PRIVACY_REVIEW.md

## 3. Python environments (outside the repository tree)

uv 0.13.1 (`/opt/homebrew/bin/uv`); the source tree's `.venv` was not used. Supported versions per `pyproject.toml`
`requires-python = ">=3.11"` and CI matrix `["3.11", "3.12", "3.13"]` (`.github/workflows/ci.yml`).

```sh
mkdir -p ~/.venvs-p29
for v in 3.11 3.12 3.13; do uv venv -q --python $v ~/.venvs-p29/py$v; done
for v in 3.11 3.12 3.13; do uv pip install -q --python ~/.venvs-p29/py$v -e ".[dev,otel-test,http]"; done   # same extras as CI test job
```

The repository declares dev dependencies as lower-bounded ranges (no lock file), so "pinned as the repo does" means the same ranges; the
resolved set on 2026-10-16 (Python 3.11 venv) was: ruff 0.17.1, mypy 2.4.0, pytest 9.1.1 and the rest of `uv pip freeze` (29 packages).
Interpreters: CPython 3.11.17, 3.12.15, 3.13.16.

## 4. Baseline verification (before any P29 change)

Commands run from the workspace root, per interpreter (`V=~/.venvs-p29/py3.XX/bin`):

```sh
$V/ruff check .                      # CI step "ruff check ."
$V/ruff format --check .             # CI step "ruff format --check ."
$V/mypy src                          # CI step "mypy src" (strict, per pyproject)
$V/python scripts/verify_p28_fixtures.py
$V/python -m pytest -q -p no:cacheprovider
```

| Python | ruff check | ruff format --check | mypy src | pytest |
|---|---|---|---|---|
| 3.11.17 | All checks passed | 187 files already formatted | no issues in 46 source files | 856 passed |
| 3.12.15 | All checks passed | 187 files already formatted | no issues in 46 source files | 856 passed |
| 3.13.16 | All checks passed | 187 files already formatted | no issues in 46 source files | 856 passed |

`verify_p28_fixtures.py`: "4 fixture hashes verified; platform comparison: False" (no platform checkout supplied). Pre-existing failures: none.
Not run at baseline: `scripts/verify_release_artifacts.py` (builds wheel/sdist; needs network/isolated envs), the `.github` workflow itself.


## Re-sync (2026-10-16, after the P28 D-1 remediation and release review in the original tree)

Why: while P29 part 2 and the review remediation ran, other sessions changed the **original** SDK tree (P28 overlay). This section re-syncs only the P28-owned overlay files into the workspace. The original tree was only read
(snapshot taken 2026-10-16T21:34:51+0530; the original may keep changing, and `git status --porcelain` there showed 33 entries at that moment; HEAD is still `7aa6883b6dcc5ae171f40fae570e8ee80fe88a68`).

### What drifted (per-file sha256, original overlay set at the first snapshot versus now)

| File | Change in the original | sha256 before (workspace baseline) | sha256 after (original now) | workspace after |
|---|---|---|---|---|
| `CHANGELOG.md` | added | `-` | `4574ffe9a636` | `4574ffe9a636` |
| `docs/HTTP_EXPORTER.md` | changed | `229c075916c1` | `64fd040a67f5` | `64fd040a67f5` |
| `docs/P28_SDK_D1_INDEPENDENT_REVIEW.md` | added | `-` | `72eba208c49a` | `72eba208c49a` |
| `docs/P28_SDK_D1_REMEDIATION_REPORT.md` | added | `-` | `a8679ca32fb8` | `a8679ca32fb8` |
| `docs/P28_SDK_D1_TARGETED_VERIFICATION.md` | added | `-` | `8ae0011ead82` | `8ae0011ead82` |
| `docs/P28_SDK_EXPORTER_RELEASE_REVIEW.md` | added | `-` | `84d5e0bbe3e3` | `84d5e0bbe3e3` |
| `pyproject.toml` | changed | `3c4b4008ee29` | `6ad690c1a817` | `6ad690c1a817` |
| `scripts/verify_release_artifacts.py` | changed | `8b3fc02371ee` | `b94f100188ad` | `92ee63ceacef` |
| `tests/fixtures/tls/README.md` | removed | `c0f88df237bf` | `-` | `(removed)` |
| `tests/fixtures/tls/ca.crt` | removed | `b2463f4eafdb` | `-` | `(removed)` |
| `tests/fixtures/tls/expired.crt` | removed | `b5cc0ccad447` | `-` | `(removed)` |
| `tests/fixtures/tls/expired.key` | removed | `34354472a9cd` | `-` | `(removed)` |
| `tests/fixtures/tls/generate.py` | removed | `401ffd7fb7fa` | `-` | `(removed)` |
| `tests/fixtures/tls/localhost.crt` | removed | `a49cf8a61cf5` | `-` | `(removed)` |
| `tests/fixtures/tls/localhost.key` | removed | `efefb44c3602` | `-` | `(removed)` |
| `tests/fixtures/tls/other.crt` | removed | `9bef787003f0` | `-` | `(removed)` |
| `tests/fixtures/tls/other.key` | removed | `cbee58967324` | `-` | `(removed)` |
| `tests/fixtures/tls/selfsigned.crt` | removed | `13bf3983ded8` | `-` | `(removed)` |
| `tests/fixtures/tls/selfsigned.key` | removed | `3998d2c6544e` | `-` | `(removed)` |
| `tests/unit/test_http_exporter_tls_real.py` | changed | `16b7a35e6169` | `5d89929866b8` | `5d89929866b8` |

Not drifted (hash-identical to the baseline): `src/agent_reliability/adapters/http_event_sink.py` (the D-1 `_failure()` fix was **already present** in the first baseline: sha256 prefix `ddabd121d3e2`), `_http_delivery.py`, `_http_protocol.py`,
`sdk/context.py`, `sdk/evaluator_runner.py`, `ports/event_sink.py`, `ports/` and `adapters/` files, `tests/compat/*`, `tests/fixtures/p28/*`. What changed upstream is test infrastructure, packaging guard, documentation and reports:
the real-TLS test now generates its certificates at test time (so the throwaway `tests/fixtures/tls/*` files, including four private keys, were removed upstream), `pyproject.toml` gained the dev-only `cryptography>=42` (inside the `dev` extra, no runtime dependency),
`scripts/verify_release_artifacts.py` gained `_assert_no_private_keys`, `docs/HTTP_EXPORTER.md` defines "consecutive", `CHANGELOG.md` gained an `[Unreleased]` entry, and four P28 review/verification documents were added.

### Commands (workspace side; the original was never written)

```sh
# snapshot of the original overlay set and hashes (read-only)
cd <workspace>/agent-reliability && git ls-files -m -o --exclude-standard | sort | xargs shasum -a 256 > <scratch>/orig_new.sha
# compare with the first snapshot (<scratch>/hash_before.txt): ADDED / REMOVED / CHANGED (table above)
cd <workspace>
for f in CHANGELOG.md docs/HTTP_EXPORTER.md pyproject.toml tests/unit/test_http_exporter_tls_real.py \
         docs/P28_SDK_D1_INDEPENDENT_REVIEW.md docs/P28_SDK_D1_REMEDIATION_REPORT.md \
         docs/P28_SDK_D1_TARGETED_VERIFICATION.md docs/P28_SDK_EXPORTER_RELEASE_REVIEW.md; do
  rsync -a agent-reliability/$f agent-reliability-p29/$f; done                 # modes preserved
rm -rf agent-reliability-p29/tests/fixtures/tls                                   # removed upstream
# scripts/verify_release_artifacts.py: three-way reconcile (below)
uv pip install --python ~/.venvs-p29/py3.XX -e ".[dev,otel-test,http]"           # picks up the new dev-only dependency (cryptography 50.0.2)
```

### Three-way reconciliation of the one file both sides edited

`scripts/verify_release_artifacts.py`: base = the file as of the first baseline (sha256 `8b3fc02371ee...`), theirs = the original now (`b94f100188ad...`, adds `_assert_no_private_keys`), ours = P29 (wheel must contain the judge package, rubrics and schemas; base-wheel probe loads the rubrics).
Resolution: started from **their** file and re-applied the two P29 additive hunks at the same anchors; the result (`92ee63ceacef...`) differs from the original only by those hunks (22 changed lines). No other P29-edited file (README.md, docs/EVALUATE.md, GA_CONTRACT.md, ROADMAP.md,
VERSIONING.md, ADR-0007, adr/README.md) changed upstream, so nothing else needed reconciling; none of them was overwritten.

### New baseline manifest and guards

`docs/P29_WORKSPACE_BASELINE_RESYNC.sha256` (207 entries) is the old manifest updated with the original-now hashes of the overlay files above (removed entries dropped, added entries added); entries of P29-edited files keep their **pre-P29** content hash,
except `scripts/verify_release_artifacts.py`, which carries the upstream (pre-P29) hash of the new original. The old manifest is kept unchanged for history.
The hash-pinned guards now read the re-synced manifest through `tests/fakes/p29_baseline.py::load_baseline` (RESYNC preferred, original manifest as fallback): the compat snapshot guard, "no pre-existing `src` module modified by P29", the P29-S05-AC09(d) `RunHandle`/`EvaluatorRunner`/`ports/event_sink.py` guard and the S09-AC06 P28 fixture/document guard.
No pinned hash had to change: `sdk/context.py` (`3687873a...`), `sdk/evaluator_runner.py` (`d4354eca...`) and `ports/event_sink.py` (`9d9af2da...`) are byte-identical in the original now, so the guard still proves that P29 changed no pre-existing `src` module (the 8 files that differ from the manifest are the documented P29 documentation/script edits).
`test_p29_s09_ac06` previously listed `tests/fixtures/tls/*` implicitly via the manifest; those entries are gone with the files.

### Results after the re-sync

See `docs/P29_TEST_EVIDENCE.md` section 11. Summary: ruff, format, mypy clean on 3.11/3.12/3.13; 1549 passed (platform check enabled) and 1548 passed + 1 skipped (default) per Python; the pre-existing suite alone 857 passed (it includes the D-1 real-TLS tests; the P28 report states 857); stress set x3 passed; full `verify_release_artifacts.py` (now with the private-key guard) passed.
