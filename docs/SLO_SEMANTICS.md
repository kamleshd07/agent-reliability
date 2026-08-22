# SLO Semantics

Status: **specification only** — this document defines the mathematics
that milestone M1 (Reliability Domain Kernel) must implement exactly.
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

For a ratio SLI with `objective_direction = ">= target"`:

```text
target = 0.995                       (99.5%)
allowed_bad_fraction = 1 - target    = 0.005  (0.5%)
```

For `objective_direction = "<= target"` (a "lower is better" SLI, e.g.
a hallucination rate), the SLI itself is already defined as the *bad*
fraction, so:

```text
target = 0.001                       (0.1%)
allowed_bad_fraction = target        = 0.001
```

Both directions reduce to the same downstream quantity —
`allowed_bad_fraction` over the window — which is what feeds the error
budget below. This is why `objective_direction` must be recorded on
every SLO: it changes how `allowed_bad_fraction` is derived from
`target`, even though everything after that point is direction-agnostic.

## Error Budget

```text
allowed_bad_events = allowed_bad_fraction × valid_events
consumed_bad_events = valid_events × (1 - SLI)     [for ">=" SLOs]
                    = valid_events × SLI            [for "<=" SLOs,
                                                      since SLI already
                                                      represents the bad
                                                      fraction]
error_budget_remaining_fraction =
    (allowed_bad_events - consumed_bad_events) / allowed_bad_events
```

Worked example, continuing the `TREAT_AS_BAD` case above
(`SLI = 99.20%`, `valid_events = 10,000`, `target = 99.5%`):

```text
allowed_bad_fraction  = 1 - 0.995 = 0.005
allowed_bad_events    = 0.005 × 10,000 = 50
consumed_bad_events   = 10,000 × (1 - 0.9920) = 80
error_budget_remaining_fraction = (50 - 80) / 50 = -0.60
```

A negative remaining fraction means the budget is **exhausted and
exceeded** — the SLO is currently breached, not merely at risk. Error
budget remaining is not clamped to `[0, 1]` by the domain math itself;
clamping (if a presentation layer wants to show "0% remaining" rather
than "-60%") is a display decision, not a domain one, so that the
magnitude of a breach is never silently lost.

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
0 <= SLI <= 1
error_budget_remaining_fraction is never NaN
identical input always produces identical output
```
