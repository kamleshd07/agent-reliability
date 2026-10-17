# P28 / P29 owner decisions 003 (response to the owner decision packet)

Recorded 2026-10-17. Provenance: the project owner's reply in the working session, in full: "Approved. I have
authorized: recording the approved governance decisions and implementing the permitted security changes; creating
local branches and commits following the verified Git integration plan; pushing the approved integration branches
to GitHub; opening draft pull requests and running hosted GitHub Actions; fixing scoped CI failures and independently
verifying the resulting changes." The reply is unsigned, names no approver, and does not mention individual
decision numbers or supply any value the packet left blank. It is therefore recorded as **approval of the packet's
recommended options** (OD-1..OD-10 all rest on this same blanket reading; the owner may correct any of them), limited to what the packet itself proposed, with every blank left blank. No approver identity
or timestamp is invented.

| # | Decision | Recorded status |
|---|---|---|
| OD-1 | D14 / ADR-0023 A.2 | Approved as recommended, **conditional** on the production-equivalent OIDC matrix before the first production release (condition not met) |
| OD-2 | F-2 layered rate limiting | Design direction approved; **numeric quotas not approved** (implemented inactive); failure-counter layer and trusted-proxy range deferred |
| OD-3 | Retention | Structure approved; **periods and class owners not supplied** (left blank); read-only report only, nothing can be deleted |
| OD-4 | Verified identity in logs | Approved, implemented |
| OD-5 | `dev_header` | Option (c) approved, implemented |
| OD-6 | Duplicate headers | Option (a) with 422 approved, implemented |
| OD-7 | Git integration | Local commits authorized following the plan; recommended sub-decisions applied: internal reports committed with local paths replaced by placeholders, CRLF reviewer files normalized to LF |
| OD-8 | Hosted CI | Push of the integration branches and **draft** PRs authorized; no merge. **Changing GitHub repository settings (required checks) was not authorized**: only verification where permissions permit and a report of changes needing an administrator |
| OD-9 | Release roles and versions | **Not supplied**: no role holder named, no version assigned, no release authorized |
| OD-10 | Measurement health and the P7 gate | Accepted for the pilot **under the blanket reading only**; the packet's wording was a specific sentence, so the owner should confirm it explicitly before any pilot |
| OD-11 | Pilot roles, calibration, pilot | **Not supplied**: no pilot owner named; no calibration run, provider, model or spend authorized; customer pilot not authorized; SG-1..SG-6 remain NOT SATISFIED |

Still outside the authorization given: merging, tags, releases, PyPI publication, deployment, external-model
spending, a customer pilot, and any change to GitHub settings.
