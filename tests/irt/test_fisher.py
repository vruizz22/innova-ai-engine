from __future__ import annotations

from src.irt.fisher import fisher_information, pick_best_item


def test_fisher_information_peaks_near_difficulty() -> None:
    """Fisher information I(theta) must peak at theta == b."""
    a, b = 1.5, 0.3
    thetas = [b - 1.0, b - 0.5, b, b + 0.5, b + 1.0]
    infos = [fisher_information(a=a, b=b, theta=t) for t in thetas]
    peak_idx = infos.index(max(infos))
    assert peak_idx == 2


def test_fisher_information_is_positive() -> None:
    info = fisher_information(a=1.0, b=0.0, theta=0.0)
    assert info > 0.0


def test_pick_best_item_selects_closest_b() -> None:
    candidates = [
        ("item-easy", 1.0, -2.0),
        ("item-match", 1.0, 0.0),
        ("item-hard", 1.0, 2.0),
    ]
    best = pick_best_item(student_theta=0.0, candidates=candidates)
    assert best == "item-match"
