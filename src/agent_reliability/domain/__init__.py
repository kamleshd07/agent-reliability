"""Domain layer: pure reliability concepts (Run, Evaluation, SLI, SLO,
Error Budget, Reliability State, Reliability Event).

Rules for this package, enforced by review (not yet by tooling):

- No imports from ``agent_reliability.adapters``.
- No imports of network, filesystem, or database libraries.
- No dependency on any specific LLM provider or agent framework.
- Values should be immutable where practical.

Not implemented yet. See docs/DOMAIN_MODEL.md for the specification
this package will eventually implement (milestone M1).
"""

from __future__ import annotations
