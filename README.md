# Agent Reliability

**STATUS: PRE-ALPHA / UNDER ACTIVE DEVELOPMENT.** No public API is
stable. See [docs/COMPATIBILITY.md](docs/COMPATIBILITY.md).

> "Agent Reliability" is a working name for this project, chosen so
> that package/module naming can be changed later without contaminating
> the core domain model. Architectural decisions in this repository do
> not depend on the final name.

## Why this exists

AI agents are increasingly autonomous, but existing telemetry mostly
tells operators *what happened* — which model was called, which tool
ran, whether the HTTP request returned 200. It doesn't tell them whether
the agent is still doing its job.

## The reliability gap

Traditional observability answers "what happened?" LLM tracing answers
"what calls did the model and agent make?" Neither answers the question
that actually matters for running agents in production:

> Is this AI agent reliably accomplishing its intended job within
> defined operational boundaries?

## What "Agent SRE" means here

This project applies established SRE ideas — SLOs, error budgets, burn
rates — to autonomous agents, adapted carefully for the fact that agent
outcomes are evaluated, not just executed, and that evaluations can be
uncertain. See [docs/VISION.md](docs/VISION.md) for the full framing and
[docs/SLO_SEMANTICS.md](docs/SLO_SEMANTICS.md) for the mathematics.

## Core concepts

| Concept | Question it answers |
|---|---|
| Telemetry | What occurred? |
| Evaluation | Was some property of an execution satisfactory? |
| Reliability Indicator (SLI) | A precisely defined, measurable indicator |
| SLO | A target applied to an SLI over a window |
| Error Budget | The permitted amount of unreliability an SLO implies |
| Burn Rate | How fast that budget is being consumed |
| Reliability State | The interpreted operational state of an agent |

Full definitions: [docs/DOMAIN_MODEL.md](docs/DOMAIN_MODEL.md).

## Project status

This repository currently contains **milestone M0: repository and
specification foundation** — architecture, domain model, telemetry
contract approach, SLO mathematics, security model, and testing
strategy are documented and reviewed. **No reliability business logic
is implemented yet.** The package currently exports nothing but a
version string.

See [docs/ROADMAP.md](docs/ROADMAP.md) for the full milestone sequence
(M0 through M10) and what each one covers.

## Architecture

A layered, hexagonal (ports-and-adapters) design — domain logic has zero
dependency on any vendor SDK, telemetry backend, or agent framework.
See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) and
[docs/adr/0001-architecture-boundaries.md](docs/adr/0001-architecture-boundaries.md).

## Development

Requires Python >= 3.11.

```bash
python -m venv .venv
source .venv/bin/activate          # or .venv\Scripts\activate on Windows
pip install -e ".[dev]"

ruff check .
ruff format --check .
mypy src
pytest
python -m build
```

## Roadmap

See [docs/ROADMAP.md](docs/ROADMAP.md).

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). This project is not yet seeking
feature contributions beyond the current milestone's scope — issues and
discussion on the domain model and semantics are especially welcome
while those are still being validated.

## License

Apache License 2.0 — see [LICENSE](LICENSE). Chosen over MIT/BSD for its
explicit patent grant (Section 3) and contribution-termination clause,
which matter for infrastructure software with potential enterprise
adoption and multiple corporate contributors; chosen over a copyleft
license (e.g. GPL/AGPL) to keep the SDK freely embeddable in proprietary
agent applications, which is a stated goal of the project. See
[docs/adr/README.md](docs/adr/README.md) for the ADR process if you're
looking for the rationale behind other significant decisions in this
repository.
