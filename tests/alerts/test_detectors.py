from __future__ import annotations

from src.alerts.detectors import (
    detect_at_risk_students,
    detect_common_error_in_topic,
    detect_guide_common_error,
    detect_guide_grading_complete,
    detect_student_drop,
    detect_unit_off_track,
)
from src.alerts.schemas import AlertType, GuideErrorRow, GuideProgressRow, MasteryRow


def _m(**over: object) -> MasteryRow:
    base: dict[str, object] = {
        "course_id": "c1",
        "teacher_id": "t1",
        "student_id": "s1",
        "topic_id": "tp1",
        "topic_code": "ARITH.ADD",
        "unit_id": "u1",
        "unit_code": "U1",
        "p_known": 0.9,
        "trend_7d": None,
    }
    base.update(over)
    return MasteryRow(**base)  # type: ignore[arg-type]


def test_at_risk_fires_when_enough_weak_topics() -> None:
    rows = [
        _m(student_id="s1", topic_id="t1", topic_code="A", p_known=0.1),
        _m(student_id="s1", topic_id="t2", topic_code="B", p_known=0.2),
        _m(student_id="s1", topic_id="t3", topic_code="C", p_known=0.3),
        _m(student_id="s1", topic_id="t4", topic_code="D", p_known=0.9),
        _m(student_id="s2", topic_id="t1", topic_code="A", p_known=0.1),
        _m(student_id="s2", topic_id="t2", topic_code="B", p_known=0.2),
    ]
    out = detect_at_risk_students(rows, pknown_floor=0.4, min_topics=3)
    assert len(out) == 1  # s2 has only 2 weak topics
    candidate = out[0]
    assert candidate.alert_type == AlertType.AT_RISK_STUDENT
    assert candidate.student_id == "s1"
    assert candidate.dedup_ref == "s1"
    assert candidate.severity == "MED"
    assert candidate.payload["weak_topic_count"] == 3


def test_common_error_in_topic_uses_course_ratio() -> None:
    rows = [
        _m(student_id="s1", p_known=0.1),
        _m(student_id="s2", p_known=0.2),
        _m(student_id="s3", p_known=0.9),
    ]
    out = detect_common_error_in_topic(rows, {"c1": 4}, pknown_floor=0.4, course_ratio=0.5)
    assert len(out) == 1
    candidate = out[0]
    assert candidate.alert_type == AlertType.COMMON_ERROR_IN_TOPIC
    assert candidate.topic_id == "tp1"
    assert candidate.dedup_ref == "tp1"
    assert candidate.payload["struggling_students"] == 2
    assert candidate.payload["course_size"] == 4


def test_common_error_skips_when_course_size_unknown() -> None:
    rows = [_m(p_known=0.1)]
    out = detect_common_error_in_topic(rows, {}, pknown_floor=0.4, course_ratio=0.5)
    assert out == []


def test_student_drop_picks_worst_trend_and_ignores_none() -> None:
    rows = [
        _m(student_id="s1", topic_id="t1", topic_code="A", trend_7d=-0.2),
        _m(student_id="s1", topic_id="t2", topic_code="B", trend_7d=-0.05),
        _m(student_id="s1", topic_id="t3", topic_code="C", trend_7d=None),
    ]
    out = detect_student_drop(rows, drop_threshold=-0.15)
    assert len(out) == 1
    candidate = out[0]
    assert candidate.alert_type == AlertType.STUDENT_DROP
    assert candidate.dedup_ref == "s1"
    assert candidate.payload["worst_topic_code"] == "A"
    assert candidate.payload["dropped_topic_count"] == 1


def test_student_drop_quiet_when_above_threshold() -> None:
    rows = [_m(student_id="s1", trend_7d=-0.1)]
    assert detect_student_drop(rows, drop_threshold=-0.15) == []


def test_unit_off_track_averages_topic_mastery() -> None:
    rows = [
        _m(unit_id="u1", unit_code="U1", topic_id="t1", p_known=0.2),
        _m(unit_id="u1", unit_code="U1", topic_id="t2", p_known=0.3),
        _m(unit_id="u2", unit_code="U2", topic_id="t3", p_known=0.9),
    ]
    out = detect_unit_off_track(rows, pknown_floor=0.4)
    assert len(out) == 1
    candidate = out[0]
    assert candidate.alert_type == AlertType.UNIT_OFF_TRACK
    assert candidate.dedup_ref == "u1"
    assert candidate.topic_id is None
    assert candidate.payload["unit_code"] == "U1"
    assert candidate.payload["sample_size"] == 2


def test_guide_grading_complete_uses_completion_ratio() -> None:
    rows = [
        GuideProgressRow(
            guide_id="g1",
            title="G",
            teacher_id="t1",
            course_id="c1",
            graded_students=9,
        ),
        GuideProgressRow(
            guide_id="g2",
            title="H",
            teacher_id="t1",
            course_id="c1",
            graded_students=4,
        ),
    ]
    out = detect_guide_grading_complete(rows, {"c1": 10}, complete_ratio=0.9)
    assert len(out) == 1  # g2 only 40% graded
    candidate = out[0]
    assert candidate.alert_type == AlertType.GUIDE_GRADING_COMPLETE
    assert candidate.dedup_ref == "g1"
    assert candidate.severity == "LOW"


def test_guide_common_error_filters_special_and_uses_ratio() -> None:
    rows = [
        GuideErrorRow(
            guide_id="g1",
            guide_question_id="q1",
            error_code="ARITH.CARRY",
            teacher_id="t1",
            course_id="c1",
            n_students=4,
        ),
        # SPECIAL_ERROR_TYPES sentinel — must be dropped even at high frequency.
        GuideErrorRow(
            guide_id="g1",
            guide_question_id="q2",
            error_code="UNCLASSIFIED",
            teacher_id="t1",
            course_id="c1",
            n_students=8,
        ),
        GuideErrorRow(
            guide_id="g1",
            guide_question_id="q3",
            error_code="ARITH.SIGN",
            teacher_id="t1",
            course_id="c1",
            n_students=2,
        ),
    ]
    out = detect_guide_common_error(rows, {"c1": 10}, course_ratio=0.3)
    assert len(out) == 1  # q2 filtered (sentinel), q3 below ratio
    candidate = out[0]
    assert candidate.alert_type == AlertType.GUIDE_COMMON_ERROR
    assert candidate.payload["error_code"] == "ARITH.CARRY"
    assert candidate.dedup_ref == "q1:ARITH.CARRY"
