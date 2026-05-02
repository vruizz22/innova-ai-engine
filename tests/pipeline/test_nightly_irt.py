from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np


def test_nightly_irt_no_items_returns_zero() -> None:
    event: dict[str, object] = {}
    mock_pool = AsyncMock()
    mock_pool.fetch.side_effect = [[]]

    with patch("src.pipeline.nightly_irt.get_pool", return_value=mock_pool):
        from src.pipeline.nightly_irt import handler

        result = handler(event, MagicMock())
        assert result["calibrated_items"] == 0


def test_nightly_irt_calibrates_one_item() -> None:
    event: dict[str, object] = {}
    rng = np.random.default_rng(42)
    thetas = rng.normal(0, 1, 100)
    rows = [{"theta": float(t), "is_correct": bool(
        rng.random() < 0.5)} for t in thetas]

    mock_pool = AsyncMock()
    mock_pool.fetch.side_effect = [[{"id": "item-1"}], rows]
    mock_pool.execute = AsyncMock()

    with patch("src.pipeline.nightly_irt.get_pool", return_value=mock_pool):
        from src.pipeline.nightly_irt import handler

        result = handler(event, MagicMock())
        assert result["calibrated_items"] == 1
