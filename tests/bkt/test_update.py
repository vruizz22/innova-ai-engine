from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from src.bkt.update import bkt_update


@given(
    p_known=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
    p_transit=st.floats(min_value=0.0, max_value=0.5, allow_nan=False),
    p_slip=st.floats(min_value=0.0, max_value=0.4, allow_nan=False),
    p_guess=st.floats(min_value=0.0, max_value=0.4, allow_nan=False),
    obs=st.booleans(),
)
@settings(max_examples=500)
def test_bkt_output_bounds(
    p_known: float, p_transit: float, p_slip: float, p_guess: float, obs: bool
) -> None:
    """p_known output must always be in [0, 1]."""
    result = bkt_update(p_known, p_transit, p_slip, p_guess, obs)
    assert 0.0 <= result <= 1.0


@given(
    p_known=st.floats(min_value=0.01, max_value=0.99),
    n_correct=st.integers(min_value=1, max_value=50),
)
def test_monotonic_increase_on_correct(p_known: float, n_correct: int) -> None:
    """Repeated correct answers must not decrease p_known (with p_slip=0)."""
    state = p_known
    for _ in range(n_correct):
        new_state = bkt_update(
            state,
            p_transit=0.1,
            p_slip=0.0,
            p_guess=0.2,
            obs=True)
        assert new_state >= state - 1e-9
        state = new_state


def test_idempotent_at_mastery() -> None:
    """Near-certain mastery should stay near-certain after correct answer."""
    result = bkt_update(
        p_known=0.999,
        p_transit=0.1,
        p_slip=0.05,
        p_guess=0.2,
        obs=True)
    assert result > 0.99


def test_correct_increases_pknown() -> None:
    result = bkt_update(
        p_known=0.5,
        p_transit=0.1,
        p_slip=0.1,
        p_guess=0.2,
        obs=True)
    assert result > 0.5


def test_incorrect_decreases_pknown() -> None:
    result = bkt_update(
        p_known=0.5,
        p_transit=0.0,
        p_slip=0.1,
        p_guess=0.2,
        obs=False)
    assert result < 0.5
