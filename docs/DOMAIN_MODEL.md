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
                 — required
name           — human-readable — required
version        — this specific build/prompt/config revision — required
environment    — e.g. production, staging (open string, not an enum —
                 environments are organization-specific) — optional
```

`agent_id` and `version` are distinct on purpose: reliability regression
detection (future milestone) compares the *same* `agent_id` across
different `version`s.

`environment` is modeled as optional metadata carried on the identity,
not as part of what makes two `AgentIdentity` values equal in any
special ("same logical agent") sense — M1 implements only ordinary
structural equality (all four fields must match). Whether/how
`environment` should scope or filter the population of runs feeding an
SLI (e.g. should staging and production traffic ever share one SLI) is
not decided here; it is a future SLO-scoping question (M6). Making it
optional rather than forcing a default like `"production"` avoids
silently mislabeling data whose environment the caller genuinely did
not specify.

## AgentRun

One logical execution of an agent — the unit that evaluations attach to
and that reliability indicators are computed over.

```text
run_id          — globally unique (see "Identifiers" below); supplied
                  by the caller, never generated inside the domain
                  (see [ADR-0002](adr/0002-reliability-mathematics-and-undefined-data-semantics.md))
agent           — AgentIdentity
started_at      — UTC, timezone-aware; supplied by the caller, never
                  read from the wall clock inside the domain (ADR-0002)
ended_at        — UTC, timezone-aware, optional (unset while in flight)
status          — run-lifecycle status (see below) — NOT task success
parent_run_id   — optional; supports nested agent/tool/sub-agent runs
```

`trace_context` and `metadata` from the earlier illustrative field list
are **not** implemented on `AgentRun` at M1. `trace_context` needs a
concrete type to carry, and the right type only exists once the OTel
bridge (M3) is built against it; a placeholder field with no real type
would be worse than no field. `metadata` is an open bag whose privacy
and redaction handling ([SECURITY_MODEL.md](SECURITY_MODEL.md)) has no
consumer yet at the pure-math-kernel stage. Both are deferred to the
milestone that actually needs them, not spoken for now.

### Run lifecycle status (transport/execution-level only)

Resolved for M1 by [ADR-0002](adr/0002-reliability-mathematics-and-undefined-data-semantics.md)
as a minimal, deliberately small set:

```text
STARTED     — ended_at is None (run in progress)
COMPLETED   — terminal, ended_at is set
FAILED      — terminal, ended_at is set
CANCELLED   — terminal, ended_at is set
```

This status describes whether the run *executed to completion*, not
whether it *did the right thing*. Task success, correctness, and policy
compliance are `Evaluation`s, computed separately and possibly by a
different party, possibly asynchronously, possibly never (see
"eligibility" below).

`TIMED_OUT` (present in the original illustrative list above) is
deliberately not a distinct M1 state — a timeout is a *cause* of a run
not completing, and a richer failure-cause taxonomy needs real
instrumentation (M2+) to design against rather than being guessed at
now. It currently falls under `FAILED`. This is a narrower, resolved
version of what `ARCHITECTURE.md` previously listed as a fully deferred
"run lifecycle state machine" — the minimal four-state lifecycle above
is decided; a richer failure-cause model remains deferred.

## Evaluation

An assessment of some property of a run.

**M1 scope note:** M1 implements only `EvaluationOutcome` (the
`PASS`/`FAIL`/`UNKNOWN` enum below) and the ratio math built on it. The
full `Evaluation` record described in this section — with evaluator
identity, version, configuration, evidence, and timestamp — is deferred
to M4 ("Evaluator framework"), where it can be designed against real
evaluator implementations instead of speculatively now. M1's ratio
kernel takes a plain `Iterable[EvaluationOutcome]`; it does not need to
know who produced each outcome or when.

M1 also does **not** introduce a separate "Reliability Observation"
type distinct from `EvaluationOutcome`. For every purpose the ratio
kernel needs, an eligible observation *is* its outcome — wrapping a
single `EvaluationOutcome` in another single-field type would duplicate
the concept without adding meaning (see
[ADR-0002](adr/0002-reliability-mathematics-and-undefined-data-semantics.md)).

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
