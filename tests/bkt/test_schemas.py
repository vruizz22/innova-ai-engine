from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.bkt.schemas import AttemptObservation, BktParams


def test_valid_params() -> None:
    p = BktParams(p_l0=0.3, p_transit=0.1, p_slip=0.1, p_guess=0.2)
    assert p.p_l0 == 0.3


def test_invalid_slip_plus_guess_raises() -> None:
    with pytest.raises(ValidationError):
        BktParams(p_l0=0.3, p_transit=0.1, p_slip=0.6, p_guess=0.5)


def test_p_l0_out_of_range() -> None:
    with pytest.raises(ValidationError):
        BktParams(p_l0=1.5, p_transit=0.1, p_slip=0.1, p_guess=0.2)


def test_attempt_observation_valid() -> None:
    a = AttemptObservation(student_id="s1", skill_id="sk1", is_correct=True, timestamp=1000.0)
    assert a.student_id == "s1"
    assert a.is_correct is True
