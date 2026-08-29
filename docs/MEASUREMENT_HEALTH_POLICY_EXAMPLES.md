# Application policy examples for measurement health

`agent-reliability` reports the condition of reliability evidence. It does not
decide whether a business action is permitted.

```text
              OSS SDK
                 |
                 v
        Measurement Health
                 |
                 v
         Application Policy
          /      |       \
   fail-open  fail-close  bounded degradation
```

The examples below use application-local result enums and functions. None of
their decisions are SDK semantics.

## Fail open

[`examples/policy_fail_open.py`](https://github.com/kamleshd07/agent-reliability/blob/main/examples/policy_fail_open.py)
shows a low-criticality application continuing when evidence delivery is
degraded. It still records and displays the degraded signal. This is an
application choice, not an SDK default.

## Fail closed

[`examples/policy_fail_closed.py`](https://github.com/kamleshd07/agent-reliability/blob/main/examples/policy_fail_closed.py)
requires healthy evidence before its application-specific sensitive
capability is authorized. The SDK does not block the action; the application
maps the SDK signal to `AUTHORIZE` or `WITHHOLD`.

## Bounded degradation

[`examples/policy_bounded_degradation.py`](https://github.com/kamleshd07/agent-reliability/blob/main/examples/policy_bounded_degradation.py)
maps healthy evidence to full capability, degraded evidence to read-only
capability, and unavailable evidence to disabling a sensitive capability.
These generic capability levels are local to the example.

All three examples run offline, need no API key, use only the base package,
and have deterministic unit and subprocess contract tests.

## Policy errors

`RunHandle.evaluate_measurement_policy()` invokes the supplied application
policy explicitly. If it raises, that exception propagates. Suppressing it
would make an undocumented fail-open choice on behalf of the application.

## Trust boundary

A live `RunHandle.measurement_health` snapshot comes from SDK-observed state.
Applications can also construct `MeasurementHealthReport` values for storage,
transport, testing, or report assembly. Such values are data—not cryptographic
attestations. Never accept an acting agent's self-asserted `HEALTHY` value as
authorization evidence without an independent trusted boundary.
