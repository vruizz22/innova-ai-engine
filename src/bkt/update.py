from __future__ import annotations


def bkt_update(
    p_known: float,
    p_transit: float,
    p_slip: float,
    p_guess: float,
    obs: bool,
) -> float:
    """Closed-form BKT Bayesian update. Reference implementation (production uses TS port)."""
    if obs:
        denom = p_known * (1.0 - p_slip) + (1.0 - p_known) * p_guess
        evidence = (p_known * (1.0 - p_slip)) / denom if denom > 0.0 else 0.0
    else:
        denom = p_known * p_slip + (1.0 - p_known) * (1.0 - p_guess)
        evidence = (p_known * p_slip) / denom if denom > 0.0 else 0.0
    return evidence + (1.0 - evidence) * p_transit
