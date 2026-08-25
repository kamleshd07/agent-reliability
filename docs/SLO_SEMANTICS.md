# SLO Semantics

Status: implemented by M1 and consumed without formula duplication by M5.
This document defines the mathematics that the Reliability Domain Kernel
implements exactly.
No rolling-window algorithms, multi-window burn-rate alerting, or
statistical smoothing are specified here; those are explicit future ADR
items. This document covers single-window, batch (not streaming)
computation only.

## Ratio SLI

```text
SLI = good_events / valid_events
```

This formula is meaningless without also defining, per SLI, exactly
what counts as each term:

| Term | Meaning |
|---|---|
| `good_event` | An eligible run whose relevant `Evaluation` outcome is `PASS` (or, for a "lower is better" SLI, whose outcome does *not* trigger the bad condition) |
| `valid_event` | An eligible run counted in the denominator at all |
| `unknown_event` | An eligible run whose relevant `Evaluation` outcome is `UNKNOWN` |
| `excluded_event` | A run deliberately outside this SLI's scope (e.g. cancelled before agent work began, synthetic/canary traffic, still in flight) — never enters numerator or denominator |

**Eligibility is decided first, independently of outcome.** A run must
be determined eligible or excluded *before* looking at its evaluation
outcome. Excluding runs based on their outcome (e.g. quietly dropping
runs that failed) is not permitted — that would silently improve the
SLI by definition-gaming rather than by the agent actually improving.

### UNKNOWN policy — must be explicit per SLI

Because `UNKNOWN` must never be silently treated as `PASS` or `FAIL`
(see [DOMAIN_MODEL.md](DOMAIN_MODEL.md)), every SLI definition must
declare one of the following policies, and the choice is part of the
SLI's definition, not a global default:

| Policy | `valid_events` includes UNKNOWN? | Effect |
|---|---|---|
| `EXCLUDE` | No | UNKNOWN runs are removed from both numerator and denominator — the SLI reports on what could be judged |
| `TREAT_AS_BAD` | Yes (counted, not good) | Conservative: an unevaluable run is assumed to have failed the objective |
| `TREAT_AS_GOOD` | Yes (counted, good) | Optimistic: rarely appropriate; must be justified when chosen (e.g. a low-stakes SLI where absence of evidence of failure is an acceptable proxy) |

There is no project-wide default. An SLI definition that does not state
its UNKNOWN policy is incomplete and must not be evaluated.

### Worked example

Given, over one window:

```text
10,000 eligible runs
   9,920 successful  (PASS)
      50 failed      (FAIL)
      30 unknown     (UNKNOWN)
```

With policy `EXCLUDE`:

```text
valid_events = 9,920 + 50 = 9,970
good_events  = 9,920
SLI = 9,920 / 9,970 = 0.99498... ≈ 99.498%
```

With policy `TREAT_AS_BAD`:

```text
valid_events = 9,920 + 50 + 30 = 10,000
good_events  = 9,920
SLI = 9,920 / 10,000 = 0.9920 = 99.20%
```

With policy `TREAT_AS_GOOD`:

```text
valid_events = 10,000
good_events  = 9,920 + 30 = 9,950
SLI = 9,950 / 10,000 = 0.9950 = 99.50%
```

The three policies produce three different SLI values (99.498%, 99.20%,
99.50%) from identical raw data. This is the reason the policy cannot be
an implicit assumption — the same 30 UNKNOWN runs move the reported
value by up to 0.3 percentage points, which can be the entire difference
between meeting and breaching a 99.5% target.

## SLO

**Corrected by [ADR-0002](adr/0002-reliability-mathematics-and-undefined-data-semantics.md)**,
which resolved a contradiction in an earlier revision of this document
(it had claimed the SLI itself "is already the bad fraction" for
`AT_MOST` SLOs, which conflicts with `good_event` always meaning `PASS`
per [DOMAIN_MODEL.md](DOMAIN_MODEL.md)). The corrected model:

`PASS` always means "good," for both directions — the ratio SLI itself
(`pass_ratio = good_events / valid_events`) never changes meaning.
Direction only changes how the SLO's `allowed_bad_fraction` is derived
from `target`, and the SLO is evaluated by comparing the *observed* bad
fraction (`fail_ratio = 1 - pass_ratio`, i.e. the complement of the SLI,
computed directly rather than by subtraction) against it:

```text
AT_LEAST (e.g. task_success >= 0.995):
    allowed_bad_fraction = 1 - target   = 1 - 0.995 = 0.005

AT_MOST (e.g. hallucination_rate <= 0.001):
    allowed_bad_fraction = target       = 0.001
```

```text
SLO is MET      iff fail_ratio <= allowed_bad_fraction
SLO is BREACHED iff fail_ratio >  allowed_bad_fraction
SLO is UNKNOWN  iff there is no data (see "Undefined and zero-tolerance
                    cases" below)
```

This single comparison formula covers both directions — it is
algebraically identical to "`pass_ratio >= target`" for `AT_LEAST`
(substitute `fail_ratio = 1 - pass_ratio` and
`allowed_bad_fraction = 1 - target` and the inequality is unchanged),
so nothing about `AT_LEAST` behavior changes; it simply extends
correctly to `AT_MOST` instead of requiring a second, contradictory
formula. The practical consequence for an `AT_MOST` SLI like
hallucination rate: the underlying evaluator still reports `PASS` for
"no hallucination" and `FAIL` for "hallucination detected" — `fail_ratio`
is then literally the hallucination rate, directly comparable to the
`AT_MOST` target.

