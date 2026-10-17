# P28 / P29 final candidate - independent review (2026-10-17)

Reviewer: independent subagent (fresh context). This is a technical review, not a human approval and not a
governance sign-off. Read-only except this file; experiments ran on copies under
`<scratch>` (copy paths verified via `__file__`; `PYTHONDONTWRITEBYTECODE=1`,
`pytest -p no:cacheprovider`).

## Verdict

**NO BLOCKING FINDINGS.** 0 BLOCKER, 0 HIGH, 0 MEDIUM, 6 LOW, 6 INFORMATIONAL. The LOW items are
test-hygiene, guard-hardening and documentation-drift issues; none changes security behaviour. No
release, pilot, calibration, real-model or production-OIDC readiness is established or claimed by this review.

## 1. Freeze and tree integrity

* SDK final: `shasum -c freeze_sdk_final.txt` -> 296/296 OK, 296 files, no drift (before and after my runs).
* Platform final: `freeze_platform_final.txt` -> 632/632 OK, 632 files, no drift.
* Disclosure: my first test runs generated 156 `__pycache__` `.pyc` files and a `.hypothesis/` cache in the final
  SDK tree and 3 `.hypothesis` files in the P28-only tree (all gitignored, not in any manifest). I deleted exactly
  those generated artifacts afterwards; manifests re-verified clean. No source file was touched anywhere.
* Originals vs `base_*.txt` (sha256 of sorted modified + untracked): p29 118/118, p29-reconciled 126/126,
  platform-integration 142/142, platform 174/174: identical (0 diff lines).
* P28-only SDK `agent-reliability`: 44 -> 46 entries. Differences are exactly: CHANGELOG.md, docs/HTTP_EXPORTER.md,
  docs/GA_CONTRACT.md (newly modified), pyproject.toml, docs/P28_P29_RELEASE_GATE_CONSOLIDATION.md, and new
  docs/P28_SDK_EXPORTER_OWNER_DECISIONS_002.md. Matches the declared set.
* E2E workspace `gentlity-p28-e2e`: all 77 base hashes OK. Six `results/*/measurements-*.json` files exist that the
  base manifest does not list; their mtimes (2026-10-16) predate the base manifest (2026-10-17 00:12), so they are
  not changes made by this task (INFORMATIONAL I-5).

## 2. Platform-final vs verified integration worktree

`diff -r` (excluding caches) shows exactly: 7 files differ, 1 file only in final, and a `.hypothesis` cache dir only
in integration.
* 7 files byte-identical after removing CR (CR counts integration -> final: 0019 migration 445 -> 0, migration_runner
  116 -> 0, migration_safety_support 430 -> 0, test_migration_0019_safety 1254 -> 0, test_postgres_p28_pc2 1041 -> 0,
  test_p28_published_schema 184 -> 0, test_p28_evidence_v2 363 -> 0).
* Mode changes: 631 common files compared, exactly 89 changed (0755 -> 0644); none had a shebang; no executable
  file remains in the final tree.
* New: `tests/unit/api/test_p28_policy_characterization.py` (4 tests). Nothing else differs. No source behaviour change.
* Characterization tests assert what they claim (first-value-wins for duplicate Authorization and
  X-Organization-ID; request log carries `actor_id=asserted-actor` and `organization_id=None`; production refuses
  `dev_header`). They are labelled as non-endorsing. One assertion is vacuous (L-4).

## 3. Test and tool evidence (counts observed)

