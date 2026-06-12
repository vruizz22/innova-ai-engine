from __future__ import annotations

import asyncio
import json

import pytest

from src.shared.killswitch import PausedError
from src.shared.settings import Settings
from src.submission_grader.schemas import (
    AlignMatch,
    Alignment,
    AlignVerdict,
    GradeSubmissionMessage,
    Provisional,
    SubmissionContext,
    TranscribeAndAlign,
    Transcription,
    TranscriptionStep,
)
from src.submission_grader.service import grade_submission


def _settings(**over: object) -> Settings:
    base: dict[str, object] = {
        "anthropic_api_key": "t",
        "gemini_api_key": "t",
        "sqs_attempt_reprocess_url": "https://sqs/reprocess",
        "s3_submissions_bucket": "subs",
        "grading_min_transcription_confidence": 0.5,
    }
    base.update(over)
    return Settings(**base)  # type: ignore[arg-type]


def _msg() -> GradeSubmissionMessage:
    return GradeSubmissionMessage(guide_submission_id="sub-1", trace_id="tr1")


def _ctx(photo_keys: list[str] | None = None) -> SubmissionContext:
    return SubmissionContext(
        guide_submission_id="sub-1",
        guide_id="g1",
        guide_question_id="q1",
        student_id="stu-1",
        attempt_number=1,
        photo_keys=["uploads/a.jpg"] if photo_keys is None else photo_keys,
        grade_level=5,
        question_label="3.a",
        solution_version=2,
        solution_steps_json='{"steps": []}',
        solution_final_answer="4",
        domain_id="domain-1",
        domain_catalog_text="ARITH: carry",
    )


def _ta(
        confidence: float,
        *,
        verdict: AlignVerdict = AlignVerdict.OK) -> TranscribeAndAlign:
    return TranscribeAndAlign(
        transcription=Transcription(
            steps=[
                TranscriptionStep(
                    idx=0,
                    latex="2+2")],
            final_answer="4",
            confidence=confidence,
        ),
        alignment=Alignment(
            path="MAIN",
            matches=[
                AlignMatch(
                    student_step_idx=0,
                    solution_checkpoint_idx=0,
                    verdict=verdict)],
        ),
        provisional=Provisional(
            is_correct=verdict is AlignVerdict.OK,
            score_0_1=1.0),
    )


class _FakeGrader:
    def __init__(self, results: list[TranscribeAndAlign]) -> None:
        self._results = results
        self.calls = 0

    async def grade(
            self,
            images: list[bytes],
            **kwargs: object) -> TranscribeAndAlign:
        result = self._results[min(self.calls, len(self._results) - 1)]
        self.calls += 1
        return result


class _RaisingGrader:
    async def grade(
            self,
            images: list[bytes],
            **kwargs: object) -> TranscribeAndAlign:
        raise PausedError("paused")


class _FakeStore:
    def __init__(self) -> None:
        self.gets: list[str] = []

    def get(self, key: str) -> bytes:
        self.gets.append(key)
        return b"jpeg"

    def put(self, key: str, body: bytes, *, content_type: str) -> None:  # pragma: no cover
        raise AssertionError("grader never writes to S3")


class _FakePublisher:
    def __init__(self) -> None:
        self.published: list[tuple[str, str, str]] = []

    def publish(
            self,
            queue_url: str,
            body: str,
            *,
            trace_id: str = "") -> None:
        self.published.append((queue_url, body, trace_id))


class _FakeRepo:
    def __init__(self, ctx: SubmissionContext | None) -> None:
        self._ctx = ctx
        self.saved: list[dict[str, object]] = []

    async def load_submission_context(
        self, guide_submission_id: str
    ) -> SubmissionContext | None:
        return self._ctx

    async def save_grading(
            self,
            guide_submission_id: str,
            **kwargs: object) -> None:
        self.saved.append(
            {"guide_submission_id": guide_submission_id, **kwargs})


