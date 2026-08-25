# M6 Fresh-User Developer Experience Review

Date: 2026-08-25

This review was performed before M6 changes from the perspective of a Python
backend/AI engineer unfamiliar with the architecture. The existing M5 wheel
was installed with `--no-deps` into a newly created Python 3.11 virtual
environment, imported without OpenTelemetry installed, and used to execute the
complete SDK → evaluator → observation → SLO → report workflow.

## What already worked

- The built wheel installed successfully without runtime dependencies.
- Base imports worked with OpenTelemetry absent.
- The full explicit workflow produced an exact `2/3` reliability ratio, `MET`
  SLO status, and zero remaining budget for deterministic sample data.
- `ReliabilityObservation.from_evaluation(...)` already removes unsafe manual
  copying without hiding indicator or provenance.
- Public namespaces are coherent and the package root remains intentionally
  small.

No foundational API blocker was found.

## BLOCKER

### None found

The package itself is installable and the M1-M5 workflow is executable from a
wheel. M6 should improve the path to that success rather than change its
semantics.

## HIGH FRICTION

### No standalone first-success path

- **Problem:** README examples are split across sections and later snippets
  depend on variables created earlier. A developer cannot copy one compact
  program and see the complete product result.
- **Decision:** Fix.
- **Resolution:** Add one tested `docs/QUICKSTART.md` flow and a canonical
  `examples/basic_reliability.py`; make README product-first and link to both.

### No executable example contract

- **Problem:** There was no `examples/` directory and CI did not execute user
  workflows. Documentation could drift while unit tests remained green.
- **Decision:** Fix.
- **Resolution:** Add a small example set, subprocess tests, and CI example
  execution.

### Documentation has no audience-oriented entry point

- **Problem:** A newcomer sees a flat set of semantics, architecture, security,
  and ADR documents with no recommended path.
- **Decision:** Fix.
- **Resolution:** Add `docs/README.md` organized by getting started, concepts,
  guides, reference, and architecture.

### Clean-wheel behavior is manual only

- **Problem:** CI built a wheel but did not install that artifact into a clean
  environment or run the canonical example from it.
- **Decision:** Fix.
- **Resolution:** Add a repeatable wheel smoke script/test and a focused CI
  job using non-editable wheel and sdist installs.

## MEDIUM FRICTION

### Reliability reports require domain-field knowledge to interpret

- **Problem:** Correct M5 values are intentionally unformatted, but a new user
  must discover nested `ratio`, `slo_evaluation`, and `error_budget` fields.
- **Decision:** Fix in presentation, not public API.
- **Resolution:** Use a small example-local formatter and document the exact
  fields. Do not add a renderer that would become a long-lived public contract.

### Raw evaluator execution is easy to confuse with attributable execution

- **Problem:** `EqualityEvaluator.evaluate()` returns `EvaluationDecision`,
  while the SDK recording path requires `EvaluationResult`. The distinction is
  correct but not obvious from an isolated evaluator snippet.
- **Decision:** Fix documentation.
- **Resolution:** Canonical examples use `EvaluatorRunner`; concepts explain
  raw decisions versus completed attributable results.

### Provenance-conflict recovery is not discoverable

- **Problem:** Conflict enums are precise, but user-facing documentation does
  not collect their meanings or explain how to resolve them.
- **Decision:** Fix documentation.
- **Resolution:** Add a runnable conflict example and a conflict-resolution
  table using the implemented enum names.

### Installed typing intent is not declared

- **Problem:** The package advertises typing and passes strict MyPy, but the
  wheel has no PEP 561 `py.typed` marker.
- **Decision:** Fix.
- **Resolution:** Add `py.typed`, verify wheel contents, and run a downstream
  MyPy smoke check against the installed wheel.

### Optional OpenTelemetry workflow is separate from first-use guidance

- **Problem:** The existing detailed OTel mapping is rigorous, but newcomers
  need a shorter explanation of what Agent Reliability owns versus what their
  application configures.
- **Decision:** Fix documentation and example coverage.
- **Resolution:** Add one optional public-API-only example and integration
  guide; keep provider/exporter ownership with the host.

## MINOR

### Some public protocol/enum docstrings are absent

- **Problem:** `SyncEvaluator`, `AsyncEvaluator`, and
  `EvaluationFailureStage` have no direct docstrings.
- **Decision:** Fix narrowly.
- **Resolution:** Add concise semantic docstrings; avoid unrelated rewrites.

### Contributor and security wording still says pre-alpha/M0-era things

- **Problem:** Setup instructions are usable, but project status and the
  security-surface description lag M5.
- **Decision:** Fix current facts; defer formal GA policy.
- **Resolution:** Update contributor setup/expectations and security scope
  without inventing a private contact channel.

### No issue templates

- **Problem:** An approaching-public project lacks structured bug and feature
  intake.
- **Decision:** Fix minimally.
- **Resolution:** Add one bug-report and one feature-request template; route
  vulnerabilities to `SECURITY.md`.

## Explicitly deferred after audit

- No CLI: there is no stable serialized input contract.
- No public report renderer: example-local formatting is sufficient.
- No package-root flattening: documented imports are understandable.
- No new evaluation-to-observation helper: the existing
  `ReliabilityObservation.from_evaluation(...)` is explicit and sufficient.
- No framework adapter or framework dependency: explicit instrumentation wraps
  a normal Python execution boundary without framework internals.
- No auto-instrumentation, persistence, serialization, LLM evaluator, hosted
  service, or commercial-platform integration.
