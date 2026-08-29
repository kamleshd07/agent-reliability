# Contributing

Thank you for your interest. Agent Reliability `1.1.1` is released; public
APIs documented as stable in [docs/GA_CONTRACT.md](docs/GA_CONTRACT.md)
follow Semantic Versioning. Questions and precise critique remain welcome.

## Development setup

Requires Python 3.11–3.13.

```bash
python -m venv .venv
# POSIX: source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

Branches use `<type>/<short-description>`, for example
`fix/burn-rate-division-by-zero`. Keep commits reviewable and do not mix
unrelated semantic and formatting changes.

## Before opening a PR

```bash
ruff check .
ruff format --check .
mypy src
pytest --cov --cov-report=term-missing
python -m build
python scripts/verify_release_artifacts.py
```

CI repeats these checks. New behavior needs the appropriate unit, property,
contract, or integration tests; see [testing strategy](docs/TESTING_STRATEGY.md).
Reliability mathematics changes require invariant/property coverage.

## Architecture and documentation

Preserve the dependency direction and anti-goals in
[architecture](docs/ARCHITECTURE.md) and
[engineering principles](docs/ENGINEERING_PRINCIPLES.md). Do not add provider,
agent-framework, storage, or transport dependencies to the domain.

Hard-to-reverse decisions require an ADR alongside the implementation; see the
[ADR guide](docs/adr/README.md). Update documentation in the same PR whenever
public behavior or semantics change.

## Compatibility

Before 1.0, public APIs may receive limited breaking refinement. See
[compatibility](docs/COMPATIBILITY.md). Do not introduce convenience APIs that
hide evaluator methodology, UNKNOWN policy, provenance, or SLO choices.

## PR description checklist

- What changed and why?
- What alternatives were considered?
- What are the compatibility, security, and performance implications?
- How was it verified?

Security vulnerabilities must use the private process in [SECURITY.md](SECURITY.md),
not a public issue.
