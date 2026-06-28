"""
Apply temperature calibration to score-probability matrices.

Conceptually we want to flatten/sharpen outcome probabilities (home/draw/away),
but the rest of the pipeline consumes the full score matrix (P(i-j) for each
scoreline). So we temperature-scale the matrix cell-by-cell and renormalize.
This preserves the *shape* of the distribution within each outcome category
while pulling the overall outcome probabilities toward / away from uniform.

For k=1.0 this is a no-op.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np


@dataclass
class Calibration:
    k: float
    source_file: Optional[str] = None

    @classmethod
    def load(cls, path: str | Path) -> Optional["Calibration"]:
        p = Path(path)
        if not p.exists():
            return None
        try:
            with open(p) as f:
                data = json.load(f)
            return cls(k=float(data["k"]), source_file=str(p))
        except (json.JSONDecodeError, KeyError, ValueError):
            return None

    @classmethod
    def identity(cls) -> "Calibration":
        return cls(k=1.0)

    def apply(self, matrix: np.ndarray) -> np.ndarray:
        """Temperature-scale every cell, renormalize."""
        if abs(self.k - 1.0) < 1e-6:
            return matrix
        # Clip to avoid 0^k issues
        clipped = np.maximum(matrix, 1e-12)
        scaled = clipped ** self.k
        scaled /= scaled.sum()
        return scaled
