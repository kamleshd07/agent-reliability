# GA readiness: Agent Reliability 1.0.0

This is the M7 engineering sign-off for the first General Availability
release. It records the state verified on 2026-08-25. The target is `1.0.0`;
the working tree intentionally remains `0.1.0.dev0` until the release
preconditions below are satisfied.

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

1. ~~The repository's GitHub private vulnerability reporting setting has not
   been verified.~~ **Resolved 2026-08-25.** Private vulnerability reporting
   is enabled account-wide for public repositories, which covers this
   repository.
2. M2 through M7 were a large uncommitted working tree based on
   `d099bdc450b387c6938f3db1010766825536aa87`. **Partially resolved
   2026-08-25:** six reviewed commits now carry that work on `main`
   (`82308a1`..`9b29dee`), one per milestone boundary, with the full suite
   re-verified at 350/350 on the committed tree. Still open: this has not
   been pushed to `origin/main`, and no remote CI run exists for this exact
   commit sequence yet.
3. PyPI ownership/availability and Trusted Publishing configuration for
   `agent-reliability` have not been confirmed. No distribution with that name
   was visible on PyPI during the review, which does not by itself reserve the
   name or prove publishing authority.

After those operational prerequisites are resolved, push to `origin/main` and
confirm remote CI passes the full matrix and artifact-verification job, then
create a reviewed `1.0.0rc1` commit, publish the candidate through the
documented trusted path, and repeat the installed-distribution sanity test.
Only then should the final release commit change the single version source to
`1.0.0`, update release metadata/changelog, and be tagged.

NOT READY FOR 1.0.0 — one blocker remains (PyPI), plus pushing/remote CI for
blocker 2.
