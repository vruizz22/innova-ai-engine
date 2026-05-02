from __future__ import annotations

from typing import cast

import numpy as np
from scipy.optimize import minimize  # type: ignore[import-untyped]

from src.irt.schemas import IrtItemParams

MIN_ATTEMPTS = 50


def fit_2pl(
    item_id: str,
    attempts: list[tuple[float, bool]],
) -> IrtItemParams:
    """
    Fit 2PL IRT model via L-BFGS-B maximum likelihood.
    attempts: list of (theta_student, is_correct).
    Returns default params (a=1.0, b=0.0) if < MIN_ATTEMPTS.
    """
    if len(attempts) < MIN_ATTEMPTS:
        return IrtItemParams(item_id=item_id, a=1.0, b=0.0, calibrated=False)

    thetas = np.array([t for t, _ in attempts], dtype=float)
    correct = np.array([1.0 if c else 0.0 for _, c in attempts], dtype=float)

    def neg_log_likelihood(params: np.ndarray) -> float:
        a, b = params
        p = 1.0 / (1.0 + np.exp(-a * (thetas - b)))
        p = np.clip(p, 1e-9, 1.0 - 1e-9)
        return -float(np.sum(correct * np.log(p) +
                      (1.0 - correct) * np.log(1.0 - p)))

    result = minimize(  # type: ignore[misc]
        neg_log_likelihood,
        x0=np.array([1.0, 0.0]),
        method="L-BFGS-B",
        bounds=[(0.5, 3.0), (-3.0, 3.0)],
    )

    result_x = cast(np.ndarray, result.x)  # type: ignore[attr-defined]
    a_fit, b_fit = float(result_x[0]), float(result_x[1])
    return IrtItemParams(item_id=item_id, a=a_fit, b=b_fit, calibrated=True)
