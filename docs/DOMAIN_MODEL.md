# Domain Model

Status: **specification only**. None of the types below are implemented
in M0. This document exists to pin down semantics *before* code is
written, per
[ENGINEERING_PRINCIPLES.md](ENGINEERING_PRINCIPLES.md) #1. Field lists
are illustrative of the concepts, not a final schema — types will be
finalized alongside ADRs at M1.

## Layered concepts — do not mix these

| Concept | Question it answers |
|---|---|
| Telemetry | What occurred? |
| Evaluation | Was some property of an execution satisfactory? |
| Reliability Signal | A normalized, measurable indicator derived from executions/evaluations |
| SLI | A precisely defined service-level indicator |
| SLO | A target applied to an SLI over a window |
| Error Budget | The permitted amount of unreliability implied by an SLO |
| Burn Rate | How fast the error budget is being consumed |
| Reliability State | The interpreted operational state of an agent |

A concrete rule that falls out of this: **HTTP/transport success is not
task success.** An agent call can return 200 and still have failed the
user's actual task; an agent call can fail transport-level (timeout,
retry, then succeed) and still have succeeded at the task. `AgentRun`
status and task-success `Evaluation` are always separate fields, never
derived from one another automatically.

## AgentIdentity

Identifies *what* is running.

```text
agent_id       — stable identity across versions (this agent, over time)
name           — human-readable
version        — this specific build/prompt/config revision
environment    — e.g. production, staging (open string, not an enum —
                 environments are organization-specific)
```

`agent_id` and `version` are distinct on purpose: reliability regression
detection (future milestone) compares the *same* `agent_id` across
different `version`s.

## AgentRun

One logical execution of an agent — the unit that evaluations attach to
and that reliability indicators are computed over.

```text
run_id          — globally unique (see "Identifiers" below)
agent           — AgentIdentity
started_at      — UTC, timezone-aware
ended_at        — UTC, timezone-aware, optional (unset while in flight)
status          — run-lifecycle status (see below) — NOT task success
parent_run_id   — optional; supports nested agent/tool/sub-agent runs
trace_context   — carries the OpenTelemetry trace/span context this run
                  belongs to (see TELEMETRY_SPEC.md); this project does
                  not invent its own trace ID scheme
metadata        — open key/value bag, subject to the privacy/redaction
                  rules in SECURITY_MODEL.md
```

### Run lifecycle status (transport/execution-level only)

Illustrative states: `STARTED`, `COMPLETED`, `FAILED`, `CANCELLED`,
`TIMED_OUT`. This status describes whether the run *executed to
completion*, not whether it *did the right thing*. Task success,
correctness, and policy compliance are `Evaluation`s, computed
separately and possibly by a different party, possibly asynchronously,
possibly never (see "eligibility" below). The exact enum is an M1 ADR
item ("Run lifecycle semantics"), not decided here.

## Evaluation

An assessment of some property of a run.

```text
evaluation_type     — e.g. "task_success", "correctness",
                       "policy_compliance", "tool_success" — an open,
                       versioned vocabulary, not a closed enum, because
                       organizations define their own properties
value / score       — the evaluator's judgment (see PASS/FAIL/UNKNOWN
                       below; numeric scores are a separate, optional
                       concern from the categorical outcome)
threshold           — if the evaluator reduces a score to pass/fail via
                       a threshold, that threshold is recorded, not
                       implied
evaluator           — identity of what produced this evaluation
evaluator_version   — because evaluator behavior itself can change
configuration       — evaluator-specific config in effect at eval time
evidence            — optional supporting data (subject to the same
                       privacy rules as run metadata)
timestamp           — UTC, timezone-aware
method              — deterministic | rule_based | llm_judge | human | …
```

