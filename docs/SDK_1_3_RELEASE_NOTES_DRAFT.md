# SDK 1.3 release notes — draft, not released

Proposed scope: optional HTTP transport for content-free run/evaluation/health evidence; bounded memory queues/retries/residence; validated committed/duplicate acknowledgements; schema-v2 deployment identity and machine authentication; sync/async delivery status; TLS verification and privacy-safe diagnostics. Core offline APIs remain dependency-free and existing 1.2.x compatibility tests apply.

Known limitations: in-memory queue loses pending evidence on process death; local admission is not durable delivery; a timeout/cancellation can leave commit uncertainty; no automatic step/tool/token instrumentation; no notification delivery or scheduler supplied by this SDK. Hosted readiness, capacity and production latency are not established by local tests.

Release gates still open: named release/security/rollback roles; explicit public API classification (exporter currently INTERNAL); exact 1.3 version and compatible artifact selection; owner decision resolving Experimental P29 already present on main versus P28-only first release; final package rebuild and install/contract/E2E verification of the selected artifact; shared TEST/deployment validation separately authorized; release owner approval and publication credentials. Do not tag, publish or silently strip the judge to bypass its pilot gates. Experimental provider calibration and safeguards remain separate. This file changes neither existing release decisions nor D14 status.

See [local quickstart](PLATFORM_QUICKSTART.md) for the verified development path. Final release notes must identify the actual selected commit/artifact hashes and repeat validation after any packaging/version/content change.
