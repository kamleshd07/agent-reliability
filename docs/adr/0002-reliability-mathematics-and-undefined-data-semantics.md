# ADR-0002: Reliability mathematics and undefined-data semantics

## Status

Accepted

## Context

Implementing the M1 reliability domain kernel against the M0
specifications ([DOMAIN_MODEL.md](../DOMAIN_MODEL.md),
[SLO_SEMANTICS.md](../SLO_SEMANTICS.md)) surfaced concrete ambiguities
that the M0 documents did not resolve with enough precision to write
code against. Per [ENGINEERING_PRINCIPLES.md](../ENGINEERING_PRINCIPLES.md)
#1, none of these are resolved silently in the implementation — they are
resolved here first, and the affected M0 documents are corrected to
match.

### Ambiguity 1 — `AT_MOST` SLOs contradicted the ratio SLI definition

[SLO_SEMANTICS.md](../SLO_SEMANTICS.md) (M0 revision) stated that a
ratio SLI is always `good_events / valid_events`, and separately, in
its Error Budget section, stated that for an `AT_MOST` SLO "the SLI
itself is already defined as the *bad* fraction." Both cannot be true
of the same computed value: [DOMAIN_MODEL.md](../DOMAIN_MODEL.md)
independently defines `good_event` as "an evaluation outcome of `PASS`
... or, for a lower-is-better SLI, whose outcome does *not* trigger the
bad condition" — meaning `PASS` always denotes "good," regardless of
SLO direction. A single ratio quantity cannot simultaneously always mean
"good fraction" and, for one direction, mean "bad fraction." One of the
two framings had to be discarded.

### Ambiguity 2 — zero-denominator and zero-tolerance semantics were named but not typed

[SLO_SEMANTICS.md](../SLO_SEMANTICS.md) required that an undefined SLI
ratio (no eligible observations) never be reported as `0.0` or `1.0`,
but did not specify a concrete representation. Separately, a `target =
100%` (or, for `AT_MOST`, `target = 0%`) SLO makes `allowed_bad_fraction
= 0`, which makes error-budget consumption and burn rate a division by
zero — a distinct situation from "no data," since the SLI itself can be
perfectly well-defined (e.g. exactly 100% observed pass rate) while the
*budget math* built on top of it is degenerate.

### Ambiguity 3 — numeric representation for ratios and thresholds was unspecified

Nothing in M0 fixed whether ratio/threshold arithmetic uses `float`,
`decimal.Decimal`, or `fractions.Fraction`. This matters concretely
because M1 requires exact boundary comparisons (`ratio == target` must
resolve correctly for SLO evaluation).

## Decision

### 1. Ratio math is unified around a single "bad fraction," not two separate formulas per direction

A ratio SLI computes exactly one canonical quantity from raw
`EvaluationOutcome` counts: `pass_ratio = considered_pass_count /
considered_count`, where "considered" already reflects the chosen
`UnknownPolicy`. `PASS` always means "good," full stop, matching
`DOMAIN_MODEL.md` — there is no per-direction reinterpretation of what
counts as `PASS`.

Everything direction-sensitive is expressed instead through
`fail_ratio = considered_fail_count / considered_count`
(`= 1 - pass_ratio` whenever both are defined, though each is computed
directly from its own counts rather than by subtraction, so the two
never disagree due to independent rounding) and through the SLO's own
`allowed_bad_fraction`:

```text
AT_LEAST (e.g. task_success >= 0.995):  allowed_bad_fraction = 1 - target
AT_MOST  (e.g. hallucination <= 0.001): allowed_bad_fraction = target
```

An SLO is `MET` iff `fail_ratio <= allowed_bad_fraction` — one formula,
both directions. This is not a new rule bolted on top of the two
directions; it is algebraically identical to "`pass_ratio >= target`"
for `AT_LEAST` (substitute `fail_ratio = 1 - pass_ratio` and
`allowed_bad_fraction = 1 - target}` and the inequality is unchanged),
so nothing about the documented `AT_LEAST` behavior changes — this
merely extends the same formula correctly to `AT_MOST` instead of
inventing a second, contradictory one.

