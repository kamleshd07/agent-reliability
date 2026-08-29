# Security Model

## Measurement health

Measurement health retains only a bounded set of structural enum reasons. It
never retains exception objects/messages, tracebacks, prompts, outputs, tool
data, credentials, PII, or arbitrary metadata. State is run-local and bounded.
Live `RunHandle` health derives from SDK-observed failures; freely constructed
values are not attestations and must not be trusted from agent content as
authorization evidence. See ADR-0009.

Status: threat model established at M0; mitigations are implemented
incrementally as the corresponding functionality is built. M2 adds the
first real runtime capture surface (an in-process instrumentation SDK).
There is still no network code or exporter. M4 adds only trusted in-process
evaluator execution and bounded attribution values. M5 adds pure in-memory
aggregation over bounded structural observations and no I/O.

## Threats considered

| Threat | Concern |
|---|---|
| Prompt leakage | Agent prompts captured in telemetry may contain secrets, PII, or proprietary instructions |
| Response leakage | Agent/model responses may contain the same |
| PII collection | Run/evaluation metadata may incidentally capture personal data |
| Credential leakage | Tool arguments or environment context may contain API keys, tokens, passwords |
| Tool-argument leakage | Tool call parameters may contain sensitive business or customer data |
| Telemetry poisoning | A malicious or compromised agent could emit crafted telemetry to manipulate reported reliability |
| Malicious metadata | Attacker-controlled strings in metadata fields (injection into downstream systems, log injection) |
| Oversized payloads | Unbounded prompt/response capture could exhaust memory, disk, or network budgets |
| Exporter abuse | A malicious or misconfigured exporter destination could be used to exfiltrate data |
| Untrusted evaluator output | An evaluator (especially LLM-as-judge) is a form of untrusted input to the reliability engine and must not be treated as a trusted computation |
| Resource exhaustion | Unbounded queues, unbounded metadata, or unbounded evaluation fan-out could exhaust CPU/memory in the host application |

## Principles

- **Bounded input.** Every field that accepts caller-provided data
  (metadata, evidence, tool arguments) has a documented size limit
  enforced at the boundary, not left to the exporter or backend to
  discover.
- **Bounded queues.** No unbounded queue anywhere in the SDK; see
  [ENGINEERING_PRINCIPLES.md](ENGINEERING_PRINCIPLES.md) #13.
- **Bounded metadata.** Open key/value metadata bags (on `AgentRun`,
  `Evaluation`) have documented key-count and value-size limits.
- **Safe serialization.** Telemetry serialization never executes
  arbitrary code and never deserializes caller data into live objects
  (no `pickle` or equivalent over untrusted data).
- **No arbitrary code execution.** Evaluator and exporter configuration
  is data, not code, wherever the SDK provides a configuration surface.
- **No implicit secret capture.** Raw payload (prompt/response/tool-
  argument) capture is opt-in per
  [ENGINEERING_PRINCIPLES.md](ENGINEERING_PRINCIPLES.md) #7. Metadata-
  only operation is the default posture; nothing in the SDK assumes raw
  content capture is always available.
- **Untrusted evaluator output is data, not authority.** A judge
  evaluator's `PASS`/`FAIL`/`UNKNOWN` output feeds the reliability
  engine as an ordinary evaluation with recorded provenance (see
  [DOMAIN_MODEL.md](DOMAIN_MODEL.md)); it is never given a code-
  execution path or elevated trust over a deterministic evaluator's
  output.
- **Telemetry poisoning resistance is provenance, not cryptography, at
  this stage.** Every evaluation records evaluator identity and version
  (see DOMAIN_MODEL.md) so a compromised or misbehaving evaluator's
  output is at least attributable. Cryptographic integrity of telemetry
  is out of scope for the current milestones and would be a future ADR
  if a threat model requiring it emerges (e.g. multi-tenant ingestion).

## M2/M2.1: what is actually captured

M2's instrumentation events
(`agent_reliability.ports.events.{RunStarted,RunCompleted,RunFailed,EvaluationRecorded}`)
carry only: identifiers (`run_id`, `parent_run_id`), `AgentIdentity`
(`agent_id`/`name`/`version`/`environment` — all caller-supplied,
short, structural strings), timestamps, `RunStatus`, the recorded
`indicator` name and `EvaluationOutcome`, and — for `RunFailed` — the
failing exception's **class name only**. M2 never captures prompts,
responses, tool arguments, message history, or model internals; nothing
in the SDK reads or serializes arbitrary application objects. This
directly satisfies [ENGINEERING_PRINCIPLES.md](ENGINEERING_PRINCIPLES.md)
#7 (metadata-only operation as the default, and — for M2 — the *only*
mode; opt-in raw payload capture does not exist yet and is not planned
before a milestone that actually needs it).

`RunFailed.exception_type` deliberately excludes `str(exc)`, the
exception object, and its traceback — `str(exc)` can contain arbitrary
application data (e.g. a `ValueError` embedding a user's email or an
account balance), and retaining the traceback would keep stack frames
(and everything they close over) alive longer than necessary. See
[SDK_DESIGN.md](SDK_DESIGN.md)'s event model section and
[ADR-0004](adr/0004-instrumentation-failure-isolation.md).

### Diagnostics are a scoped, documented exception

