# P28 SDK exporter - owner decisions 002 (F-4, F-9, L2 refinements)

Date of record: 2026-10-17.

Provenance: the product owner's explicit statement in the user's own instruction for the
"Complete P28 and P29 End-to-End" task ("The owner explicitly approves: F-4, F-9, L2 ...").
Signature: none. Approver identity: not recorded. Approval time of day: not recorded. No
named owner, role holder or reviewer is assigned or inferred. This record is not a
cryptographic signature. It supersedes the "pending" status of these items in
`P28_P29_RELEASE_GATE_CONSOLIDATION.md` and the readiness report; it approves nothing else.

## Decisions recorded (exact scope)

| ID | Decision as approved | Implemented in |
|---|---|---|
| F-4 | The HTTP exporter implementation submodules stay classified **INTERNAL** under the SDK's existing stability policy (`GA_CONTRACT.md`). **No new Beta class** is introduced. The documented consumer entry points are identified and distinguished from internal implementation modules. No release version is invented and no stable compatibility is promised beyond the existing policy | `docs/HTTP_EXPORTER.md` "Stability status"; `docs/GA_CONTRACT.md` "P28 HTTP evidence exporter (unreleased): INTERNAL" |
| F-9 | Exclude from the P28 sdist: `CLAUDE.md`, `AGENTS.md`, internal `docs/P28_*` reports. Preserve public documentation, licensing, source files and required build/test inputs | `pyproject.toml` `[tool.hatch.build.targets.sdist] exclude`; `scripts/verify_release_artifacts.py` guard |
| L2 | TLS certificate-verification failures count only for attempts where the application request has not been sent. An explicit proxy CONNECT request does not count as sending the application request. The failure streak is scoped to an endpoint within each exporter instance. Previously documented rules retained: threshold of three qualifying consecutive failures; reset after verified successful communication and explicit endpoint resume; ordinary network failures neutral | `docs/HTTP_EXPORTER.md` L2 paragraph (unchanged semantics); tests in `tests/unit/test_http_exporter_tls_real.py` |

## Not decided here

Release version and date; commit and publication authorization; named release owner and
reviewer; D14; ADR-0023 Appendix A.2; pre-authentication rate limiting; audit retention;
verified-identity logging; production `dev_header` policy; duplicate-header policy;
platform-first release evidence; P29 SG-1..SG-6 and any pilot. They remain open.