The practical consequence for callers defining an `AT_MOST` SLI (e.g.
hallucination rate): the underlying evaluator must still report `PASS`
for "no hallucination detected" and `FAIL` for "hallucination
detected" — `fail_ratio` is then literally the hallucination rate,
directly comparable to the `AT_MOST` target. This resolves Ambiguity 1
by discarding the "SLI is already the bad fraction" framing entirely;
[SLO_SEMANTICS.md](../SLO_SEMANTICS.md) is corrected accordingly.

Burn rate and cumulative error-budget consumption turn out to be the
*same* computation (`fail_ratio / allowed_bad_fraction`) applied to two
different observation windows — a full window for error budget, an
arbitrary shorter lookback for burn rate. The implementation shares one
internal helper for this reason; this is a discovered simplification,
not a new independent rule.

### 2. Undefined ratios/budgets are `None` on `Fraction`-typed fields, tagged by an explicit status enum — never `0.0`, `1.0`, `NaN`, or a bare infinity

Two distinct "cannot compute a number" situations exist, and are kept
distinguishable:

- **No data** (`considered_count == 0`): `RatioResult.pass_ratio` and
  `.fail_ratio` are `None`. `SloEvaluation.status` is `SloStatus.UNKNOWN`
  (not `MET`, not `BREACHED` — a third, first-class outcome, consistent
  with `DOMAIN_MODEL.md`'s general rule that missing evidence must
  never collapse into `PASS`/`FAIL`-shaped semantics). `ErrorBudget`
  and `BurnRate` report `status = BudgetStatus.NO_DATA` with their
  numeric fields set to `None`.
- **Zero tolerance** (`allowed_bad_fraction == 0`, i.e. a 100%
  `AT_LEAST` or 0% `AT_MOST` target), which can only arise when data
  *does* exist (`considered_count > 0`, so the SLI itself is
  well-defined) but the budget math's denominator is zero:
  - zero observed bad events → `BudgetStatus.ZERO_TOLERANCE_INTACT`,
    reported as a genuine, finite `consumption_ratio = 0` /
    `remaining_fraction = 1` / burn rate `0` — a zero-tolerance budget
    with zero violations is not undefined, it is fully intact by
    definition, and forcing it into a "no data" bucket would be
    incorrect.
  - one or more observed bad events → `BudgetStatus.ZERO_TOLERANCE_EXCEEDED`,
    with the ratio-typed fields set to `None`. The true value here is
    unbounded (dividing a positive number by zero), which
    `fractions.Fraction` cannot represent (unlike IEEE float, it has no
    infinity), and inventing a mixed `Fraction | float` field just to
    carry an occasional `inf` was rejected as worse than a `None` +
    explicit status the caller must already handle for the `NO_DATA`
    case. Any code path that checks `status` before reading the numeric
    field handles both "no data" and "breached beyond measure"
    correctly without needing to special-case infinity.