`SdkDiagnostic` (delivered to a caller-supplied `DiagnosticHandler` when
an instrumentation dependency — clock, id generator, sink — fails) does
carry the original exception object, including its message. This is a
deliberate, narrow exception to the "no message content" rule above: the
diagnostic channel's entire purpose is letting an operator debug the
SDK's *own* malfunctions (e.g. "why does my sink keep failing"), it is
delivered synchronously and in-process only, never serialized or
exported by anything in M2. The default `LoggingDiagnosticHandler` is
privacy-safe: it logs only component, operation, run ID if known, and
exception class name. It never logs `str(exception)`, `repr(exception)`,
`exception.args`, a traceback/stack trace, or the raw diagnostic payload,
and retains nothing afterward. This sanitization was added at M2.1 — see
[ADR-0005](adr/0005-instrumentation-initialization-degraded-mode.md),
which also documents that the default previously logged the exception's
`repr()`, including its message.

A custom diagnostic handler receives the underlying exception and is
therefore an explicit trusted in-process boundary responsible for its own
sensitive-data handling. A caller that persists or forwards diagnostics
accepts responsibility for what that custom path may expose.

### New M2/M2.1 threats considered

| Threat | Mitigation |
|---|---|
| A broken/malicious sink used to crash the host application | Every `sink.emit()` call runs inside the SDK's failure-isolation wrapper (only `Exception` caught, never `BaseException`) and can never raise into application code — see ADR-0004 |
| A broken/malicious sink used to replace the application's own exception | `__exit__`/`__aexit__` never raise due to instrumentation failure, full stop, regardless of what the caller's code did — see ADR-0004 |
| Clock/ID/internal start failure prevents the application body | M2.1 returns a no-telemetry degraded handle, emits no fake lifecycle data, and leaves the active context unchanged — see [ADR-0005](adr/0005-instrumentation-initialization-degraded-mode.md) |
| Exception secrets leak through default diagnostics | The default logger records sanitized structural metadata and exception class only; tests assert message, repr, secret, and traceback absence — see ADR-0005 |
| Unbounded memory growth from accumulated events | No queue exists in M2 (see [SDK_DESIGN.md](SDK_DESIGN.md), "Buffering"); `InMemoryEventSink` explicitly retains every event without limit and is test/local-only, never production-safe |
| A diagnostic handler itself crashing the application | Caught and dropped — the one deliberate last-resort suppression in the SDK (ADR-0004) |
| Context/identity leakage across concurrent `asyncio` tasks | Relies on `contextvars`' own per-task isolation, not custom SDK logic; tested with 150 concurrent tasks (see the M2 test report) |

## M3 OpenTelemetry capture surface

The optional adapter exports only the allowlisted identity, run correlation,
and terminal fields in [OTEL_MAPPING.md](OTEL_MAPPING.md). It disables OTel's
automatic exception recording and never sends the exception object, message,
stack trace, prompt, response, tool data, user data, arbitrary event fields,
or baggage. The project configures no provider or exporter.

Agent identity fields and run IDs are application-supplied and may be high
cardinality. They must not contain secrets or unbounded user content. They are
span attributes only and must not become metric dimensions. Host SDK span
limits and backend policy remain the deployment enforcement point. OTel
failures use the existing sanitized diagnostic channel.

## M4 evaluation capture and trust boundary

M4 never automatically retains, copies, renders, serializes, logs, or emits
evaluation input or output. `EvaluationResult` contains only outcome, bounded
reason code, and immutable evaluator provenance. There is no arbitrary
evidence/metadata mapping, score, confidence, human message, or exception
field. Configuration identity is caller-supplied non-sensitive machine data;
the library never hashes raw configuration.

Safe evaluator failures use the existing diagnostic channel. The returned
`EvaluationExecutionFailure` carries only evaluator identity when available,
failure stage, and exception class name. The default logger never renders the
input or exception message/representation/traceback. As before, a custom
diagnostic handler receives the raw exception and is a trusted in-process
boundary responsible for its handling.

Evaluator implementations and predicate callables are explicitly supplied,
trusted application code. M4 does not discover, deserialize, register, or
sandbox arbitrary Python code. Evaluator authors own any internal mutable
state and concurrency safety. LLM, human, remote, dataset, and platform
evaluators remain absent.

## M5 local analysis boundary

M5 accepts only a bounded indicator, categorical outcome, and optional M4
provenance. It never accepts or renders arbitrary metadata, original evaluator
input/output, exception content, reason text, or run payload. Conflicts expose
only a bounded frozenset of enum reasons; they do not reproduce hostile values.
Each iterable is streamed once and observations are not retained, keeping
auxiliary memory bounded. Caller-owned iterables may still be infinite, slow,
or raise; M5 adds no threads, timeout enforcement, sandbox, logging, storage,
or network boundary.

## Explicitly out of scope for now

An elaborate security system (signing, encryption at rest, access
control, multi-tenant isolation) is not being built during initial SDK
development. Those concerns belong to a future hosted backend / control
plane, not the embeddable open-source SDK, and will get their own threat
model when that component exists.

## Where this connects to CI

[ARCHITECTURE.md](ARCHITECTURE.md) explains why `.github/workflows/security.yml`
(dependency/SAST scanning) is deferred rather than added at M0: there is
no dependency surface or untrusted-input handling yet to scan
meaningfully. It should be added at the milestone that first introduces
a runtime dependency or a network/deserialization boundary.
