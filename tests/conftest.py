from __future__ import annotations

import random

import numpy as np
import pytest

from src.bkt.schemas import AttemptObservation, BktParams
from src.bkt.update import bkt_update


def generate_synthetic_bkt_sequence(
    params: BktParams,
    n: int = 1000,
    seed: int = 42,
    n_students: int = 10,
) -> list[AttemptObservation]:
    """Generate attempts across multiple students for better BKT identifiability."""
    rng = random.Random(seed)
    attempts = []
    skill_id = "synth-skill"
    per_student = n // n_students
    for s in range(n_students):
        p_known = params.p_l0
        student_id = f"synth-student-{s}"
        for i in range(per_student):
            p_correct = p_known * (1 - params.p_slip) + \
                (1 - p_known) * params.p_guess
            is_correct = rng.random() < p_correct
            attempts.append(
                AttemptObservation(
                    student_id=student_id,
                    skill_id=skill_id,
                    is_correct=is_correct,
                    timestamp=float(s * per_student + i),
                )
            )
            p_known = bkt_update(
                p_known,
                params.p_transit,
                params.p_slip,
                params.p_guess,
                is_correct)
    return attempts


def generate_synthetic_2pl_attempts(
    a: float,
    b: float,
    n: int = 1000,
    seed: int = 42,
) -> list[tuple[float, bool]]:
    rng = np.random.default_rng(seed)
    thetas = rng.normal(0.0, 1.0, n)
    probs = 1.0 / (1.0 + np.exp(-a * (thetas - b)))
    correct = rng.random(n) < probs
    return list(zip(thetas.tolist(), correct.tolist(), strict=False))


@pytest.fixture
def sample_attempts():  # type: ignore[no-untyped-def]
    from src.llm_classifier.schemas import Attempt

    return [
        Attempt(
            id=f"att-{i}",
            topic="subtraction_borrow",
            problem_statement="53 - 26",
            canonical_solution="27",
            raw_steps=[],
            final_answer="33",
        )
        for i in range(20)
    ]