`objective_direction` must still be recorded on every SLO: it is what
determines how `allowed_bad_fraction` is derived from `target`, even
though the comparison itself is direction-agnostic once
`allowed_bad_fraction` is known.

## Error Budget

```text
allowed_bad_events = allowed_bad_fraction × considered_events
observed_bad_events = the actual observed count of bad (FAIL, or
                       UNKNOWN-under-TREAT_AS_BAD) events — always an
                       exact integer, never derived by multiplying a
                       ratio back out
consumption_ratio = fail_ratio / allowed_bad_fraction
error_budget_remaining_fraction = 1 - consumption_ratio
```

Worked example, continuing the `TREAT_AS_BAD` case above
(`SLI = 99.20%`, `valid_events = 10,000`, `target = 99.5%`):

```text
allowed_bad_fraction  = 1 - 0.995 = 0.005
allowed_bad_events    = 0.005 × 10,000 = 50
observed_bad_events   = 80                       (the 50 FAIL + 30
                                                   UNKNOWN-under-
                                                   TREAT_AS_BAD)
fail_ratio            = 80 / 10,000 = 0.0080
consumption_ratio     = 0.0080 / 0.005 = 1.60
error_budget_remaining_fraction = 1 - 1.60 = -0.60
```

A negative remaining fraction means the budget is **exhausted and
exceeded** — the SLO is currently breached, not merely at risk. Error
budget remaining is not clamped to `[0, 1]` by the domain math itself;
clamping (if a presentation layer wants to show "0% remaining" rather
than "-60%") is a display decision, not a domain one, so that the
magnitude of a breach is never silently lost.

## Undefined and zero-tolerance cases

Two distinct situations make the formulas above unable to produce an
ordinary number, and they are not the same situation — see
[ADR-0002](adr/0002-reliability-mathematics-and-undefined-data-semantics.md)
for the full reasoning:

| Situation | `considered_events` | `allowed_bad_fraction` | Result |
|---|---|---|---|
| No data | `0` | any | SLI, error budget, and burn rate are all **undefined** — not `0`, not `1`. The SLO status is `UNKNOWN`. |
| Zero tolerance, intact | `> 0` | `0` (a 100% `AT_LEAST` or 0% `AT_MOST` target) | `0` observed bad events → budget fully intact (`remaining_fraction = 1`, burn rate `0`); this is well-defined, not undefined, because zero violations against a zero-tolerance target is a real, decidable outcome. |
| Zero tolerance, exceeded | `> 0` | `0` | `> 0` observed bad events → the true consumption/burn magnitude is unbounded (division by zero). This is reported as its own explicit state rather than as a floating-point infinity or `NaN` — see ADR-0002. |

## Burn Rate

Burn rate expresses how fast the error budget is being consumed
*relative to the rate that would exactly exhaust it by the end of the
observation window*, evaluated over a specific (typically shorter)
lookback period within that window.

```text
burn_rate = (bad_event_fraction_in_lookback_period) / allowed_bad_fraction
```

A `burn_rate` of `1.0` means the agent is consuming budget at exactly
the sustainable rate for the full window. A `burn_rate` of `4.7` means
the agent is consuming budget 4.7× faster than sustainable — i.e., if
sustained, the entire window's budget would be exhausted in
`window_length / 4.7`.

Worked example: a 30-day window, `target = 99.5%`
(`allowed_bad_fraction = 0.005`). Over the most recent 1-hour lookback,
suppose 200 eligible runs occurred with 3 bad events:

```text
bad_event_fraction_in_lookback_period = 3 / 200 = 0.015
burn_rate = 0.015 / 0.005 = 3.0
```

At a sustained burn rate of 3.0, the 30-day budget would be exhausted in
`30 days / 3.0 = 10 days`.

Burn rate and the cumulative `consumption_ratio` used in the error
budget above are, mechanically, the *same* division
(`bad_fraction / allowed_bad_fraction`) applied to two different
observation windows — a full window for the error budget, an arbitrary
shorter lookback for burn rate. This is a discovered simplification,
not two independently-specified formulas that happen to look similar;
see ADR-0002. The zero-data and zero-tolerance cases above therefore
apply identically to burn rate.

**Not specified here (future ADR item):** multi-window burn-rate
alerting (comparing a short lookback against a long one to distinguish a
brief spike from a sustained regression, as is common SRE practice) and
any rolling/streaming computation strategy. This document defines the
single-window, single-lookback mathematics only, sufficient for a batch
report; it deliberately does not yet define an alerting policy.

## Determinism and testability

Every example above is a fixed calculation with no free implementation
choice once the UNKNOWN policy and window boundaries are fixed. This
makes them suitable as golden test cases at M1: given the same inputs,
policy, and window, the domain kernel must reproduce these exact
numbers, and property-based tests must confirm the general invariants
(see [TESTING_STRATEGY.md](TESTING_STRATEGY.md)):

```text
0 <= SLI <= 1 whenever it is defined
error_budget_remaining_fraction is never NaN (it is a Fraction, or
    None with an explicit status — see ADR-0002)
identical input always produces identical output
```
