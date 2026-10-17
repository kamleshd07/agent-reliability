# P28 SDK - D-1 remediation report (2026-10-16)

Status: D-1 is fixed in the working tree of the real SDK; **nothing is committed, released or
published**, and the SDK still carries the other uncommitted P28 exporter work.

## Change set (relative to the state recorded before this task)
| File | Change |
|---|---|
| `src/agent_reliability/adapters/http_event_sink.py` | `_failure()` only (untracked file; original sha256 prefix 97689b8a687de630) |
| `tests/unit/test_http_exporter_tls_real.py` | new, 16 tests with REAL TLS handshakes |
| `tests/fixtures/tls/{README.md,generate.py,ca.crt,localhost.{crt,key},other.{crt,key},expired.{crt,key},selfsigned.{crt,key}}` | new throwaway fixtures (TEST ONLY) |
| `docs/HTTP_EXPORTER.md` | two added sentences defining "consecutive" for the L2 TLS streak |
| `docs/P28_SDK_D1_REMEDIATION_REPORT.md`, `docs/P28_SDK_D1_INDEPENDENT_REVIEW.md` | this report; the reviewer's report (authored by the reviewer) |

## Provenance
The fix is the E2E workspace patch `patches/sdk_tls_verification_chain.patch` (verified by an
earlier reviewer and verifier), applied with `patch -p1` to the real file. Differences from the
tested patch: comment line-wrapping only (ruff E501); the code is byte-for-byte the tested
logic. Semantics: bounded (64 nodes), cycle-safe walk of both `__cause__` and `__context__`;
`__suppress_context__` is deliberately NOT honoured (real httpcore sets it on the exception
that hides the SSL error); TLS verification failure is recognised only for an attempt that has
not sent (`record.sent` is reset per attempt in `Core.take()`).

## Changes after the independent review
R-1 test for the per-attempt `sent` reset (mutant that deletes the reset is now killed); R-2
flakiness fixed at its root (the test server closed the socket right after replying, which
sometimes made the client see a reset instead of the 500 - an "indeterminate" failure that
rightly does not reset the streak; the server now shuts down orderly) and retry backoff zeroed
in these tests; R-3 the D-1 premise is asserted on the real httpcore exception; R-4 the
cycle/bound tests run under a deadline; R-6 definition of "consecutive" documented. R-5 (below)
is a release decision, not changed.

## Results (PostgreSQL 16.15 / 17.11, Node v26.12.0)
| Check | Result |
|---|---|
| SDK full suite, Python 3.11.17 / 3.12.15 / 3.13.16 | 857 passed each |
| New real-TLS tests, 48 runs in 6 parallel loops (3.11) and 8 runs (3.13) | 56 of 56 passed |
| `ruff check`, `ruff format --check`, `mypy src` (46 files) | clean |
| `verify_p28_fixtures.py`, Node reference | 4 hashes verified, platform comparison True; 76 canonical + 74 acknowledgement vectors |
| `python -m build` + `scripts/verify_release_artifacts.py` (scratch copy) | exit 0 |
| E2E suite against the REAL SDK (scratch copy of the workspace, variant `real`) | 80 passed on PostgreSQL 16 and on 17, no expected failures |
| Mutants (reviewer: 12, 11 killed; author: reverted classifier -> 9 of 15 fail; per-attempt-reset mutant -> killed) | see the review |

## Remaining gates (none closed by this work)
Review of the whole uncommitted P28 exporter change set; owner decision on committed throwaway
private keys (R-5: the four `tests/fixtures/tls/*.key` files are in the sdist but not the wheel;
secret scanners will flag them - allow-list, generate at test time, or exclude from the sdist);
a CHANGELOG entry; owner confirmation of the "consecutive" reading in `HTTP_EXPORTER.md`;
commit/release authorization; platform-first release evidence; formal D14 / ADR-0023 Appendix
A.2 approval (unapproved; no owner or reviewer is named here); items unrelated to D-1 from the
E2E report (platform-terminated TLS, explicit proxy/CA, connect timeout, PostgreSQL 18, load).
