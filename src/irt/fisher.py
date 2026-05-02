from __future__ import annotations

import numpy as np


def fisher_information(a: float, b: float, theta: float) -> float:
    """Fisher information I(theta) = a^2 * P(theta) * (1 - P(theta))."""
    p = 1.0 / (1.0 + np.exp(-a * (theta - b)))
    return float(a**2 * p * (1.0 - p))


def pick_best_item(
    student_theta: float,
    candidates: list[tuple[str, float, float]],
) -> str:
    """Return item_id with maximum Fisher information for given theta."""
    best_id = candidates[0][0]
    best_info = -1.0
    for item_id, a, b in candidates:
        info = fisher_information(a, b, student_theta)
        if info > best_info:
            best_info = info
            best_id = item_id
    return best_id
