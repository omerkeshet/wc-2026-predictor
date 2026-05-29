"""Football prediction model package."""

from .calibration import Calibration
from .dixon_coles import (
    DixonColesFit,
    fit,
    score_matrix,
    outcome_probs,
    expected_goals,
    most_likely_score,
)
from .simulator import Group, simulate

__all__ = [
    "Calibration",
    "DixonColesFit",
    "fit",
    "score_matrix",
    "outcome_probs",
    "expected_goals",
    "most_likely_score",
    "Group",
    "simulate",
]
