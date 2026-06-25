from __future__ import annotations

from collections import defaultdict

from src.alerts.schemas import (
    AlertCandidate,
    AlertType,
    GuideErrorRow,
    GuideProgressRow,
    MasteryRow,
)
from src.llm_classifier.catalog import SPECIAL_ERROR_TYPES

# TeacherAlert.severity is a free String column; we keep the ErrorSeverity vocabulary
# (LOW | MED | HIGH) so the web dashboard can reuse one severity scale (A9.2).
SEV_LOW = "LOW"
SEV_MED = "MED"
SEV_HIGH = "HIGH"


def _severity_from_ratio(ratio: float) -> str:
    if ratio >= 0.66:
        return SEV_HIGH
    if ratio >= 0.4:
        return SEV_MED
    return SEV_LOW


def _deficit_severity(value: float, floor: float) -> str:
    deficit = floor - value
    if deficit >= 0.2:
        return SEV_HIGH
    if deficit >= 0.1:
        return SEV_MED
    return SEV_LOW


def _drop_severity(trend: float, threshold: float) -> str:
    # threshold is negative; a more negative trend is a steeper drop.
    if trend <= threshold * 2:
        return SEV_HIGH
    if trend <= threshold:
        return SEV_MED
    return SEV_LOW


def _count_severity(count: int, base: int) -> str:
    if count >= base * 2:
        return SEV_HIGH
    if count >= base:
        return SEV_MED
    return SEV_LOW


def detect_at_risk_students(
    rows: list[MasteryRow], *, pknown_floor: float, min_topics: int
) -> list[AlertCandidate]:
    """One AT_RISK_STUDENT alert per student with >= `min_topics` topics below the
    mastery floor in a course (dedup key: student)."""
    by_student: dict[tuple[str, str, str], list[MasteryRow]] = defaultdict(list)
    for row in rows:
        by_student[(row.course_id, row.teacher_id, row.student_id)].append(row)

    candidates: list[AlertCandidate] = []
    for (course_id, teacher_id, student_id), student_rows in by_student.items():
        weak = [r.topic_code for r in student_rows if r.p_known < pknown_floor]
        if len(weak) < min_topics:
            continue
        payload: dict[str, object] = {
            "course_id": course_id,
            "weak_topic_count": len(weak),
            "topics": weak[:5],
            "pknown_floor": pknown_floor,
        }
        candidates.append(
            AlertCandidate(
                teacher_id=teacher_id,
                course_id=course_id,
                alert_type=AlertType.AT_RISK_STUDENT,
                severity=_count_severity(len(weak), min_topics),
                student_id=student_id,
                dedup_ref=student_id,
                payload=payload,
            )
        )
    return candidates


def detect_common_error_in_topic(
    rows: list[MasteryRow],
    sizes: dict[str, int],
    *,
    pknown_floor: float,
    course_ratio: float,
) -> list[AlertCandidate]:
    """COMMON_ERROR_IN_TOPIC when a large fraction of a course is below the mastery
    floor on the same topic (dedup key: topic)."""
    by_topic: dict[tuple[str, str, str, str], list[MasteryRow]] = defaultdict(list)
    for row in rows:
        by_topic[(row.course_id, row.teacher_id, row.topic_id, row.topic_code)].append(row)

    candidates: list[AlertCandidate] = []
    for (course_id, teacher_id, topic_id, topic_code), topic_rows in by_topic.items():
        size = sizes.get(course_id, 0)
        if size <= 0:
            continue
        struggling = sum(1 for r in topic_rows if r.p_known < pknown_floor)
        ratio = struggling / size
        if ratio < course_ratio:
            continue
        payload: dict[str, object] = {
            "course_id": course_id,
            "topic_code": topic_code,
            "struggling_students": struggling,
            "course_size": size,
            "ratio": round(ratio, 3),
        }
        candidates.append(
            AlertCandidate(
                teacher_id=teacher_id,
                course_id=course_id,
                alert_type=AlertType.COMMON_ERROR_IN_TOPIC,
                severity=_severity_from_ratio(ratio),
                topic_id=topic_id,
                dedup_ref=topic_id,
                payload=payload,
            )
        )
    return candidates


