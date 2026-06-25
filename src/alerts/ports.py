from __future__ import annotations

from typing import Protocol, runtime_checkable

from src.alerts.schemas import (
    AlertCandidate,
    GuideErrorRow,
    GuideProgressRow,
    MasteryRow,
)


@runtime_checkable
class AlertRepositoryPort(Protocol):
    """All Postgres access for the hourly alert cron (CLAUDE.md §8/§10, async)."""

    async def fetch_mastery_rows(self) -> list[MasteryRow]:
        """One row per (active enrollment, mastered topic) under the course's lead
        teacher, scoped to the course's subject."""
        ...

    async def fetch_course_sizes(self) -> dict[str, int]:
        """course_id -> count of ACTIVE enrollments (denominator for course ratios)."""
        ...

    async def fetch_guide_progress_rows(self) -> list[GuideProgressRow]:
        """Grading progress per published guide."""
        ...

    async def fetch_guide_error_rows(self) -> list[GuideErrorRow]:
        """Per (guide question, definitive error code) student counts on published
        guides — the error code is resolved from the live catalog source of truth."""
        ...

    async def insert_alert_if_absent(self, candidate: AlertCandidate) -> bool:
        """Insert the alert unless an equivalent one already exists today
        (teacher, alert_type, dedup_ref, day). Returns True iff a row was inserted."""
        ...