| Check | Result |
|---|---|
| Final SDK full suite, Python 3.11.17 / 3.12.15 | 1,564 passed, 1 skipped each |
| Final SDK, Python 3.13.16 | first run 1,563 passed, 1 failed (flaky `test_ids_are_not_sequential`, L-1); re-run 1,564 passed, 1 skipped |
| P28-only SDK, 3.11 / 3.12 / 3.13 | 870 passed each |
| ruff check / format --check / mypy src (final) | clean / 256 files formatted / 65 source files clean |
| ruff / format / mypy (P28-only) | clean / 195 files / 46 source files |
| `verify_p28_fixtures.py --platform-root <final>` | 4 fixture hashes verified; platform comparison True |
| `node scripts/verify_p28_reference.mjs` | 76 canonical vectors, 74 acknowledgement vectors passed |
| `tests/contract/test_p29_wire_conformance.py` with P29_PLATFORM_ROOT/PYTHON (final platform) | 24 passed |
| Platform final ruff / format / mypy | clean / 551 files formatted / 138 source files clean |
| Platform unit + property | 1,164 passed (9 warnings) |
| Platform integration, PostgreSQL 16.15, `-m "not slow"` | run 1 (concurrent with other heavy jobs): 508 passed, 1 failed (timing, L-2); run 2 (quiet): 509 passed, 3 deselected, 1 xfailed |
| E2E (real SDK + final platform), PostgreSQL 16.15 | 84 passed (113 s) |
| E2E, PostgreSQL 17.11 | 84 passed (112 s) |
| Final sdist extracted, tests run against its `src` | 1,559 passed, 6 skipped (5 extra skips = tests that read excluded internal logs) |
| P28-only sdist extracted | 870 passed |

Not re-run by me (not claimed): PostgreSQL 17 integration suite (512 passed in the report), PostgreSQL 18, Windows,
GitHub Actions, real forward proxy, connect-timeout, production-equivalent OIDC, real models, calibration.
The `typing`/`otel` smoke steps of `verify_release_artifacts.py` were skipped (`--skip-otel --skip-typing`);
base, sdist and http steps ran.

## 4. Packaging

Scratch builds (hatchling backend, from a uv cache, no index access) of copies of both trees:

| Artifact | sdist files | wheel files | notes |
|---|---|---|---|
| P28-only | 198 | 51 | 0 judge files; no P28 docs; verify script exit 0 |
| Final | 267 | 77 | 26 judge files in wheel; verify script passes (metadata/contents, base wheel + examples, sdist install, http extra mocked delivery) |

Matches report section 8. Over/under-exclusion: files in the source tree absent from the final sdist are exactly
CLAUDE.md, AGENTS.md, 17 `docs/P28_*`, eight P29 internal reports/baselines (ACCEPTANCE_MATRIX, IMPLEMENTATION_LOG,
INDEPENDENT_REVIEW, P28_RECONCILIATION, REVIEW_REMEDIATION_REPORT, TARGETED_VERIFICATION, TEST_EVIDENCE,
WORKSPACE_BASELINE*) and `docs/evidence/*`; P29_PILOT_RUNBOOK and P29_PILOT_SAFEGUARDS are kept. No kept document
or non-test source links to an excluded file (references exist only in test comments/skip logic).

Guard-defeat experiments (`verify_release_artifacts._inspect_artifacts` on doctored artifacts):

| Plant | Result |
|---|---|
| PEM private-key block (sdist src/ and wheel) | caught |
| `.pem` key file | caught |
| `/Users/...` path (sdist docs, wheel) ; `/private/tmp/` (wheel) | caught |
| CLAUDE.md at sdist root; `docs/P28_X`; `docs/P29_IMPLEMENTATION_LOG`; `docs/evidence/x` | caught |
| PGP `...PRIVATE KEY BLOCK-----` | NOT caught |
| JSON-escaped Windows path `C:\\Users\\x`; lowercase `c:\users\x`; `/var/folders/...` | NOT caught |
| nested `tests/CLAUDE.md`; new `docs/P29_FOO_REPORT.md`; wheel-side `CLAUDE.md` or `docs/P29_*` | NOT caught (internal-file check is sdist-only, root-anchored, denylist) |

These are denylist limits (L-3); the stated guarantees of the report (internal files named in F-9/P29 list, keys,
`/Users/`, `/private/tmp/`, `<tmp>`, `/home/`) hold.

## 5. Mutation results (on copies)

