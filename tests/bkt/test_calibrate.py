from __future__ import annotations

from src.bkt.calibrate import calibrate_skill
from src.bkt.schemas import BktParams
from tests.conftest import generate_synthetic_bkt_sequence


def test_bkt_calibration_recovers_params() -> None:
    """
    Grid search recovers measurement params (slip, guess) within +-0.15.
    p_l0 and p_transit are confounded (known BKT identifiability issue), so
    only the measurement params are checked for exact recovery.
    """
    true_params = BktParams(p_l0=0.3, p_transit=0.15, p_slip=0.1, p_guess=0.2)
    attempts = generate_synthetic_bkt_sequence(true_params, n=1000, seed=42)
    recovered = calibrate_skill(attempts)

    # Measurement params are identifiable
    assert abs(recovered.p_slip - true_params.p_slip) <= 0.15
    assert abs(recovered.p_guess - true_params.p_guess) <= 0.15
    # Log-likelihood must be finite and negative
    assert recovered.log_likelihood is not None
    assert recovered.log_likelihood < 0


def test_calibrate_returns_bkt_params_type() -> None:
    true_params = BktParams(p_l0=0.3, p_transit=0.1, p_slip=0.1, p_guess=0.2)
    attempts = generate_synthetic_bkt_sequence(true_params, n=200, seed=1)
    result = calibrate_skill(attempts)
    assert isinstance(result, BktParams)
    assert result.log_likelihood is not None
    assert result.log_likelihood < 0
