from __future__ import annotations

import asyncio

from src.alerts.schemas import (
    AlertCandidate,
    AlertType,
    GuideErrorRow,
    GuideProgressRow,
    MasteryRow,
)
from src.alerts.service import run_hourly_alerts
from src.shared.settings import Settings


def _settings(**over: object) -> Settings:
    base: dict[str, object] = {"anthropic_api_key": "t", "gemini_api_key": "t"}
    base.update(over)
    return Settings(**base)  # type: ignore[arg-type]


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


class _FakeRepo:
    def __init__(
        self,
        *,
        mastery: list[MasteryRow] | None = None,
        sizes: dict[str, int] | None = None,
        progress: list[GuideProgressRow] | None = None,
        errors: list[GuideErrorRow] | None = None,
        dup_refs: set[str] | None = None,
    ) -> None:
        self._mastery = mastery or []
        self._sizes = sizes or {}
        self._progress = progress or []
        self._errors = errors or []
        self._dup_refs = dup_refs or set()
        self.inserted: list[AlertCandidate] = []

    async def fetch_mastery_rows(self) -> list[MasteryRow]:
        return self._mastery

    async def fetch_course_sizes(self) -> dict[str, int]:
        return self._sizes

    async def fetch_guide_progress_rows(self) -> list[GuideProgressRow]:
        return self._progress

    async def fetch_guide_error_rows(self) -> list[GuideErrorRow]:
        return self._errors

    async def insert_alert_if_absent(self, candidate: AlertCandidate) -> bool:
        if candidate.dedup_ref in self._dup_refs:
            return False
        self.inserted.append(candidate)
        return True


def _three_weak_topics() -> list[MasteryRow]:
    return [
        _m(topic_id="t1", topic_code="A", p_known=0.1),
        _m(topic_id="t2", topic_code="B", p_known=0.2),
        _m(topic_id="t3", topic_code="C", p_known=0.3),
    ]


def test_run_collects_mastery_alerts() -> None:
    # Large course size keeps per-topic ratios below the common-error threshold, so only
    # the at-risk student + the off-track unit fire.
    repo = _FakeRepo(mastery=_three_weak_topics(), sizes={"c1": 30})
    outcome = asyncio.run(run_hourly_alerts(repo=repo, settings=_settings()))
    assert outcome.candidates == 2
    assert outcome.inserted == 2
    assert outcome.by_type[AlertType.AT_RISK_STUDENT] == 1
    assert outcome.by_type[AlertType.UNIT_OFF_TRACK] == 1


def test_dedup_skips_existing_alert() -> None:
    repo = _FakeRepo(mastery=_three_weak_topics(), sizes={"c1": 30}, dup_refs={"s1"})
    outcome = asyncio.run(run_hourly_alerts(repo=repo, settings=_settings()))
    assert outcome.candidates == 2
    assert outcome.inserted == 1  # AT_RISK_STUDENT (dedup_ref s1) already present
    assert all(c.dedup_ref != "s1" for c in repo.inserted)


def test_run_collects_guide_alerts() -> None:
    progress = [
        GuideProgressRow(
            guide_id="g1",
            title="G",
            teacher_id="t1",
            course_id="c1",
            graded_students=10,
        )
    ]
    errors = [
        GuideErrorRow(
            guide_id="g1",
            guide_question_id="q1",
            error_code="ARITH.CARRY",
            teacher_id="t1",
            course_id="c1",
            n_students=5,
        )
    ]
    repo = _FakeRepo(sizes={"c1": 10}, progress=progress, errors=errors)
    outcome = asyncio.run(run_hourly_alerts(repo=repo, settings=_settings()))
    assert outcome.inserted == 2
    assert outcome.by_type[AlertType.GUIDE_GRADING_COMPLETE] == 1
    assert outcome.by_type[AlertType.GUIDE_COMMON_ERROR] == 1


def test_run_with_no_data_inserts_nothing() -> None:
    repo = _FakeRepo()
    outcome = asyncio.run(run_hourly_alerts(repo=repo, settings=_settings()))
    assert outcome.candidates == 0
    assert outcome.inserted == 0
    assert outcome.by_type == {}
