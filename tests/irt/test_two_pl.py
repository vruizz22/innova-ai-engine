from __future__ import annotations

from src.irt.two_pl import MIN_ATTEMPTS, fit_2pl
from tests.conftest import generate_synthetic_2pl_attempts


def test_irt_2pl_recovery() -> None:
    """Fit 2PL on synthetic data. Recovered a, b within +-0.2 of true values."""
    true_a, true_b = 1.5, 0.5
    attempts = generate_synthetic_2pl_attempts(a=true_a, b=true_b, n=1000, seed=42)
    params = fit_2pl(item_id="test-item", attempts=attempts)

    assert abs(params.a - true_a) < 0.2, f"a: expected {true_a}, got {params.a}"
    assert abs(params.b - true_b) < 0.2, f"b: expected {true_b}, got {params.b}"


def test_irt_skip_items_below_threshold() -> None:
    """Items with < MIN_ATTEMPTS must return default params (a=1.0, b=0.0)."""
    attempts = generate_synthetic_2pl_attempts(a=1.5, b=0.5, n=30, seed=42)
    params = fit_2pl(item_id="sparse-item", attempts=attempts)
    assert params.a == 1.0
    assert params.b == 0.0
    assert params.calibrated is False


def test_irt_calibrated_flag_set_when_enough_data() -> None:
    attempts = generate_synthetic_2pl_attempts(a=1.0, b=0.0, n=MIN_ATTEMPTS, seed=42)
    params = fit_2pl(item_id="item-min", attempts=attempts)
    assert params.calibrated is True
