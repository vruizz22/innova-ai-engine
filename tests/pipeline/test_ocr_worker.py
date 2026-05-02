from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from src.ocr.schemas import OcrProvider, OcrResult


def _s3_event(bucket: str = "innova-uploads",
              key: str = "test.jpg") -> dict[str, object]:
    return {
        "Records": [
            {
                "s3": {
                    "bucket": {"name": bucket},
                    "object": {"key": key},
                }
            }
        ]
    }


def test_ocr_worker_processes_image() -> None:
    event = _s3_event()
    mock_result = OcrResult(
        latex_steps=["x=3"],
        overall_confidence=0.9,
        provider=OcrProvider.GEMINI)

    with patch("boto3.client") as mock_boto:
        mock_s3 = MagicMock()
        mock_boto.return_value = mock_s3
        mock_body = MagicMock()
        mock_body.read.return_value = b"fake_bytes"
        mock_s3.get_object.return_value = {"Body": mock_body}

        with patch(
            "src.pipeline.ocr_worker.strip_exif_and_validate",
            return_value=b"fake_bytes",
        ):
            with patch("src.pipeline.ocr_worker.OcrOrchestrator") as mock_orch_cls:
                mock_orch = MagicMock()
                mock_orch.extract = AsyncMock(return_value=mock_result)
                mock_orch_cls.return_value = mock_orch

                from src.pipeline.ocr_worker import handler

                result = handler(event, MagicMock())
                assert result["processed"] == 1
