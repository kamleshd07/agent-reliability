# GA readiness: Agent Reliability 1.0.0

This is the M7 engineering sign-off for the first General Availability
release, updated after the `1.0.0rc1` release candidate. It records the
state verified on 2026-08-25. The target is `1.0.0`. `1.0.0rc1` was
published to PyPI through GitHub OIDC Trusted Publishing on 2026-08-25 and
independently reinstalled and re-verified from the public artifact — see
"Release-candidate validation" below. All release blockers identified during
M7 engineering sign-off are now resolved with evidence.

## Engineering gates

| Gate | Result | Evidence |
|---|---|---|
| Supported Python | PASS | All 350 tests pass on CPython 3.11.5, 3.12, and 3.13; CI covers the same matrix. |
| Public API | PASS | Frozen and classified in [GA_CONTRACT.md](GA_CONTRACT.md) and [PUBLIC_API_REVIEW.md](PUBLIC_API_REVIEW.md); compatibility tests protect exports, signatures, and enums. |
| Semantic contract | PASS | Golden tests protect outcomes, UNKNOWN policies, exact arithmetic, boundary/no-data/zero-tolerance behavior, and provenance conflicts. |
| OpenTelemetry | PASS | The stable Python bridge is optional; the external mapping is explicitly EXTERNAL-EVOLVING. Context, failure isolation, privacy, and the `>=1.44,<2` bounds were tested. |
| Security/privacy | PASS | Adversarial tests found and closed a diagnostic `repr` secret path. BaseException/control-flow handling and bounded telemetry fields were reviewed. GitHub private vulnerability reporting is enabled account-wide for public repositories, which covers this repository. |
| Dependencies | PASS | The base wheel declares zero runtime dependencies. OTel API/SDK packages remain extras. |
| Packaging | PASS | Isolated wheel and sdist builds and installs pass. Metadata, contents, offline examples, OTel extra, and installed-wheel typing pass. |
| Typing | PASS | `py.typed` ships and a representative downstream consumer passes strict mypy against the wheel. |
| Documentation | PASS | Normative contracts, compatibility/deprecation policy, release procedure, security policy, examples, and current status are linked and consistent. Historical ADR wording remains historical context. |
| Tests/coverage | PASS | 350 tests pass; 99% branch coverage overall and 100% on implemented core modules. The two uncovered statements are empty reserved namespaces. |

## Supported and bounded behavior

- Supported interpreters: CPython 3.11, 3.12, and 3.13.
- Supported concurrency: synchronous scopes, async scopes/tasks, nesting, and
  the documented context-local thread behavior. Fork/multiprocess behavior is
  not specified.
- Base instrumentation, deterministic evaluation, and reliability analysis
  are offline and require no network, database, exporter, or commercial
  service.
- The package does not automatically collect prompts, responses, tool data,
  exception messages, tracebacks, credentials, PII, or arbitrary payloads.
  Custom diagnostic handlers are a trusted boundary and receive exceptions.
- Input collection size is caller-controlled. Aggregation is linear in the
  number of observations with bounded auxiliary memory; no arbitrary size
  limit is imposed.

## Local performance reference

These are engineering baselines from CPython 3.11.5 on Windows, not an SLA or
marketing claim. Seven-batch medians measured SDK enter/exit at 20.832 us,
enter/record/exit at 29.278 us, three-level nesting at 84.811 us, and event
construction at 2.073 us. Reliability aggregation medians were 1.030 ms for
1,000 observations, 10.108 ms for 10,000, 77.170 ms for 100,000, and 837.837
ms for 1,000,000. Traced engine peak allocation stayed between 2.3 and 2.6
KiB, excluding the caller-owned input list. Benchmarks remain non-blocking.

## Deferred features, not blockers

The first GA intentionally has no CLI, persistence, rolling-window selector,
report renderer, LLM-as-judge, framework auto-instrumentation, hosted backend,
dashboard, agent registry, dataset service, experiment system, or policy
engine. These are product evolution, not missing pieces of the frozen core.

## Release blockers

All three blockers identified during M7 engineering sign-off are resolved.

1. ~~The repository's GitHub private vulnerability reporting setting has not
   been verified.~~ **Resolved 2026-08-25.** Confirmed directly on this
   repository (Settings → Advanced Security → Private vulnerability
   reporting shows "Disable," i.e. currently enabled), not merely inferred
   from an account-wide default. The repository is also confirmed public
   (Settings → Danger Zone), which the PyPI project metadata and the OSS
   contribution workflow both assume.
2. ~~M2 through M7 were a large uncommitted working tree based on
   `d099bdc450b387c6938f3db1010766825536aa87`, with no reviewed
   release-candidate commit or remote CI result.~~ **Resolved 2026-08-25.**
   Seven reviewed commits carried that work onto `main` (`82308a1`..`6976d0a`),
   one per milestone boundary plus the GA-readiness status update and the new
   release workflow, with the full suite re-verified at 350/350 on the
   committed tree. Pushed to `origin/main` as a clean fast-forward from
   `d099bdc`; the `CI` workflow run against `6976d0a` completed with all jobs
   (lint/format/mypy, the 3.11/3.12/3.13 test matrix, and the
   release-artifact verification job) passing.
3. ~~PyPI ownership/availability and Trusted Publishing configuration for
   `agent-reliability` have not been confirmed.~~ **Resolved 2026-08-25.**
   `1.0.0rc1` (tag `v1.0.0rc1`, commit `ec467f6ea462a314f5f04321e314564c8c45f177`)
   was published to PyPI through the registered GitHub OIDC Trusted Publisher
   (repository `kamleshd07/agent-reliability`, workflow `release.yml`,
   environment `pypi`) with no stored PyPI token. The successful publish
   created the `agent-reliability` PyPI project, proving both ownership and
   that the Trusted Publishing path works end to end. Independently
   re-verified afterward from the public artifact alone (not local
   `dist/`/editable install): wheel and sdist downloaded directly from
   `pypi.org`/`files.pythonhosted.org` with matching SHA-256 hashes, a
   fresh-venv install with zero base dependencies, the README quickstart,
   a strict-mypy downstream consumer, the `[otel]` extra, and adversarial
   secret-leak checks (`SdkDiagnostic`, `EvaluationExecutionFailure`,
   default diagnostic logging) against the live installed package.

## Release-candidate validation

`1.0.0rc1` is the release-candidate baseline for `1.0.0`: same source tree,
same public contract, same dependency-free base install, same OTel-optional
adapter, same measurement-integrity and privacy behavior — differing only in
version string and pre-release status. GA preparation from this point is
intentionally limited to version, changelog, and documentation-status
changes; see the RC → GA diff recorded in the release commit for the exact,
minimal set of differences.

READY FOR 1.0.0
