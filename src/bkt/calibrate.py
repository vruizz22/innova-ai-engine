from __future__ import annotations

from itertools import product

import numpy as np

from .schemas import AttemptObservation, BktParams
from .update import bkt_update


def _compute_log_likelihood(
    attempts: list[AttemptObservation],
    p_l0: float,
    p_transit: float,
    p_slip: float,
    p_guess: float,
) -> float:
    """Compute log-likelihood of attempt sequence under given BKT params."""
    # Group by student
    from collections import defaultdict
    by_student: dict[str, list[AttemptObservation]] = defaultdict(list)
    for a in attempts:
        by_student[a.student_id].append(a)

    total_ll = 0.0
    for obs_list in by_student.values():
        sorted_obs = sorted(obs_list, key=lambda x: x.timestamp)
        p_known = p_l0
        for obs in sorted_obs:
            p_correct = p_known * (1.0 - p_slip) + (1.0 - p_known) * p_guess
            p_correct = max(1e-9, min(1.0 - 1e-9, p_correct))
            if obs.is_correct:
                total_ll += np.log(p_correct)
            else:
                total_ll += np.log(1.0 - p_correct)
            p_known = bkt_update(
                p_known,
                p_transit,
                p_slip,
                p_guess,
                obs.is_correct)
    return float(total_ll)


def calibrate_skill(attempts: list[AttemptObservation]) -> BktParams:
    """
    Brute-force grid search over (p_l0, p_transit, p_slip, p_guess).
    Grid: [0.05, 0.50] step 0.05. Minimizes negative log-likelihood.
    """
    grid = [round(x, 2) for x in np.arange(0.05, 0.96, 0.05).tolist()]
    best_params: tuple[float, float, float, float] | None = None
    best_ll = float("-inf")

    for p_l0, p_transit, p_slip, p_guess in product(grid, grid, grid, grid):
        if p_slip + p_guess >= 1.0:
            continue
        ll = _compute_log_likelihood(
            attempts, p_l0, p_transit, p_slip, p_guess)
        if ll > best_ll:
            best_ll = ll
            best_params = (p_l0, p_transit, p_slip, p_guess)

    if best_params is None:
        return BktParams(
            p_l0=0.3,
            p_transit=0.1,
            p_slip=0.1,
            p_guess=0.2,
            log_likelihood=best_ll)

    return BktParams(
        p_l0=best_params[0],
        p_transit=best_params[1],
        p_slip=best_params[2],
        p_guess=best_params[3],
        log_likelihood=best_ll,
    )
