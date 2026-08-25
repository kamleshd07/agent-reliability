# Core concepts

## Agent run

One logical execution for a user request or task. Wrap that boundary—not every
token, helper, or tiny tool call. A genuine sub-agent may have a nested run.

## Evaluation

A judgment of one reliability property for one relevant execution or result.
One evaluation is not “whole agent quality”; an agent can have separate
indicators such as `task_success`, `policy_compliance`, and `tool_correctness`.

## Indicator

What is measured. Its stable name groups comparable observations, for example
`task_success`, `policy_compliance`, or `tool_correctness`.

## Evaluator

How an indicator is judged. Evaluators return `PASS`, `FAIL`, or `UNKNOWN`.
Built-in equality and predicate evaluators are deterministic.

## Provenance

Which evaluator name, version, optional configuration, and determinism produced
a judgment. Provenance prevents a change in measurement method from silently
looking like a change in agent reliability.

Suppose evaluator v1 reports `task_success = 99.7%` and v2 reports 96.8%.
Reporting a combined 98.25% would be misleading: the method changed, so the
observations are not automatically comparable. The engine returns an
`AggregationConflict` instead.

## SLI

The observed reliability measurement: counts and an exact ratio under a stated
policy for `UNKNOWN` outcomes.

## SLO

The desired target for an indicator. `task_success >= 99.5%` permits a 0.5%
bad-event rate. An `AT_MOST` objective describes a lower-is-better indicator;
for example, `policy_violation <= 0.1%` permits violations up to 0.1%.

## Error budget

The unreliability permitted by an SLO. Consuming the entire budget does not by
itself change the measurement—it explains how much tolerance remains.

## Burn rate

Observed bad-event rate divided by the SLO's allowed bad-event rate. It is not
“current failures divided by total failures.” M5 calculates a burn rate only
when the caller supplies an explicit lookback ratio; it does not retain data or
select a time window.

## UNKNOWN

Evaluation completed but could not make a definitive judgment. The caller must
choose an `UnknownPolicy`: exclude unknowns, count them as failures, or require
all observations to be known. The choice materially affects the SLI.

## EvaluationExecutionFailure

The evaluator itself raised, or provenance timestamping failed. This is
categorically not `FAIL` and not `UNKNOWN`; it produces no reliability
observation. Handle or retry it separately so infrastructure problems do not
become fabricated agent outcomes.
