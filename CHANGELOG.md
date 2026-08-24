# Changelog

All notable changes to this project are documented here. Format loosely
follows [Keep a Changelog](https://keepachangelog.com/); versioning
follows [docs/COMPATIBILITY.md](docs/COMPATIBILITY.md).

## [0.1.0.dev0] — Unreleased

### Added

- Milestone M1: the reliability domain kernel, under
  `agent_reliability.domain` (not the package root). Pure, typed,
  deterministic, zero I/O:
  - `EvaluationOutcome` (`PASS`/`FAIL`/`UNKNOWN`)
  - `AgentIdentity`
  - `AgentRun`, `RunStatus` (minimal four-state lifecycle)
  - `UnknownPolicy`, `ObservationCounts`, `RatioResult`, `compute_ratio`
  - `ObjectiveDirection`, `Slo`, `SloStatus`, `SloEvaluation`, `evaluate_slo`
  - `BudgetStatus`, `ErrorBudget`, `BurnRate`, `compute_error_budget`,
    `compute_burn_rate`
  - ADR-0002 resolves the ratio-math and undefined-data semantics this
    kernel implements, correcting an ambiguity found in the M0
    `SLO_SEMANTICS.md` draft. All public symbols remain pre-alpha with
    no compatibility guarantee (see `docs/COMPATIBILITY.md`).

- Repository foundation (milestone M0): engineering principles,
  architecture and domain-model specifications, telemetry contract
  approach, SLO/error-budget/burn-rate mathematics specification,
  security threat model, testing strategy, ADR process
  (ADR-0001: architecture and dependency boundaries), and CI.
- `agent_reliability` package skeleton: layered `domain` / `application`
  / `ports` / `adapters` / `experimental` structure, all currently
  empty placeholders. Public API is limited to `__version__`.

No reliability domain logic, SDK, or telemetry emission exists yet.
