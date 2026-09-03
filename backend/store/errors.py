"""Store-layer error types.

AD-6 / FR-17 — ghost-validation guardrail enforced at the persistence boundary.
"""


class TestArtifactMissingError(RuntimeError):
    """AD-6 / FR-17: raised when a ticket lacks a verifiable test artifact."""

    def __init__(self, project_id: str, ticket_id: str):
        super().__init__(
            f"Test artifact missing for ticket {ticket_id} in project {project_id} — "
            "cannot transition to Done (FR-17/AD-6)."
        )
        self.project_id = project_id
        self.ticket_id = ticket_id
