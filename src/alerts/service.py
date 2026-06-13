from __future__ import annotations

import structlog

from src.alerts.detectors import (
    detect_at_risk_students,
    detect_common_error_in_topic,
    detect_guide_common_error,
    detect_guide_grading_complete,
    detect_student_drop,
    detect_unit_off_track,
)
from src.alerts.ports import AlertRepositoryPort
from src.alerts.schemas import AlertCandidate, AlertRunOutcome
from src.shared.settings import Settings

logger = structlog.get_logger()


async def run_hourly_alerts(
    *, repo: AlertRepositoryPort, settings: Settings
) -> AlertRunOutcome:
    """Run every detector over the current mastery + guide state and insert the deduped
    candidates. Pure of any concrete DB: all I/O goes through the injected port, so the
    flow is unit-testable with a fake repo (CLAUDE.md §8, ADR v9 A9.2)."""
    mastery = await repo.fetch_mastery_rows()
    sizes = await repo.fetch_course_sizes()
    guide_progress = await repo.fetch_guide_progress_rows()
    guide_errors = await repo.fetch_guide_error_rows()

    candidates: list[AlertCandidate] = []
    candidates += detect_at_risk_students(
        mastery,
        pknown_floor=settings.alert_at_risk_pknown_floor,
        min_topics=settings.alert_at_risk_min_topics,
    )
    candidates += detect_common_error_in_topic(
        mastery,
        sizes,
        pknown_floor=settings.alert_at_risk_pknown_floor,
        course_ratio=settings.alert_topic_struggle_ratio,
    )
    candidates += detect_student_drop(
        mastery, drop_threshold=settings.alert_student_drop_trend
    )
    candidates += detect_unit_off_track(
        mastery, pknown_floor=settings.alert_unit_off_track_floor
    )
    candidates += detect_guide_grading_complete(
        guide_progress, sizes, complete_ratio=settings.alert_guide_complete_ratio)
    candidates += detect_guide_common_error(
        guide_errors, sizes, course_ratio=settings.alert_guide_common_error_ratio)

    inserted = 0
    by_type: dict[str, int] = {}
    for candidate in candidates:
        if await repo.insert_alert_if_absent(candidate):
            inserted += 1
            by_type[candidate.alert_type] = by_type.get(
                candidate.alert_type, 0) + 1

    logger.info(
        "hourly_alerts_run",
        candidates=len(candidates),
        inserted=inserted,
        by_type=by_type,
    )
    return AlertRunOutcome(
        candidates=len(candidates), inserted=inserted, by_type=by_type
    )
