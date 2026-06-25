from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class AlertType(StrEnum):
    """TeacherAlert.alert_type values written by the hourly cron (CLAUDE.md §8 + A9.2)."""

    # v7 (mastery-based)
    AT_RISK_STUDENT = "AT_RISK_STUDENT"
    COMMON_ERROR_IN_TOPIC = "COMMON_ERROR_IN_TOPIC"
    STUDENT_DROP = "STUDENT_DROP"
    UNIT_OFF_TRACK = "UNIT_OFF_TRACK"
    # v9 (guides-based)
    GUIDE_GRADING_COMPLETE = "GUIDE_GRADING_COMPLETE"
    GUIDE_COMMON_ERROR = "GUIDE_COMMON_ERROR"


class MasteryRow(BaseModel):
    """One (active enrollment, topic) mastery datapoint for the lead teacher's course."""

    course_id: str
    teacher_id: str
    student_id: str
    topic_id: str
    topic_code: str
    unit_id: str
    unit_code: str
    p_known: float
    trend_7d: float | None = None


class GuideProgressRow(BaseModel):
    """Grading progress of one published guide."""

    guide_id: str
    title: str
    teacher_id: str
    course_id: str
    graded_students: int


class GuideErrorRow(BaseModel):
    """Count of students sharing one definitive error code on a guide question.

    `error_code` is the live `error_tags.code` (teacher override else the rule-engine /
    classifier tag landed after reprocess) — always aligned with the catalog (A9.2)."""

    guide_id: str
    guide_question_id: str
    error_code: str
    teacher_id: str
    course_id: str
    n_students: int


class AlertCandidate(BaseModel):
    """A detected alert before dedup. `dedup_ref` is the entity identity used for the
    daily `(teacher, type, entity, day)` dedup."""

    teacher_id: str
    course_id: str
    alert_type: str
    severity: str = "MED"
    topic_id: str | None = None
    student_id: str | None = None
    dedup_ref: str
    # Heterogeneous per-type JSON written to teacher_alerts.payload (a Json column);
    # values are str/int/float/list, all `object` subtypes (justifies dict[str, object]).
    payload: dict[str, object] = Field(default_factory=dict)


class AlertRunOutcome(BaseModel):
    """Cron-run summary for the handler response."""

    candidates: int = 0
    inserted: int = 0
    by_type: dict[str, int] = Field(default_factory=dict)
