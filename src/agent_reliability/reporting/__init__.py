"""Local, offline presentation of a canonical :class:`ReliabilityReport`.

New additive namespace (post-1.1.1): consumes the existing
``agent_reliability.reliability.ReliabilityReport`` produced by
``evaluate_reliability``/``evaluate_reliability_or_raise`` and renders it for
a human (``format_report``) or for another program (``report_to_dict``).
Nothing here recomputes reliability, SLO status, error-budget consumption,
or burn rate — every value comes directly from the report's own fields. See
``format_report``/``report_to_dict`` docstrings for the exact contract.

No network I/O, no persistence, no proprietary wire protocol, and no
capture of arbitrary application payloads.
"""

from __future__ import annotations

from agent_reliability.reporting.formatting import format_report, report_to_dict

__all__ = ["format_report", "report_to_dict"]
