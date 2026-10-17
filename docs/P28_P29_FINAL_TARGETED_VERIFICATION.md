# P28 / P29 final targeted verification (2026-10-17)

Independent verifier (fresh context). Scope: only the remediation applied after
`P28_P29_FINAL_INDEPENDENT_REVIEW.md`; the review was not redone. Experiments ran in
`<tmp>/` on copies (module `__file__` asserted); only the rebuilt environments in
`<envs>` were used. Nothing was committed, pushed or edited elsewhere. My own test runs
created `.hypothesis/` directories in three trees; I deleted them.

## Verdict: VERIFIED (no blocking or functional defect; 2 INFO test-coverage gaps, 2 INFO wording slips)

## 1. Fixes against the files

| ID | Result |
|---|---|
| L-3 guards | Present in both `scripts/verify_release_artifacts.py`. Marker is `PRIVATE KEY`. Local-path markers: `/Users/`, `/private/tmp/`, `/var/folders/`, `/home/`, plus Windows plain, JSON-escaped and forward-slash forms, matched case-insensitively. `_assert_no_internal_files` is present and called, with the two-document allowlist (`docs/P29_PILOT_RUNBOOK.md`, `docs/P29_PILOT_SAFEGUARDS.md`). The two scripts differ only in the judge-specific assertions (final has them, P28-only does not). `tests/unit/test_release_artifact_guards.py` is byte-identical in both trees and has 30 tests. |
| L-4 | Verified. `spoofed`/`uuid4` are gone from the characterization file. The remaining assertions are valid: `organization_id=None` is logged, the asserted actor is logged, and the token is absent from the log. |
| L-5 | Final CHANGELOG has the P29 experimental entry. The only diff between the two CHANGELOGs is that entry. Both packaging bullets describe the guards (private keys, local paths, internal files, planted-case tests). |
| L-6 | `docs/P29_PILOT_SAFEGUARDS.md` now says "quoted or condensed (meaning preserved)". |
| I-1 | The README says the released 1.2.1 package includes no LLM judge and points to the "experimental, unreleased" section below it. |
| Hash manifest | `docs/P29_WORKSPACE_BASELINE_RESYNC.sha256`: the CHANGELOG.md, `scripts/verify_release_artifacts.py`, HTTP_EXPORTER.md and pyproject.toml entries equal the current files. The only entries that do not match the files are README.md, EVALUATE.md, GA_CONTRACT.md, ROADMAP.md, VERSIONING.md and two ADR files. These are P29-edited files, and their entries are identical to the original `P29_WORKSPACE_BASELINE.sha256`. That is the convention in RECONCILIATION sections 3 and 5, so no P29-owned entry changed. |
| L-1 / L-2 | Only recorded, as stated. |

## 2. Guards: planted cases and false positives

Both SDK trees were built on scratch copies (hatchling, Python 3.13).
- `python scripts/verify_release_artifacts.py` exited 0 in both trees (metadata/contents, base wheel and examples, sdist install, http extra, otel extra, downstream strict mypy).
- Counts: final sdist 268 and wheel 77 (80 judge-named members, including the 26 judge files in the wheel). P28-only sdist 199 and wheel 51, with 0 judge files. These are the earlier 267/198 plus exactly the new test file.
- The final sdist contains only `docs/P29_PILOT_RUNBOOK.md` and `docs/P29_PILOT_SAFEGUARDS.md` under `docs/P*`. There is no CLAUDE.md, AGENTS.md or `docs/evidence`.
- Neither artifact contains any literal marker (grep over the extracted sdists returned 0). The test file and the scripts assemble the markers from pieces.

Planted cases were run through `_inspect_artifacts` in both trees. The results were identical in the two trees:

| Planted case | Result |
|---|---|
| Clean artifacts | pass (no false positive) |
| PEM RSA, PKCS8 and OpenSSH key blocks (sdist and wheel) | CAUGHT |
| PGP key block | CAUGHT |
| `.pem` file name (sdist, and wheel in upper case) | CAUGHT |
| Unix home path | CAUGHT |
| `/home/` path | CAUGHT |
| macOS `/private/tmp` path | CAUGHT |
| `/var/folders` path | CAUGHT |
| Windows path: backslash, lower-case JSON-escaped, forward-slash | all 3 CAUGHT |
| Nested `docs/sub/CLAUDE.md`, nested `src/AGENTS.md` | CAUGHT |
| `docs/evidence/` | CAUGHT |
| New `docs/P29_NEW_REPORT.md`, `docs/P31_X.md` | CAUGHT |
| `docs/P29_PILOT_RUNBOOK.md` | allowed, as required |
| Wheel `docs/` member, wheel `CLAUDE.md` | CAUGHT |
| Wheel `tests/` member | CAUGHT (by the older repository-only check) |

Mutants on copies of the final tree, run against `tests/unit/test_release_artifact_guards.py`:

| Mutant | Result |
|---|---|
| Local-path scan disabled | KILLED |
| Internal regex narrowed to the root only | KILLED |
| Allowlist check removed | KILLED |
| Allowlist made permissive | KILLED |
| Key marker reverted to the narrow `-----BEGIN PRIVATE KEY-----` | KILLED |
| `/var/folders` marker dropped | KILLED |
| Windows JSON-escaped marker dropped | KILLED |
| Windows case-insensitivity removed | KILLED |
| `docs/evidence/` check removed | KILLED |
| Wheel `docs/` check removed | KILLED |
| `.pem` suffix dropped | KILLED |
| Wheel private-key scan dropped | KILLED |
| Windows forward-slash marker dropped | SURVIVED (equivalent: `C:/Users/` is still matched by the `/Users/` marker) |
| `/private/tmp/` marker dropped | SURVIVED (no test) |
| `/home/` marker dropped | SURVIVED (no test) |

The four mutants you required were all killed. The three survivors do not affect the claim, because the real guard catches all three planted cases (see the table above). They are INFO findings (section 5).

## 3. Re-run results

- Final SDK full suite, Python 3.11.17 / 3.12.15 / 3.13.16: 1,594 passed, 1 skipped each.
- P28-only SDK suite on the same three versions: 900 passed each.
- Editable installs resolve to the right trees (final, P28-only and platform-final).
- ruff check, `ruff format --check` and `mypy src`: final 258 files formatted and 65 source files; P28-only 196 files formatted and 46 source files. All clean.
- Platform-final: ruff and format clean (551 files), mypy 138 files clean, unit+property 1,164 passed, characterization file 4 passed.
- Extra checks:
  - Fixture hashes: 4 verified; with `--platform-root` the platform comparison is True.
  - Node reference check: 76 canonical and 74 acknowledgement vectors.
  - 24 wire-conformance tests pass with `P29_PLATFORM_ROOT` and `P29_PLATFORM_PYTHON` set.
  - `p29_sg_evidence.py` reports "ALL SAFEGUARDS NOT SATISFIED".
- Integrity:
  - `http_event_sink.py`, `_http_delivery.py` and `_http_protocol.py` are byte-identical between the two SDK trees.
  - Final SDK versus `freeze2_sdk_final.txt`: the file set is identical and all files hash-match except `docs/P28_P29_FINAL_COMPLETION_REPORT.md` and `docs/evidence/README.md`. Both are docs, edited after the freeze.
  - No `src/` file in either SDK tree is newer than the freeze. The P28-only manifest (47 entries, 7 under `src/`) is all OK, and no file in that tree is newer than the freeze.
  - Platform-final versus `freeze2_platform_final.txt`: file set identical, all 632 hashes OK.
  - The originals are untouched.
  - Not re-run: PostgreSQL integration and E2E (accepted from the review, since no runtime code changed).

## 4. Completion report `P28_P29_FINAL_COMPLETION_REPORT.md`

Everything below checked out.
- Section 5: 900 tests, 199/51, no judge files, ruff/format/mypy clean.
- Section 8: 268/77, 26 judge files, the exclusions, the guard list and the 30 planted-case tests.
- Section 9: Python 3.11.17/3.12.15/3.13.16, 900 and 1,594 + 1 skipped, 46/65 files, 4 fixture hashes, 76/74 vectors, 24 wire tests.
- Sections 12 and 16: the finding dispositions match the review register, and L-3 to L-6 and I-1 are actually fixed. Section 16 states "None of these is approved".
- The report makes no release, pilot, calibration, real-model or approval claim. Every such item is "not performed", "NOT SATISFIED" or "no".
- `TARGETED_VERIFICATION_PLACEHOLDER` was ignored.

Wording slips (INFO, both inherited from the review text):
- Section 12 says "18 mutants: 15 killed, 3 detected only by harness, 1 equivalent", which sums to 19. The review's table has 14 killed, 3 guard mutants and 1 equivalent (18). Fix: "14 killed".
- Section 7 says SG requirements are "exactly ... quoted", which contradicts the corrected "quoted or condensed" in the safeguards doc. Fix: align the wording.
- Section 2 and the section 12 note cite `<scratch>` manifests that no longer exist. Section 12 already explains the deletion and the regenerated `freeze2_*` manifests.

## 5. New defects

No LOW or higher defects.

- INFO-A: `tests/unit/test_release_artifact_guards.py` has no planted case for `/private/tmp/` or `/home/`, so removing those markers survives. The real guard catches both today. Fix: add two parametrized cases.
- INFO-B: the Windows forward-slash marker is redundant with the `/Users/` marker. It is harmless and could be dropped or documented.
- INFO-C: the scan is a denylist of literal markers. For example, it does not catch other usernames or `~/`. This is as designed and was already noted in the review (L-3).

VERDICT: VERIFIED.