def detect_student_drop(rows: list[MasteryRow], *, drop_threshold: float) -> list[AlertCandidate]:
    """STUDENT_DROP when a student's 7-day trend on some topic falls at/below the
    (negative) threshold (dedup key: student)."""
    # Filter out None trends first so the grouped values are plain floats
    # (pyright).
    pairs: list[tuple[float, MasteryRow]] = [
        (row.trend_7d, row) for row in rows if row.trend_7d is not None
    ]
    by_student: dict[tuple[str, str, str], list[tuple[float, MasteryRow]]]
    by_student = defaultdict(list)
    for trend, row in pairs:
        by_student[(row.course_id, row.teacher_id, row.student_id)].append((trend, row))

    candidates: list[AlertCandidate] = []
    for (course_id, teacher_id, student_id), trend_rows in by_student.items():
        dropped = [(t, r) for (t, r) in trend_rows if t <= drop_threshold]
        if not dropped:
            continue
        worst_trend, worst_row = min(dropped, key=lambda tr: tr[0])
        payload: dict[str, object] = {
            "course_id": course_id,
            "worst_topic_code": worst_row.topic_code,
            "worst_trend": round(worst_trend, 3),
            "dropped_topic_count": len(dropped),
        }
        candidates.append(
            AlertCandidate(
                teacher_id=teacher_id,
                course_id=course_id,
                alert_type=AlertType.STUDENT_DROP,
                severity=_drop_severity(worst_trend, drop_threshold),
                student_id=student_id,
                dedup_ref=student_id,
                payload=payload,
            )
        )
    return candidates


def detect_unit_off_track(rows: list[MasteryRow], *, pknown_floor: float) -> list[AlertCandidate]:
    """UNIT_OFF_TRACK when a course's average mastery across a unit's topics is below
    the floor (dedup key: unit; stored in payload since teacher_alerts has no unit FK)."""
    by_unit: dict[tuple[str, str, str, str], list[float]] = defaultdict(list)
    for row in rows:
        by_unit[(row.course_id, row.teacher_id, row.unit_id, row.unit_code)].append(row.p_known)

    candidates: list[AlertCandidate] = []
    for (course_id, teacher_id, unit_id, unit_code), pknowns in by_unit.items():
        if not pknowns:
            continue
        avg = sum(pknowns) / len(pknowns)
        if avg >= pknown_floor:
            continue
        payload: dict[str, object] = {
            "course_id": course_id,
            "unit_id": unit_id,
            "unit_code": unit_code,
            "avg_pknown": round(avg, 3),
            "sample_size": len(pknowns),
        }
        candidates.append(
            AlertCandidate(
                teacher_id=teacher_id,
                course_id=course_id,
                alert_type=AlertType.UNIT_OFF_TRACK,
                severity=_deficit_severity(avg, pknown_floor),
                dedup_ref=unit_id,
                payload=payload,
            )
        )
    return candidates


def detect_guide_grading_complete(
    rows: list[GuideProgressRow], sizes: dict[str, int], *, complete_ratio: float
) -> list[AlertCandidate]:
    """Informational GUIDE_GRADING_COMPLETE when (almost) every enrolled student of a
    published guide has a graded submission (dedup key: guide)."""
    candidates: list[AlertCandidate] = []
    for row in rows:
        size = sizes.get(row.course_id, 0)
        if size <= 0:
            continue
        ratio = row.graded_students / size
        if ratio < complete_ratio:
            continue
        payload: dict[str, object] = {
            "guide_id": row.guide_id,
            "title": row.title,
            "graded_students": row.graded_students,
            "course_size": size,
            "ratio": round(ratio, 3),
        }
        candidates.append(
            AlertCandidate(
                teacher_id=row.teacher_id,
                course_id=row.course_id,
                alert_type=AlertType.GUIDE_GRADING_COMPLETE,
                severity=SEV_LOW,
                dedup_ref=row.guide_id,
                payload=payload,
            )
        )
    return candidates


def detect_guide_common_error(
    rows: list[GuideErrorRow], sizes: dict[str, int], *, course_ratio: float
) -> list[AlertCandidate]:
    """GUIDE_COMMON_ERROR when many students share the same definitive error code on a
    guide question (dedup key: question:error_code).

    `error_code` arrives already resolved from the live source of truth (teacher override
    else `attempt_error_reports -> error_tags.code`), so this stays aligned with the
    catalog as it grows. We only drop the catalog-independent sentinels here, reading the
    single `SPECIAL_ERROR_TYPES` source rather than hardcoding codes (A9.2)."""
    special = set(SPECIAL_ERROR_TYPES)
    candidates: list[AlertCandidate] = []
    for row in rows:
        if row.error_code in special:
            continue
        size = sizes.get(row.course_id, 0)
        if size <= 0:
            continue
        ratio = row.n_students / size
        if ratio < course_ratio:
            continue
        payload: dict[str, object] = {
            "guide_id": row.guide_id,
            "guide_question_id": row.guide_question_id,
            "error_code": row.error_code,
            "n_students": row.n_students,
            "course_size": size,
            "ratio": round(ratio, 3),
        }
        candidates.append(
            AlertCandidate(
                teacher_id=row.teacher_id,
                course_id=row.course_id,
                alert_type=AlertType.GUIDE_COMMON_ERROR,
                severity=_severity_from_ratio(ratio),
                dedup_ref=f"{row.guide_question_id}:{row.error_code}",
                payload=payload,
            )
        )
    return candidates
