"""
Release Notes Agent — Stub
==========
Not yet implemented. Structure is in place.
This agent will be built after the CS Documentation Agent MVP is validated.

Reference: GACI Whitepaper v1.2, Section 2.3
"""


class ReleaseNotesAgent:
    """Stub — implement after CS Documentation Agent MVP is validated."""

    AGENT_ID = "release-notes-agent-v1.0"
    CONTENT_CATEGORY = "release-notes"

    def run(self, context, parent_task_key: str) -> dict:
        raise NotImplementedError(
            f"{self.__class__.__name__} is not yet implemented. "
            "See GACI Whitepaper v1.2, Section 2.3 for specification."
        )
