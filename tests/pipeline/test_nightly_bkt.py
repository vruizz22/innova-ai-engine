from __future__ import annotations

import random
from unittest.mock import AsyncMock, MagicMock, patch

from src.bkt.schemas import BktParams
from src.bkt.update import bkt_update as _bkt_update


def test_nightly_bkt_skips_skill_with_low_data() -> None:
    event: dict[str, object] = {"source": "aws.events"}

    mock_pool = AsyncMock()
    mock_pool.fetch.side_effect = [
        [{"id": "skill-1"}],
        [],
    ]
    mock_pool.execute = AsyncMock()

    with patch("src.pipeline.nightly_bkt.get_pool", return_value=mock_pool):
        from src.pipeline.nightly_bkt import handler

        result = handler(event, MagicMock())
        assert result["count"] == 0


def test_nightly_bkt_calibrates_skill_with_sufficient_data() -> None:
    event: dict[str, object] = {}
    true = BktParams(p_l0=0.3, p_transit=0.1, p_slip=0.1, p_guess=0.2)

    rng = random.Random(0)
    p_known = true.p_l0
    rows = []
    for i in range(60):
        p_c = p_known * (1 - true.p_slip) + (1 - p_known) * true.p_guess
        is_correct = rng.random() < p_c
        rows.append(
            {"student_id": "s1", "is_correct": is_correct, "ts": float(i)})
        p_known = _bkt_update(
            p_known,
            true.p_transit,
            true.p_slip,
            true.p_guess,
            is_correct)

    mock_pool = AsyncMock()
    mock_pool.fetch.side_effect = [[{"id": "skill-1"}], rows]
    mock_pool.execute = AsyncMock()

    with patch("src.pipeline.nightly_bkt.get_pool", return_value=mock_pool):
        from src.pipeline.nightly_bkt import handler

        result = handler(event, MagicMock())
        assert result["count"] == 1