| # | Mutant | Result |
|---|---|---|
| 1 | judge: any non-unknown verdict maps to PASS (FAIL -> PASS) | KILLED (judge tests) |
| 2 | judge: low confidence -> PASS instead of UNKNOWN | KILLED |
| 3 | judge: model-produced `reason` text placed in the decision reason code (wire/payload member) | KILLED |
| 4 | judge: transient-failure retry bound removed | KILLED |
| 5 | judge: budget tracker check removed | KILLED |
| 6 | exporter: proxy CONNECT counted as "request sent" | KILLED (real-TLS tests, 95 s) |
| 7 | exporter: TLS streak not reset on success | KILLED |
| 8 | exporter: threshold 3 -> 4 | KILLED |
| 9 | exporter: TLS classification ignores `record.sent` | KILLED |
| 10 | release guard: local-path scan disabled | detected by my harness (2 plants pass); no in-repo test (L-3) |
| 11 | release guard: `docs/P28_` removed from internal regex | detected by harness (not by repo tests) |
| 12 | release guard: private-key marker / key-suffix check neutered | detected by harness (not by repo tests) |
| 13 | hatch exclude for `docs/P29_TEST_EVIDENCE.md` removed | KILLED by the release guard on the rebuilt sdist |
| 14 | platform: machine scope check (`context.require`) removed | KILLED (PG integration) - SURVIVED the unit/api subset (unit tests use a fake auth service) |
| 15 | platform: tenant-mismatch check removed | KILLED (unit/api) |
| 16 | platform: revoked credential accepted | KILLED (PG integration), survived unit subset |
| 17 | platform: token hash comparison removed | KILLED (PG integration), survived unit subset |
| 18 | platform: tenant taken from header when present | SURVIVED - equivalent mutant (header must equal credential tenant at that point) |

Result: 15 killed by repository tests, 3 guard mutants detected only by the reviewer harness, 1 equivalent survivor.
(One accidental overlap of two mutation runs was detected, sources were restored from the frozen tree and diffed
clean before rerunning the remaining mutants.)

## 6. Findings register

