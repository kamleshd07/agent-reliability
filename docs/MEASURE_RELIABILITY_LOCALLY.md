# Measure reliability locally

Once you have `ReliabilityObservation` values (see [Evaluate](EVALUATE.md)),
turn them into a reliability number with `evaluate_reliability(...)` (or
`evaluate_reliability_or_raise(...)`) from `agent_reliability.reliability`.
This page covers presenting the resulting `ReliabilityReport` — the
mathematics themselves are specified in
[LOCAL_RELIABILITY_ENGINE.md](LOCAL_RELIABILITY_ENGINE.md) and
[SLO_SEMANTICS.md](SLO_SEMANTICS.md); this page does not repeat them.

## For a human: `format_report`

```python
from agent_reliability.reporting import format_report

print(format_report(report))
```

```text
Indicator: task_success
Observations: pass=3 fail=1 unknown=0 considered=4 (unknown_policy=exclude)
Reliability: 75.00%
SLO: task-success target=75.00% direction=at_least status=MET
Error budget: status=measured remaining=0.00%
Measurement health: HEALTHY
```

`format_report` never recomputes reliability, SLO status, error-budget
consumption, or burn rate — every value comes directly from fields the
engine already produced on `report`. When there are no considered
observations, reliability and the error budget are shown as `NO DATA`, never
`0.00%` — a null result is not the same as a measured zero.

The exact text layout is a display convenience, not a wire format: it may
change between minor releases. Do not parse it; use `report_to_dict` for a
stable machine-readable shape.

## For a program: `report_to_dict`

```python
import json
from agent_reliability.reporting import report_to_dict

payload = report_to_dict(report)
print(json.dumps(payload, indent=2))
```

The result is JSON-compatible primitive structures only (`dict`/`list`/
`str`/`int`/`bool`/`None`) with a fixed, exhaustive key set: no arbitrary or
unbounded payload data is ever included, because `ReliabilityReport` itself
has no open-ended payload field. Exact `fractions.Fraction` values are
represented losslessly as `{"numerator": int, "denominator": int}` — no
rounded `float` sibling is included, so there is exactly one machine-readable
number for each ratio/fraction-shaped value, and it is always exact. A caller
that wants a display number computes `numerator / denominator` itself. This
is not a proprietary wire protocol — it is a plain dict you own once
returned.

## Next

[Test reliability](TEST_RELIABILITY.md) in your own test suite or CI.
