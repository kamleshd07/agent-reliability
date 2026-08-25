from __future__ import annotations

from agent_reliability.sdk.diagnostics import SdkDiagnostic


class CollectingDiagnosticHandler:
    """Appends every diagnostic it receives — lets tests assert that a
    suppressed failure was actually reported, not just that it didn't
    raise."""

    def __init__(self) -> None:
        self.diagnostics: list[SdkDiagnostic] = []

    def handle(self, diagnostic: SdkDiagnostic) -> None:
        self.diagnostics.append(diagnostic)


class BrokenDiagnosticHandler:
    """A diagnostic handler that always raises — proves the SDK's
    absolute last-resort suppression around the handler itself."""

    def handle(self, diagnostic: SdkDiagnostic) -> None:
        raise RuntimeError("diagnostic handler is broken")
