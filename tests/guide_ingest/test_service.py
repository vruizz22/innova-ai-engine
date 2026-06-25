from __future__ import annotations

import asyncio

import pytest

from src.guide_ingest.schemas import (
    ExtractedQuestion,
    ExtractGuideResult,
    FigureBBox,
    GuideIngestMessage,
    MergedQuestion,
    PdfKind,
    PrecheckResult,
)
from src.guide_ingest.service import ingest_guide
from src.observability.cost import TokenUsage
from src.shared.killswitch import PausedError
from src.shared.settings import Settings


def _settings(**over: object) -> Settings:
    base: dict[str, object] = {
        "anthropic_api_key": "t",
        "gemini_api_key": "t",
        "sqs_solution_gen_url": "https://sqs/solgen",
        "s3_guides_bucket": "bkt",
        "guide_ingest_chunk_pages": 20,
        "guide_ingest_chunk_overlap": 1,
        "guide_min_extraction_quality": 0.5,
    }
    base.update(over)
    return Settings(**base)  # type: ignore[arg-type]


def _msg() -> GuideIngestMessage:
    return GuideIngestMessage(
        guide_id="g1",
        source_pdf_key="guides/uploads/g1.pdf",
        course_grade_level=5,
        trace_id="tr1",
    )


class _FakePrecheck:
    def __init__(self, result: PrecheckResult) -> None:
        self._result = result
        self.calls = 0

    async def precheck(self, pdf_bytes: bytes, *, trace_id: str = "") -> PrecheckResult:
        self.calls += 1
        return self._result


class _RaisingPrecheck:
    async def precheck(self, pdf_bytes: bytes, *, trace_id: str = "") -> PrecheckResult:
        raise PausedError("paused")


class _FakeExtractor:
    def __init__(self, results: list[ExtractGuideResult]) -> None:
        self._results = results
        self.calls = 0

    async def extract_chunk(
        self, pdf_chunk: bytes, *, grade_level: int, page_count: int, trace_id: str = ""
    ) -> tuple[ExtractGuideResult, TokenUsage]:
        result = self._results[self.calls]
        self.calls += 1
        return result, TokenUsage(input_tokens=100, output_tokens=50)


class _FakePdf:
    def __init__(self, pages: int) -> None:
        self._pages = pages
        self.crops = 0

    def page_count(self, pdf_bytes: bytes) -> int:
        return self._pages

    def slice_pages(self, pdf_bytes: bytes, start: int, end: int) -> bytes:
        return b"chunk"

    def crop_figure(self, pdf_bytes: bytes, bbox: FigureBBox) -> bytes:
        self.crops += 1
        return b"png"


class _FakeStore:
    def __init__(self) -> None:
        self.puts: list[tuple[str, str]] = []
        self.gets: list[str] = []

    def get(self, key: str) -> bytes:
        self.gets.append(key)
        return b"pdf"

    def put(self, key: str, body: bytes, *, content_type: str) -> None:
        self.puts.append((key, content_type))


class _FakePublisher:
    def __init__(self) -> None:
        self.published: list[tuple[str, str, str]] = []

    def publish(self, queue_url: str, body: str, *, trace_id: str = "") -> None:
        self.published.append((queue_url, body, trace_id))


class _FakeRepo:
    def __init__(self) -> None:
        self.extracting: list[str] = []
        self.failed: list[tuple[str, str]] = []
        self.completed: list[tuple[str, list[MergedQuestion]]] = []

    async def mark_extracting(self, guide_id: str) -> None:
        self.extracting.append(guide_id)

    async def mark_failed(
        self, guide_id: str, *, source_kind: str, pages: int | None, reason: str
    ) -> None:
        self.failed.append((guide_id, reason))

    async def complete(
        self,
        guide_id: str,
        questions: list[MergedQuestion],
        *,
        source_kind: str,
        pages: int | None,
        latex_key: str,
        extraction_confidence: float,
        extraction_model: str,
    ) -> None:
        self.completed.append((guide_id, questions))

    async def save_cost_event(self, **kwargs: object) -> None:
        pass


def test_happy_path_extracts_persists_and_enqueues() -> None:
    precheck = _FakePrecheck(PrecheckResult(kind=PdfKind.DIGITAL, quality=0.9))
    extractor = _FakeExtractor(
        [
            ExtractGuideResult(
                questions=[
                    ExtractedQuestion(
                        label="1",
                        statement_latex="$1+1$",
                        statement_text="one plus one",
                        figure_bboxes=[FigureBBox(page=0, x0=0.1, y0=0.1, x1=0.2, y1=0.2)],
                    ),
                    ExtractedQuestion(
                        label="2",
                        statement_latex="$2+2$",
                        statement_text="two plus two",
                    ),
                ]
            )
        ]
    )
    pdf = _FakePdf(3)
    store = _FakeStore()
    publisher = _FakePublisher()
    repo = _FakeRepo()

    outcome = asyncio.run(
        ingest_guide(
            _msg(),
            precheck=precheck,
            extractor=extractor,
            pdf=pdf,
            store=store,
            publisher=publisher,
            repo=repo,
            settings=_settings(),
        )
    )

    assert outcome.status == "GENERATING_SOLUTIONS"
    assert outcome.question_count == 2
    assert repo.extracting == ["g1"]
    assert len(repo.completed) == 1
    _, questions = repo.completed[0]
    assert [q.sequence for q in questions] == [1, 2]
    assert questions[0].figure_keys == ["guides/g1/figures/q1_0.png"]
    assert pdf.crops == 1

    put_keys = [key for key, _ in store.puts]
    assert "guides/g1/figures/q1_0.png" in put_keys
    assert "guides/g1/guide.tex" in put_keys

    assert len(publisher.published) == 1
    queue_url, body, trace = publisher.published[0]
    assert queue_url == "https://sqs/solgen"
    assert '"guide_id":"g1"' in body
    assert trace == "tr1"


def test_precheck_failure_terminates_before_extraction() -> None:
    precheck = _FakePrecheck(
        PrecheckResult(kind=PdfKind.SCANNED, quality=0.2, notes="rescan pages 3-5")
    )
    extractor = _FakeExtractor([])
    pdf = _FakePdf(3)
    store = _FakeStore()
    publisher = _FakePublisher()
    repo = _FakeRepo()

    outcome = asyncio.run(
        ingest_guide(
            _msg(),
            precheck=precheck,
            extractor=extractor,
            pdf=pdf,
            store=store,
            publisher=publisher,
            repo=repo,
            settings=_settings(),
        )
    )

    assert outcome.status == "EXTRACTION_FAILED"
    assert outcome.failure_reason == "rescan pages 3-5"
    assert extractor.calls == 0  # no Sonnet tokens burned
    assert repo.completed == []
    assert repo.failed and repo.failed[0][0] == "g1"
    assert publisher.published == []


def test_killswitch_propagates_and_publishes_nothing() -> None:
    repo = _FakeRepo()
    publisher = _FakePublisher()

    with pytest.raises(PausedError):
        asyncio.run(
            ingest_guide(
                _msg(),
                precheck=_RaisingPrecheck(),
                extractor=_FakeExtractor([]),
                pdf=_FakePdf(1),
                store=_FakeStore(),
                publisher=publisher,
                repo=repo,
                settings=_settings(),
            )
        )

    assert publisher.published == []
    assert repo.completed == []