**Provenance is not optional.** An `Evaluation` must always be traceable
to the evaluator identity, version, configuration, and timestamp that
produced it, because evaluator behavior is not fixed over time (a
prompt-based judge can change behavior when its underlying model is
upgraded, even with no version bump on the caller's side). Reliability
math that can't be traced back to "which evaluator, which version, said
this" is not trustworthy math.

### PASS / FAIL / UNKNOWN — not boolean

Every `Evaluation` outcome is one of `PASS`, `FAIL`, or `UNKNOWN` —
never forced into a boolean. Reasons `UNKNOWN` must exist as a first-
class outcome, not an implementation detail:

- the evaluator itself failed or timed out (`EVALUATOR_FAILURE`)
- the run is still in flight / not yet evaluated
- the evaluator explicitly abstains (e.g. an LLM judge declines to
  score ambiguous input)
- required evidence is missing

`UNKNOWN` is never silently treated as `PASS` or `FAIL`. How `UNKNOWN`
affects a specific SLI's ratio is a per-SLI, explicitly chosen policy —
see [SLO_SEMANTICS.md](SLO_SEMANTICS.md). This is one of the most
consequential modeling decisions in the project and is deliberately
documented separately rather than hidden inside an implementation.

## ReliabilityIndicator / SLI

A precisely defined ratio (or other statistic) computed from runs and
evaluations over a window.

```text
sli definition = numerator condition, denominator condition, window
```

Example:

```text
task_success_ratio = successful_eligible_runs / eligible_runs
```

An SLI definition must state, explicitly:

- **Eligibility** — which runs count in the denominator at all. A run
  that was cancelled by the caller before the agent did any work is
  plausibly *excluded*, not counted as a failure. A run still in flight
  is *not yet eligible*.
- **Excluded runs** — runs that are deliberately out of scope for this
  SLI (e.g. synthetic canary traffic), and why.
- **Unknown handling** — the chosen policy for `UNKNOWN` evaluations
  under this SLI (exclude from denominator / count as bad / count as
  good — each is legitimate for different SLIs, none is a silent
  default). See [SLO_SEMANTICS.md](SLO_SEMANTICS.md).
- **Aborted/timed-out runs** — treated as their own case, not silently
  folded into `FAILED`, because an infra timeout and a task failure
  imply different remediation.

## SLO

A target applied to an SLI over an observation window.

```text
indicator            — the SLI being targeted
target               — a threshold, e.g. 0.995
objective_direction  — >= target, or <= target
window               — an explicit observation window with documented
                        boundary semantics (see ENGINEERING_PRINCIPLES.md
                        #14 — no implicit or ambiguous window edges)
```

Both directions are required because both shapes of SLO are real and
common:

```text
task_success       >= 99.5%   (higher is better)
hallucination_rate <= 0.1%    (lower is better)
```

## ErrorBudget

The permitted amount of unreliability implied by an SLO — not merely a
cached percentage. Its derivation must be traceable back to the SLO's
target and the observed eligible-event count over the window; see
[SLO_SEMANTICS.md](SLO_SEMANTICS.md) for the worked mathematics.

## BurnRate

How rapidly the error budget is being consumed, defined mathematically
in [SLO_SEMANTICS.md](SLO_SEMANTICS.md) rather than left to
implementation. Multi-window burn-rate alerting (the common SRE
practice of comparing a short and a long window) is an explicit future
ADR item — M0/M1 defines the single-window mathematics only.

## ReliabilityState

The interpreted operational state of an agent. Candidate states —
**names not finalized**, semantics matter more than naming at this
stage:

```text
HEALTHY   — SLO(s) met, budget not meaningfully at risk
AT_RISK   — SLO(s) currently met but burn rate threatens the window
BREACHED  — SLO(s) not met over the window
UNKNOWN   — insufficient eligible data to make a determination
```

`UNKNOWN` is included deliberately at this level too: a brand-new agent
version with few runs so far should not be silently reported `HEALTHY`
by an empty-denominator default.

## ReliabilityEvent

Discrete, emittable occurrences derived from state transitions or
threshold crossings:

```text
SLO_BREACH
ERROR_BUDGET_WARNING
ERROR_BUDGET_EXHAUSTED
REGRESSION_DETECTED
EVALUATOR_FAILURE
```

`EVALUATOR_FAILURE` is itself a reliability event, not merely an
internal SDK log line — an evaluator that starts failing silently
degrades every SLI that depends on it, so this is signal for the agent
operator, not just for the SDK maintainer (see also
[ENGINEERING_PRINCIPLES.md](ENGINEERING_PRINCIPLES.md) #12).

## Identifiers

Domain identifiers (`agent_id`, `run_id`, evaluation IDs) must support
generation in a distributed setting without coordination — e.g. UUIDs or
ULIDs, not auto-incrementing integers. No domain type is coupled to how
it is persisted; ORM models, if any exist in the future, live entirely
in an adapter and are mapped to/from domain types at the boundary. The
domain package has no knowledge that persistence exists.