This resolves Ambiguity 2. `None` is used here deliberately as "no
finite ratio exists," which is a different concept from
`EvaluationOutcome.UNKNOWN` ("the evidence needed to categorize this
observation does not exist") — the two must not be confused, and
`EvaluationOutcome` itself never uses `None` for exactly that reason
([DOMAIN_MODEL.md](../DOMAIN_MODEL.md)).

### 3. `fractions.Fraction` is the numeric type for all ratio/threshold arithmetic in the kernel

Rejected `float`: ordinary decimal thresholds like `0.995` have no
exact binary floating-point representation, which is fatal precisely at
the inclusive-boundary comparisons M1 is required to get right
(`ratio == target` must resolve consistently). Rejected `decimal.Decimal`:
`Decimal` arithmetic result precision depends on the ambient
`decimal.Context` (thread-local, mutable, configurable via
`getcontext().prec`), which is a form of hidden global state
([ENGINEERING_PRINCIPLES.md](../ENGINEERING_PRINCIPLES.md) #11) — two
calls to the same function could silently disagree if something else in
the process changed the context in between. `Fraction` has no such
context: it is always exact, hashable, totally ordered, and constructs
losslessly from integer counts (`Fraction(good, total)`) and from exact
decimal literals given as strings or integer pairs (`Fraction("0.995")`,
`Fraction(995, 1000)`). Every ratio in this kernel is definitionally
rational (an integer count divided by an integer count), so `Fraction`
is not an approximation of the right type — it *is* the right type.

The one documented pitfall: `Fraction(0.995)` (a bare float literal)
captures the float's binary rounding error, not the exact decimal
value, because the float rounding already happened before `Fraction`
ever sees it. `Slo.target` therefore performs a runtime `isinstance`
check rejecting non-`Fraction` input rather than relying on type hints
alone, specifically because this is the one construction site where a
caller ignoring or lacking static type checking could otherwise
silently reintroduce float rounding at the exact spot correctness
depends on most.

Conversion to `float`/JSON/wire formats for display or serialization is
an adapter/presentation concern, out of scope for the domain kernel and
deferred to whichever future milestone needs it.

### 4. No hidden ID generation, no hidden clock reads, inside domain constructors

`AgentRun.run_id` and `AgentRun.started_at`/`ended_at` are required
constructor arguments with no defaults. The domain never calls
`uuid.uuid4()` or `datetime.now()` internally. A value object that
silently generates its own random ID or reads the wall clock on
construction cannot be reproduced in a test or reasoned about as pure
data — id/time generation belongs to whatever layer actually needs
randomness or wall-clock access (the future SDK, M2), injected
explicitly. Naive (timezone-unaware) timestamps are rejected outright,
never silently assumed to be UTC; timezone-aware timestamps are
normalized to UTC internally so that comparisons across differently
zoned inputs are always correct.

### 5. A minimal `RunStatus` is defined now; a richer failure-cause taxonomy remains deferred

[ARCHITECTURE.md](../ARCHITECTURE.md) previously listed "run lifecycle
state machine" as fully deferred to a future ADR. M1 needs *enough* of
`AgentRun`'s lifecycle to state the invariant "a run without `ended_at`
is in progress; a run with `ended_at` is terminal," which requires some
status values to exist now. Rather than leave `AgentRun` unimplementable
or invent a placeholder that gets thrown away, this ADR defines the
minimal set needed for that invariant:

```text
STARTED     — ended_at is None
COMPLETED   — terminal, ended_at is set
FAILED      — terminal, ended_at is set
CANCELLED   — terminal, ended_at is set
```

`TIMED_OUT` (present in `DOMAIN_MODEL.md`'s original illustrative list)
is deliberately **not** included as a distinct M1 state: a timeout is a
specific *cause* of a run not completing, and distinguishing causes
requires instrumentation actually observing why a run ended, which does
not exist until M2. Collapsing timeout into `FAILED` for now avoids
guessing at a richer taxonomy with no real usage to validate it against.
A richer failure-cause model (of which timeout would be one case) is
still deferred, and `ARCHITECTURE.md` is updated to reflect that only
the minimal four-state lifecycle is resolved, not the full future state
machine.

### 6. No separate `ReliabilityObservation` type

`DOMAIN_MODEL.md`'s "Reliability Observation" concept — "the outcome of
one eligible reliability observation" — is, for every purpose the ratio
kernel needs, exactly an `EvaluationOutcome`. Introducing a second
single-field type that wraps it would duplicate the concept without
adding meaning, which `DOMAIN_MODEL.md` itself warns against. The ratio
kernel's public entry point (`compute_ratio`) accepts a plain
`Iterable[EvaluationOutcome]`; a richer per-observation record (with
evaluator provenance, timestamp, evidence, per `DOMAIN_MODEL.md`'s
`Evaluation` concept) is deferred to M4 ("Evaluator framework"), where
evaluator identity genuinely matters and can be designed against real
evaluator implementations instead of speculatively now.

## Alternatives Considered

- **Keep two separate formulas for `AT_LEAST` and `AT_MOST`** (as M0's
  text implied), each computing its own notion of "the SLI." Rejected:
  this is the contradiction that triggered this ADR — it requires
  `PASS` to mean different things depending on a field on a different
  object (the `Slo`, not the evaluation itself), which cannot be
  determined locally when computing a `RatioResult`, and produces two
  code paths that could silently drift apart.
- **Represent undefined ratios as `0.0`/`1.0`.** Rejected explicitly by
  `SLO_SEMANTICS.md` and for the obvious reason: both are wrong answers
  presented with false confidence.
- **Represent undefined/infinite results as `float('nan')` /
  `float('inf')`.** Rejected: `NaN` poisons downstream arithmetic
  silently (any comparison involving `NaN` is `False`, including
  `NaN == NaN`, which is exactly the kind of "accidental" semantic the
  M1 brief warned against); mixing `float`s into an otherwise-`Fraction`
  kernel for one rare case adds a type union everywhere for a single
  edge case better handled by an explicit status.
- **`decimal.Decimal` for ratio arithmetic.** Rejected due to ambient,
  mutable precision context — see Decision 3.
- **A single generic "undefined reason" enum shared across
  `RatioResult`, `SloEvaluation`, `ErrorBudget`, and `BurnRate`.**
  Considered, but `RatioResult`'s only undefined case is "no data,"
  which is already fully expressed by `pass_ratio is None`; adding a
  status enum there for a single boolean-shaped condition would be
  redundant. `ErrorBudget`/`BurnRate` share `BudgetStatus` because they
  have three distinguishable states, not one.

## Consequences

- `SLO_SEMANTICS.md` is corrected to remove the "SLI is already the bad
  fraction" framing and to document the unified `fail_ratio` /
  `allowed_bad_fraction` formulation, plus the zero-data and
  zero-tolerance cases.
- `DOMAIN_MODEL.md` is updated to record: the resolved minimal
  `RunStatus`, the decision not to introduce `ReliabilityObservation`
  as a distinct type, and the explicit-injection requirement for
  `run_id`/timestamps.
- `ARCHITECTURE.md`'s deferred-decisions list is updated: "run lifecycle
  state machine" is narrowed to "richer run failure-cause taxonomy" to
  reflect that the minimal four-state version is now resolved.
- Any future milestone computing a non-ratio SLI (e.g. a latency
  percentile) will need its own ADR — nothing here generalizes beyond
  ratio SLIs built from `EvaluationOutcome` counts.

## Security Impact

None beyond what [SECURITY_MODEL.md](../SECURITY_MODEL.md) already
covers. `Fraction` arithmetic on caller-supplied integer counts has no
new injection or resource-exhaustion surface beyond ordinary integer
overflow-free Python arithmetic; counts are always non-negative
integers, validated at construction.

## Performance Impact

`Fraction` construction reduces numerator/denominator via `gcd`, which
is `O(log n)` — negligible for M1's use, and no different in complexity
class from the ratio division itself. `compute_ratio` streams over its
input in `O(1)` memory. No benchmarks are established at M1 per
[ENGINEERING_PRINCIPLES.md](../ENGINEERING_PRINCIPLES.md) #6 — deferred
to M2, when a real instrumentation hot path exists to measure.

## Compatibility Impact

This is the first ADR to authorize real public domain types. They are
exported from `agent_reliability.domain` (not the package root) and
remain subject to the pre-alpha "no stability guarantee" policy in
[COMPATIBILITY.md](../COMPATIBILITY.md) — nothing here is declared
stable.