| ID | Sev | Location | Evidence | Impact | Reproduction | Remediation | Class |
|---|---|---|---|---|---|---|---|
| L-1 | LOW | tests/unit/adapters/test_adapters.py:39-43 | `assert not (a.endswith("0") and b.endswith("1"))` on random UUIDs; failed on 3.13 (`21e26f43-...3130`, `fa542228-...2b41`); same code in the P28-only tree | ~1/256 spurious CI failure of the exact "1,564 passed" gate | rerun `pytest tests/unit/adapters/test_adapters.py` repeatedly | drop the tail assertion or seed deterministically | pre-existing (defect in test) |
| L-2 | LOW | platform tests/integration/test_migration_0019_safety.py:1186 | `assert 1.5 <= outcome["elapsed"] < 90` got 1.23 s under concurrent load; passed solo 3x and in the quiet full run | spurious failure on loaded CI | run the suite alongside other CPU-heavy jobs | measure from lock-wait start or relax the bound | defect (test timing), PC-2 test |
| L-3 | LOW | scripts/verify_release_artifacts.py:122-203 | no test references the script; denylist bypasses in section 4 | guard regressions would be caught only when CI builds artifacts; listed bypasses | `defeat.py` harness in rev10 | add unit tests with doctored artifacts; also scan the wheel for internal names; add `PRIVATE KEY BLOCK`, escaped/lowercase Windows paths | optional |
| L-4 | LOW | platform tests/unit/api/test_p28_policy_characterization.py:89,104 | `spoofed = str(uuid4())` is never sent, so `assert spoofed not in lines` proves nothing | one claimed (header spoof not logged as identity) assertion is vacuous; other assertions are valid | read the test | send `spoofed` as `X-Organization-ID` or delete the assertion | defect (test), policy-neutral |
| L-5 | LOW | CHANGELOG.md [Unreleased] (lines 7-80) | no entry for the P29 experimental judge; sdist note lists only CLAUDE.md/AGENTS.md/`docs/P28_*`; guard note mentions only private keys | changelog understates final-tree content (P29 additions, P29 sdist exclusions, internal-file and local-path guards) | `grep -n -i judge CHANGELOG.md` (no match) | add P29 (experimental, unreleased) and guard entries when the release owner prepares notes | defect (documentation) |
| L-6 | LOW | docs/P29_PILOT_SAFEGUARDS.md header | says requirement text is "quoted"; SG-1/SG-2/SG-6 rows are condensed/paraphrased versus P29_OWNER_DECISIONS_001.md section 4 (e.g. SG-1 adds "budget exhaustion and overload"; SG-2 changes "the runbook states that" to "Pilot runbook note: one judge failure...") | meaning preserved, wording not verbatim; the SG record is the owner-facing source | compare lines 159-164 of the owner record | say "condensed from" or use verbatim text | defect (documentation) |
| I-1 | INFO | README.md:176-181 | "No remote ingestion ... LLM judge ... is included" precedes an "LLM-judge evaluators (experimental, unreleased)" section; exporter not mentioned | possible reader confusion; true for release 1.2.1 | read | clarify at release time | optional |
| I-2 | INFO | docs/P28_P29_RELEASE_GATE_CONSOLIDATION.md lines 103,193-194 | body still lists F-4/F-9 as READY_FOR_OWNER_DECISION / "pending F-9"; a top note (line 10) records the later decisions | stale rows, mitigated by the note | read | refresh rows when the document is next edited | optional |
| I-3 | INFO | pyproject.toml sdist exclude; DECISIONS_002 | sdist also excludes P29 internal reports and `docs/evidence`, wider than F-9; pyproject and packet item 11 state this honestly as "same rule applied" and not approved | no wider approval is claimed | read | owner decides (packet item 11) | owner decision |
| I-4 | INFO | platform security_service.py:640 | `authenticate_machine` takes `SELECT ... FOR UPDATE` on the credential row per request | concurrent requests of one credential serialize; no capacity claim is made or established here | read | consider `FOR NO KEY UPDATE`/no lock for the read path later | optional / pre-existing design |
| I-5 | INFO | E2E workspace | six older `results/*/measurements-*.json` files unlisted by the base manifest | none | see section 1 | none | n/a |
| I-6 | INFO | judge structured output | a reply wrapped in a ```json fence is accepted as valid; trailing text, duplicate keys, NUL in input, oversize input fail as execution failures (no verdict), and no canary appears in results/logs | lenient fence handling is a documented-behaviour question only | `canary.py` in rev10 | none | optional |

Also INFORMATIONAL: final-SDK core source files (`evaluation/*`, `reliability/*`) are LF while the P28-only working
tree has CRLF for the same content (diff ignoring CR is empty); owner-decision provenance statements ("the owner's
explicit statement in the user's instruction") cannot be verified by a reviewer and are correctly recorded as unsigned.

## 7. Areas checked and found sound

* Machine authentication (`dependencies.py`, `security_service.authenticate_machine`): prefix is dispatch only;
  hash compared with `hmac.compare_digest`; expiry/revocation/disabled principal checked; uniform 401 message;
  scope checked after authentication; tenant is credential-authoritative; `X-Organization-ID` optional and must
  match (403); `X-Actor-ID` ignored for machine principals; no human fallback after a failed machine check
  (including missing security service); a session cookie beside a machine bearer is ignored and CSRF not applied;
  human cookie-beats-bearer behaviour unchanged; `evidence:ingest` and `execution:ingest` separated; `dev_header`
  refused in production. All backed by the 30+ unit tests and PG integration tests (mutants 14-17).
* Schema-v2 ingestion, idempotency/conflict, bounds and persistence: unit+property (1,164) and PG integration
  (509) and E2E (84 on 16 and 17) pass; no discrepancy found.
* Exporter: `http_event_sink.py`, `_http_delivery.py`, `_http_protocol.py` are byte-identical between the P28-only
  and final trees (`cmp`); TLS classification, CONNECT rule, endpoint pause threshold/reset and per-exporter scope
  match owner decisions 002 (docs, code and tests agree; mutants 6-9 killed). F-4 documented as INTERNAL with
  entry points and no Beta class in `HTTP_EXPORTER.md` and `GA_CONTRACT.md`; F-9 implemented as recorded.
* Final vs P28-only SDK: non-judge differences are CR-only in four source files and eleven test files (diff ignoring
  CR is empty), pyproject (sdist exclude list and comment), the release script, and docs/examples for P29.
  `dependencies = []` unchanged; no new core dependency; no new wire fields (24 wire-conformance tests pass).
* Judge: PASS/FAIL/UNKNOWN mapping, failure-is-not-a-verdict, budgets/retries/limits (mutants 1-5 killed);
  privacy canaries (unicode, bidi override, 200 kB inputs, exception text and `reason` containing content) produced no
  leak in results, reprs or captured logs; NUL input rejected at construction without echoing; injection attempts in
  the reply (trailing text, duplicate keys) end as execution failures.
* ADR-0010 is the only file with that number; status reads "Accepted - owner-approved 2026-10-16, unsigned; number
  provisional", scope not widened; ADR README row matches; GA_CONTRACT labels the namespace EXPERIMENTAL/unreleased.
* P29 safeguards: all six NOT SATISFIED, roles described and unassigned, templates blank; `scripts/p29_sg_evidence.py`
  runs 12 mapped tests (SG-1 3, SG-2 2, SG-3 3, SG-4 1, SG-5 2, SG-6 1) all passed and reports
  "ALL SAFEGUARDS NOT SATISFIED (no pilot exists)". No accuracy, calibration or pilot claim was found in README,
  EVALUATE, runbook, HTTP_EXPORTER or CHANGELOG (reference rubrics are described as uncalibrated).

## 8. Final report accuracy (docs/P28_P29_FINAL_COMPLETION_REPORT.md)

Verified as stated: baselines and file counts (296/632), 7+89+4-test platform changes, 1,164 unit+property, 509 passed
/ 3 deselected / 1 xfailed on 16.15, platform ruff/mypy 138 files, 870 P28-only, 1,564 + 1 skip final (with the
caveat that 3.13 can show the L-1 flake), 46/65 mypy files, 4 fixture hashes, 76/74 Node vectors, 24 wire tests,
84 E2E on 16.15 and 17.11, sdist/wheel counts 198/51 and 267/77 with 26 judge files, guards behaviour, SG status,
mocked-provider vs real-platform vs real-model distinction (real-model, calibration, pilot, release: "not performed /
no"). Measurements are labelled development-machine values, not capacity. Nothing claims release or pilot readiness.
Not independently re-run by me: the 512-pass PostgreSQL 17 integration count, the P3/P4 hand-computed values (the
judge E2E tests passed), and the "idle cost about 0.4% of a core" measurement.
Section 16 (owner-decision packet) claims no approval: every row is "None of these is approved"; D14, ADR-0023 A.2,
F-2, audit retention, verified-identity logging, `dev_header`, duplicate headers, platform-first evidence,
commit/merge, versioning, release owner/reviewer, publication, SG-1..SG-6 and pilot all remain open, consistent with
DECISIONS_002 ("Not decided here") and the P29 owner record. Section 12 of the report is still the placeholder.

## 9. Disposition summary

Defects (all LOW, none blocking): L-1, L-2, L-4, L-5, L-6. Optional: L-3, I-1, I-2, I-4, I-6. Owner decision: I-3
and packet items 1-12. External gates (unchanged): commit/merge, CI, platform-first evidence, release/publication,
named roles, SG-1..SG-6, pilot, calibration, real-model evaluation, PostgreSQL 18, Windows, production OIDC.
