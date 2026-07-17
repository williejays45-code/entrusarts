"""Closed ART-001 failure vocabulary."""


class ArtifactStorageError(RuntimeError):
    """Fail-closed artifact authority error with a stable reason code."""

    def __init__(self, reason_code: str):
        super().__init__(reason_code)
        self.reason_code = reason_code

