# First evidence delivery from a local build

This procedure verifies first evidence delivery from a **locally built distribution of the 1.3 release candidate** (`1.3.0rc1`, unpublished). The published 1.2.1 package does not contain the exporter; do not install the PyPI release expecting platform delivery. The candidate also contains the Experimental judge adapter, which this procedure does not use. It describes a local, disposable platform: no hosted Gentlity service and no production support are implied (see the [release notes](RELEASE_NOTES_1_3.md)).

## Prerequisites

Use Python 3.11+, a built wheel from the reviewed commit, and an initialized local platform with migrations at its pinned head. Install the exact artifact into a fresh virtual environment:

```sh
python -m venv .venv
.venv/bin/python -m pip install '/absolute/path/to/agent_reliability-1.3.0rc1-py3-none-any.whl[http]'
.venv/bin/python -c 'import agent_reliability; print(agent_reliability.__version__, agent_reliability.__file__)'
```

The path is an artifact path, not a public package version recommendation. Confirm the module comes from this environment's `site-packages`, not a source checkout. Do not set `PYTHONPATH` to SDK source for installation verification.

An authorized platform operator/administrator must create an organization (an operator-only step: the organization-creation API is available only in the platform's local development-header mode), bootstrap its first administrator with the platform's operator bootstrap command, then use authenticated registry APIs to create a workspace, environment, agent, version and deployment, and issue a machine credential with only `evidence:ingest`. Do not enable development tenant-header authentication for hosted use. The deployment must belong to the credential's organization. Its agent key, display name, version and environment key must exactly match the values below. Never use customer data for the demonstration. Human read/SLO-authoring permissions are separate from the machine credential.

## Run the synthetic example

Supply these environment variables through your local secret manager or shell session; do not paste a token into shell history, CLI arguments, screenshots or logs:

- `GENTLITY_EVIDENCE_URL`: complete `/api/v1/evidence/runs` URL. HTTPS with normal certificate verification for any non-loopback destination; local loopback HTTP is for disposable verification only.
- `GENTLITY_MACHINE_TOKEN`: the one-time returned machine credential, securely held.
- `GENTLITY_DEPLOYMENT_ID`: deployment UUID.
- `GENTLITY_AGENT_KEY`, `GENTLITY_AGENT_NAME`, `GENTLITY_AGENT_VERSION`, `GENTLITY_ENVIRONMENT_KEY`: exact deployment identity.

```sh
.venv/bin/python examples/platform_quickstart.py
```

The example creates one run and one synthetic `task-success=PASS` evaluation, followed by terminal and health evidence. It sends no prompts, responses, tool arguments or model credentials. Its success message requires acknowledged committed/duplicate dispositions and an empty queue, not merely successful local admission. Application evaluation success and transport health remain separate facts. The sample supplies a known deterministic result; it does not evaluate a real customer's task.

## Verify insight, not just HTTP

As a human member of the same organization, read `/api/v1/evidence/runs?deployment_id=<uuid>` and that run's evaluations. Query `/api/v1/reliability/deployment/<uuid>/summary` with `indicator=task-success` and UTC `start`/`end` bracketing the run. Expect one pass and no failures for a fresh deployment, not a seed-derived number. Historical `as_of` can change visibility. Create a deployment-scoped SLO through `POST /api/v1/slos` with an effective revision before the run, an explicit target and window; read `/api/v1/slos/<id>/evaluation?evaluation_time=<UTC instant>`. The SLO's measurement must match the same persisted evidence and correct time window. Machine credentials cannot authorize these read/authoring operations.

For a reproducible negative demonstration, a second run recording FAIL for the same indicator yields pass 1 / fail 1 and reliability 0.5 in a fresh scope. A 0.99 target then violates compliance. Compare stored canonical digests and use a second synthetic tenant to verify foreign deployment/read denial. Retrying the *same serialized event* is idempotent; rerunning this example creates a new run/events and correctly increases totals.

## What this example guarantees (and does not)

Delivery is best-effort with idempotent acknowledgement, not exactly-once and not durable: each record
gets a few jittered attempts (under about 2 s in total by default), so a platform outage longer than that
loses the affected evidence unless you raise `retry_max_attempts`; loss is reported in the delivery
status, never silent. Indicator names and other identifiers you choose are sent verbatim: never derive
them from user input, model output or secrets. Details: [HTTP exporter](HTTP_EXPORTER.md).

## Troubleshooting and bounded behavior

- Missing configuration/invalid deployment identity: correct local configuration before retrying. Never weaken schema validation or change supported source literals.
- 401: missing/expired/revoked machine credential. Rotate through the provider callback and explicitly resume the documented auth gate; no fallback to cookies/human tenant headers.
- 403: verify scope/credential permissions;404: verify deployment ownership and registry identity. Do not probe other tenants.
- 409: identity/payload conflict is a terminal error, not an automatic overwrite.
- 422: request contract mismatch; use published schema-v2 fixtures. The exporter serializes supported event types; do not hand-add raw content.
- 429/5xx/timeouts: inspect redacted delivery status, retry/throttle and uncertainty counters. Retry attempts, queue bytes/records and residence are bounded; a timeout may still have committed. Replaying identical event bytes avoids duplicate storage.
- TLS verification failure/redirect: correct endpoint/certificate configuration, then explicitly resume the endpoint gate. Never disable verification or follow credential-bearing redirects.
- Queue rejection/backpressure: inspect delivery-health evidence; bound event production or intentionally change documented capacities. The memory queue is not durable across process death. Flush/close deadlines do not guarantee delivery.

See [HTTP exporter](HTTP_EXPORTER.md) for exact counters/defaults, gates, cancellation/uncertainty semantics and async usage. This local guide does not establish hosted readiness or close authentication deployment-validation gates.
