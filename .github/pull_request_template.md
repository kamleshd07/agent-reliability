## What changed?

## Why?

## Alternatives considered

## Compatibility implications

<!-- See docs/COMPATIBILITY.md. Does this change any public API,
     telemetry contract, or documented semantics? -->

## Security implications

<!-- See docs/SECURITY_MODEL.md if this touches input handling,
     serialization, metadata, or external I/O. -->

## Performance implications

<!-- See docs/ENGINEERING_PRINCIPLES.md #6 if this touches a hot path. -->

## How was this verified?

- [ ] `ruff check .`
- [ ] `ruff format --check .`
- [ ] `mypy src`
- [ ] `pytest`
- [ ] `python -m build`
- [ ] `python scripts/verify_release_artifacts.py` (release-affecting changes)

## Checklist

- [ ] Tests added/updated in the correct category (see [docs/TESTING_STRATEGY.md](../docs/TESTING_STRATEGY.md))
- [ ] Docs updated if semantics changed
- [ ] Stable API/semantic changes include compatibility-test updates
- [ ] Privacy and failure-isolation tests updated when a trust boundary changed
- [ ] ADR added if this is a hard-to-reverse architectural decision (see [docs/adr/README.md](../docs/adr/README.md))
