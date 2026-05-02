from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.irt.schemas import IrtItemParams


def test_valid_irt_params() -> None:
    p = IrtItemParams(item_id="x", a=1.5, b=0.3)
    assert p.item_id == "x"
    assert p.calibrated is False


def test_invalid_a_too_high() -> None:
    with pytest.raises(ValidationError):
        IrtItemParams(item_id="x", a=5.0, b=0.0)


def test_invalid_b_out_of_range() -> None:
    with pytest.raises(ValidationError):
        IrtItemParams(item_id="x", a=1.0, b=5.0)
