# Security policy

## Reporting a vulnerability

Do not disclose vulnerabilities, exploit details, secrets, or affected-user
data in a public issue. Use GitHub private vulnerability reporting on this
repository: **Security → Report a vulnerability**.

Repository maintainers must enable that feature before the first public GA
release. If it is unavailable, publication is blocked until a real private
channel is configured and documented. No unverified address is invented here.

Include:

- affected version or commit;
- impact and affected configurations;
- minimal reproduction or proof of concept;
- known mitigations; and
- a safe way to coordinate disclosure, when appropriate.

Maintainers should acknowledge receipt promptly, validate impact, coordinate a
fix and advisory, and agree on disclosure timing with the reporter.

## Scope

See [SECURITY_MODEL.md](docs/SECURITY_MODEL.md). The base package has zero
runtime dependencies and performs no network I/O or deserialization. The
optional OpenTelemetry extra adds its API only; a host-configured exporter may
perform network I/O, but Agent Reliability does not configure one.

Instrumentation does not automatically capture prompts, responses, tool
arguments/results, credentials, exception messages, tracebacks, PII, or
arbitrary application payloads. Custom diagnostic handlers receive the
original exception and are an explicitly trusted boundary.

## Supported versions

Before 1.0, only the latest published prerelease receives security fixes.
During 1.x, the latest minor line receives fixes; maintainers may backport a
critical fix when impact and feasibility justify it. Unsupported versions must
upgrade. See [VERSIONING.md](docs/VERSIONING.md).
