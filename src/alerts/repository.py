from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Protocol

from src.alerts.schemas import (
    AlertCandidate,
    GuideErrorRow,
    GuideProgressRow,
    MasteryRow,
)


class DbConn(Protocol):
    """The asyncpg connection bits we use (untyped upstream — adapt at the handler)."""

    async def fetch(self, query: str, *args: object) -> Sequence[Mapping[str, object]]: ...

    async def fetchval(self, query: str, *args: object) -> object: ...


# Mastery is global per (student, topic); we scope it to a course via the lead teacher
# and the course's subject, so a topic is only attributed to the matching course.
_MASTERY = """
SELECT c.id              AS course_id,
       ct.teacher_id     AS teacher_id,
       e.student_id      AS student_id,
       t.id              AS topic_id,
       t.code            AS topic_code,
       u.id              AS unit_id,
       u.code            AS unit_code,
       m.p_known         AS p_known,
       m.trend_7d        AS trend_7d
  FROM enrollments e
  JOIN courses c          ON c.id = e.course_id AND c.archived_at IS NULL
  JOIN course_teachers ct ON ct.course_id = c.id AND ct.role = 'LEAD'
  JOIN student_topic_mastery m ON m.student_id = e.student_id
  JOIN topics t           ON t.id = m.topic_id
  JOIN units u            ON u.id = t.unit_id
  JOIN curricula cur      ON cur.id = u.curriculum_id AND cur.subject_id = c.subject_id
 WHERE e.status = 'ACTIVE'
"""

_COURSE_SIZES = """
SELECT c.id AS course_id, COUNT(*) AS n_students
  FROM enrollments e
  JOIN courses c ON c.id = e.course_id AND c.archived_at IS NULL
 WHERE e.status = 'ACTIVE'
 GROUP BY c.id
"""

_GUIDE_PROGRESS = """
SELECT g.id                    AS guide_id,
       g.title                 AS title,
       g.created_by_teacher_id AS teacher_id,
       g.course_id             AS course_id,
       COUNT(DISTINCT s.student_id)
           FILTER (WHERE s.status = 'GRADED') AS graded_students
  FROM guides g
  LEFT JOIN guide_submissions s ON s.guide_id = g.id
 WHERE g.status = 'PUBLISHED'
   AND g.archived_at IS NULL
 GROUP BY g.id
"""

# The definitive error per graded submission = teacher override, else the latest
# rule-engine/classifier tag landed on the linked attempt (ADR-120). Joining straight
# to error_tags keeps this aligned with the catalog as it grows — no hardcoded codes.
_GUIDE_ERRORS = """
WITH submission_error AS (
    SELECT s.guide_id            AS guide_id,
           s.guide_question_id   AS guide_question_id,
           s.student_id          AS student_id,
           COALESCE(ov.code, rep.code) AS error_code
      FROM guide_submissions s
      LEFT JOIN error_tags ov ON ov.id = s.override_error_tag_id
      LEFT JOIN LATERAL (
          SELECT et.code
            FROM attempt_error_reports aer
            JOIN error_tags et ON et.id = aer.error_tag_id
           WHERE aer.attempt_id = s.attempt_id
           ORDER BY aer.created_at DESC
           LIMIT 1
      ) rep ON TRUE
     WHERE s.status = 'GRADED'
)
SELECT g.id                    AS guide_id,
       se.guide_question_id    AS guide_question_id,
       se.error_code           AS error_code,
       g.created_by_teacher_id AS teacher_id,
       g.course_id             AS course_id,
       COUNT(DISTINCT se.student_id) AS n_students
  FROM submission_error se
  JOIN guides g ON g.id = se.guide_id
 WHERE se.error_code IS NOT NULL
   AND g.status = 'PUBLISHED'
   AND g.archived_at IS NULL
 GROUP BY g.id, se.guide_question_id, se.error_code
"""

# Prisma generates uuids client-side, so the raw insert supplies gen_random_uuid();
# created_at keeps its DB default. Daily dedup on (teacher, type, dedup_ref).
_INSERT_ALERT_IF_ABSENT = """
INSERT INTO teacher_alerts
    (id, teacher_id, course_id, topic_id, student_id, alert_type, severity, payload)
SELECT gen_random_uuid(), $1, $2, $3, $4, $5, $6, $7::jsonb
 WHERE NOT EXISTS (
     SELECT 1
       FROM teacher_alerts
      WHERE teacher_id = $1
        AND alert_type = $5
        AND payload->>'dedup_ref' = $8
        AND created_at >= date_trunc('day', NOW())
 )
RETURNING id
"""


class AsyncpgAlertRepository:
    """`AlertRepositoryPort` against the v7 mastery + v9 guide tables (async)."""

    def __init__(self, conn: DbConn) -> None:
        self._conn = conn

    async def fetch_mastery_rows(self) -> list[MasteryRow]:
        rows = await self._conn.fetch(_MASTERY)
        return [
            MasteryRow(
                course_id=str(row["course_id"]),
                teacher_id=str(row["teacher_id"]),
                student_id=str(row["student_id"]),
                topic_id=str(row["topic_id"]),
                topic_code=str(row["topic_code"]),
                unit_id=str(row["unit_id"]),
                unit_code=str(row["unit_code"]),
                p_known=_f(row["p_known"]),
                trend_7d=_opt_f(row["trend_7d"]),
            )
            for row in rows
        ]

    async def fetch_course_sizes(self) -> dict[str, int]:
        rows = await self._conn.fetch(_COURSE_SIZES)
        return {str(row["course_id"]): _i(row["n_students"]) for row in rows}

    async def fetch_guide_progress_rows(self) -> list[GuideProgressRow]:
        rows = await self._conn.fetch(_GUIDE_PROGRESS)
        return [
            GuideProgressRow(
                guide_id=str(row["guide_id"]),
                title=str(row["title"]),
                teacher_id=str(row["teacher_id"]),
                course_id=str(row["course_id"]),
                graded_students=_i(row["graded_students"]),
            )
            for row in rows
        ]

    async def fetch_guide_error_rows(self) -> list[GuideErrorRow]:
        rows = await self._conn.fetch(_GUIDE_ERRORS)
        return [
            GuideErrorRow(
                guide_id=str(row["guide_id"]),
                guide_question_id=str(row["guide_question_id"]),
                error_code=str(row["error_code"]),
                teacher_id=str(row["teacher_id"]),
                course_id=str(row["course_id"]),
                n_students=_i(row["n_students"]),
            )
            for row in rows
        ]

    async def insert_alert_if_absent(self, candidate: AlertCandidate) -> bool:
        payload: dict[str, object] = dict(candidate.payload)
        payload["dedup_ref"] = candidate.dedup_ref
        inserted = await self._conn.fetchval(
            _INSERT_ALERT_IF_ABSENT,
            candidate.teacher_id,
            candidate.course_id,
            candidate.topic_id,
            candidate.student_id,
            candidate.alert_type,
            candidate.severity,
            json.dumps(payload),
            candidate.dedup_ref,
        )
        return inserted is not None


def _f(value: object) -> float:
    return float(value)  # type: ignore[arg-type]


def _i(value: object) -> int:
    return int(value)  # type: ignore[arg-type]


def _opt_f(value: object) -> float | None:
    return None if value is None else float(value)  # type: ignore[arg-type]
