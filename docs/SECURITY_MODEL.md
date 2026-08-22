# Security Model

Status: threat model established at M0; mitigations are implemented
incrementally as the corresponding functionality is built. Nothing
below is implemented yet — there is no network code, no exporter, and
no evaluator execution in the repository at M0.

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
