# Test reliability

`agent_reliability.testing.assert_slo_met` turns a `ReliabilityReport` (or
the `AggregationConflict` that `evaluate_reliability` can return instead)
into a plain `AssertionError` — usable from `pytest`, `unittest`, or an
ordinary script. It adds no runtime dependency, not even on `pytest`.

```python
from agent_reliability.testing import assert_slo_met

assert_slo_met(report)  # raises AssertionError unless report's SLO is MET
```

A `pytest` test typically looks like:

```python
def test_task_success_meets_slo() -> None:
    report = build_report()  # your own aggregation, as in slo_assertion.py
    assert_slo_met(report, message="task_success nightly regression")
```

## What counts as passing

Only `SloStatus.MET`, exactly as the engine already decided it — see
[SLO_SEMANTICS.md](SLO_SEMANTICS.md) for the exact comparison
(`observed_bad_fraction <= allowed_bad_fraction`, boundary inclusive). In
particular:

- **No data** (`SloStatus.UNKNOWN`, no considered observations) is **not**
  treated as passing. The assertion fails with `"NO DATA"` in its message
  rather than silently succeeding on an empty sample.
- An **`AggregationConflict`** — measurement methodologies that cannot be
  compared — is **not** swallowed. Passing one to `assert_slo_met` fails the
  assertion with the conflict's bounded reasons, exactly like a breached SLO
  would.
- `assert_slo_met` never reinterprets `UNKNOWN` observations itself; that
  policy was already decided by the `UnknownPolicy` you chose when building
  the report (see [Evaluate](EVALUATE.md#what-unknown-means-here)).

## What the failure message contains

Only bounded, structural fields already on the report: indicator and SLO
names, `pass`/`fail`/`unknown` counts, the `UnknownPolicy` applied, and the
observed/target ratios. It never includes application payloads, because the
domain report itself carries none — see
[SECURITY_MODEL.md](SECURITY_MODEL.md).

Run [`examples/slo_assertion.py`](../examples/slo_assertion.py) to see both
a `MET` assertion (passes silently) and a `BREACHED` one (raises, caught
there only to print both outcomes in one script).

## Next

Back to the [documentation index](README.md), or
[OpenTelemetry](OTEL_MAPPING.md) if you also want distributed tracing.