def test_legible_persists_grading_and_publishes_reprocess() -> None:
    grader = _FakeGrader([_ta(0.9)])
    store = _FakeStore()
    publisher = _FakePublisher()
    repo = _FakeRepo(_ctx())

    outcome = asyncio.run(
        grade_submission(
            _msg(),
            grader=grader,
            store=store,
            publisher=publisher,
            repo=repo,
            settings=_settings(),
        )
    )

    assert grader.calls == 1
    assert store.gets == ["uploads/a.jpg"]
    assert outcome.status == "GRADING"
    assert outcome.published is True
    saved = repo.saved[0]
    assert saved["status"] == "GRADING"
    assert saved["solution_version"] == 2
    assert saved["failure_reason"] is None

    assert len(publisher.published) == 1
    queue_url, body, trace = publisher.published[0]
    assert queue_url == "https://sqs/reprocess"
    assert trace == "tr1"
    payload = json.loads(body)
    assert payload["attempt_id"] is None
    assert payload["guide_question_id"] == "q1"
    assert payload["latex_steps"] == ["2+2"]
    assert payload["alignment_summary"]["path"] == "MAIN"


def test_low_confidence_retries_once_then_succeeds() -> None:
    grader = _FakeGrader([_ta(0.3), _ta(0.8)])  # first low, retry good
    publisher = _FakePublisher()
    repo = _FakeRepo(_ctx())

    outcome = asyncio.run(
        grade_submission(
            _msg(),
            grader=grader,
            store=_FakeStore(),
            publisher=publisher,
            repo=repo,
            settings=_settings(),
        )
    )

    assert grader.calls == 2
    assert outcome.status == "GRADING"
    assert len(publisher.published) == 1


def test_illegible_after_retry_closes_graded_without_reprocess() -> None:
    grader = _FakeGrader([_ta(0.2), _ta(0.2)])
    publisher = _FakePublisher()
    repo = _FakeRepo(_ctx())

    outcome = asyncio.run(
        grade_submission(
            _msg(),
            grader=grader,
            store=_FakeStore(),
            publisher=publisher,
            repo=repo,
            settings=_settings(),
        )
    )

    assert grader.calls == 2
    assert outcome.status == "GRADED"
    assert outcome.illegible is True
    assert publisher.published == []
    saved = repo.saved[0]
    assert saved["status"] == "GRADED"
    assert saved["failure_reason"] == "ILLEGIBLE"
    assert saved["alignment_json"] is None


def test_no_photos_marks_failed() -> None:
    repo = _FakeRepo(_ctx(photo_keys=[]))
    publisher = _FakePublisher()

    outcome = asyncio.run(
        grade_submission(
            _msg(),
            grader=_FakeGrader([_ta(0.9)]),
            store=_FakeStore(),
            publisher=publisher,
            repo=repo,
            settings=_settings(),
        )
    )

    assert outcome.status == "FAILED"
    assert repo.saved[0]["failure_reason"] == "no photos"
    assert publisher.published == []


def test_missing_context_returns_failed_without_write() -> None:
    repo = _FakeRepo(None)
    outcome = asyncio.run(
        grade_submission(
            _msg(),
            grader=_FakeGrader([_ta(0.9)]),
            store=_FakeStore(),
            publisher=_FakePublisher(),
            repo=repo,
            settings=_settings(),
        )
    )
    assert outcome.status == "FAILED"
    assert repo.saved == []


def test_killswitch_propagates_and_writes_nothing() -> None:
    repo = _FakeRepo(_ctx())
    publisher = _FakePublisher()

    with pytest.raises(PausedError):
        asyncio.run(
            grade_submission(
                _msg(),
                grader=_RaisingGrader(),
                store=_FakeStore(),
                publisher=publisher,
                repo=repo,
                settings=_settings(),
            )
        )

    assert repo.saved == []
    assert publisher.published == []
