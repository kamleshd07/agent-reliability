# Agent Reliability SDK 1.4 — release notes

**Version `1.4.0`**, a backward-compatible minor release under [VERSIONING.md](VERSIONING.md). The release date is
the upload date shown by the package index and the GitHub release. Everything new is **Experimental**, optional,
and adds **no mandatory runtime dependency** (`dependencies = []` is unchanged). Nothing is sent anywhere unless
you pass an exporter.

## Stable and Experimental

| Surface | Class | Notes |
|---|---|---|
| Every stable 1.x API in [GA_CONTRACT.md](GA_CONTRACT.md), reliability and SLO semantics, the `EventSink` contract | **Stable, unchanged** | No stable source file changed since 1.3.0 |
| HTTP evidence exporter (`adapters.http_event_sink`), wire schema version 2 | Experimental, unchanged | As in 1.3 |
| `agent_reliability.experimental.instrumentation`, `adapters.langchain_instrumentation` | **Experimental, new** | LangChain execution instrumentation |
| `adapters.http_execution_exporter` (`ExecutionHTTPExporter`) | **Experimental, new** | Living under `adapters` does not make it stable |
| `experimental.judge` additions (`SemanticChecks`, `JudgeDimension.ANSWER_RELEVANCE`, admission hook) | **Experimental** | Default judge behaviour unchanged |
| `agent_reliability.experimental.calibration` | **Experimental, new** | Calibration datasets, metrics, policy, status |

Experimental names, signatures and defaults may change in a minor release with release notes.

## What is new

1. **LangChain execution instrumentation**: `experimental.instrumentation.instrument(...)`. Bounded local run, step,
   tool and model traces and `ExecutionTrace.summary()`. Optional `langchain` extra.
2. **Execution exporter**: `ExecutionHTTPExporter` (optional `http` extra) delivers content-free execution facts
   (steps, tool outcomes, declared tool classes and actions, provider-reported token counts) to the platform's
   existing execution endpoints. Prompts, answers, tool arguments and results are never sent.
3. **Semantic evaluation facade**: `SemanticChecks` and the uncalibrated `judge-answer-relevance` rubric. A model
   verdict is never authoritative, and an evaluator failure is never a FAIL.
4. **Judge calibration and admission**: `experimental.calibration` and the opt-in `admission=` hook.
5. Examples and documentation (`examples/` ships in the source distribution only, never in the wheel).

## Supported versions

* Python 3.11, 3.12 and 3.13 (`requires-python >=3.11`); the installed wheel was exercised on all three.
* Optional `langchain` extra: `langchain-core>=1.0,<2`, tested at 1.0.0, 1.2.31, 1.6.13 and 1.7.6; 0.x and 2.x are
  refused at setup. There is no automated CI matrix over this range yet.
* Optional `http` extra: `httpx>=0.28.1,<0.29`. The `otel` extra is unchanged.

## Behaviour change (Experimental only)

A value ending in a single newline no longer matches a schema pattern ending in `$` (the ECMA-262 reading). In 1.3.0
it was accepted. This affects only `experimental.judge.calibration.load_cases` input (for example an identifier such as
`"a01\n"`) and the experimental calibration file formats; every other pattern verdict is identical to 1.3.0, checked
over all bundled schema patterns. If a file is rejected for this reason, remove the trailing newline from the value. No
stable API, wire contract or evaluator identity changed.

## Limitations (read before using)

* **Delivery is best effort and in memory.** Both exporters hold a bounded in-memory queue. Queued evidence is lost if
  the process dies, and a platform outage longer than the retry budget loses the affected records (reported as
  `retry_exhausted`). There is no durable spool, and delivery is neither exactly-once nor durable.
* **The model-backed judge is uncalibrated.** Reference rubrics are examples. No accuracy, calibration or human
  agreement claim is made, and no adjudicated human-labelled reference set exists. "Calibrated" in the calibration
  module only ever means "meets your policy on your named dataset".
* **Content-free by design, but identifiers you choose are sent as written.** Keep indicator names and tool labels free
  of sensitive text.
* Validated locally and synthetically: a scripted agent against a local platform, not a real model provider, a hosted
  deployment or a customer.
* **Not customer-ready.** The customer-use gates have not been satisfied by this release: an unmet
  different-family judge smoke gate, no adjudicated human reference set, no durable spool, no CI matrix over the
  `langchain-core` range, unsigned pilot safeguards SG-1 to SG-6 ([P29_PILOT_SAFEGUARDS.md](P29_PILOT_SAFEGUARDS.md))
  and no customer validation. Publishing this Experimental package does not change that.

## Migration and rollback

Nothing to migrate unless you pass identifiers ending in a newline to the calibration entry points. To roll back, pin
`agent-reliability==1.3.0` (and drop the `langchain` extra); the Experimental modules above do not exist there and the
stable API is identical. A published file is never replaced: a defect is fixed by a new version.
