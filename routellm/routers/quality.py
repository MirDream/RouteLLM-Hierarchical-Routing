"""Deterministic hidden quality model and noisy quality predictor.

The router only consumes ``predicted_quality``.  The simulator separately uses
``actual_quality`` for evaluation, so the decision does not directly observe
the ground-truth score.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass


def clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


@dataclass(frozen=True)
class QualityEstimate:
    predicted_quality: float
    actual_quality: float
    prediction_error: float


class DeterministicQualityModel:
    """Quality oracle for simulation plus a seed-controlled imperfect predictor."""

    def __init__(self, noise_amplitude: float = 0.04):
        if not 0.0 <= noise_amplitude <= 0.25:
            raise ValueError("noise_amplitude must be in [0, 0.25]")
        self.noise_amplitude = noise_amplitude

    @staticmethod
    def actual_quality(query: str, features, model) -> float:
        difficulty = clamp01(
            0.50 * features.complexity
            + 0.30 * features.code_signal
            + 0.20 * features.math_signal
        )
        model_strength = 0.55 * model.capability_prior + 0.45 * model.capability_level
        shortfall = max(0.0, difficulty - model.capability_level)
        lowered = query.lower()
        specialty_bonus = 0.08 if any(term.lower() in lowered for term in model.specialties) else 0.0
        quality = (
            0.30
            + 0.60 * model_strength
            - 0.18 * difficulty
            - 0.35 * shortfall
            + specialty_bonus
        )
        return round(clamp01(quality), 6)

    def prediction_error(self, query: str, model_name: str, seed: int) -> float:
        payload = f"{seed}|{model_name}|{query}".encode("utf-8")
        digest = hashlib.sha256(payload).digest()
        unit = int.from_bytes(digest[:8], "big") / float((1 << 64) - 1)
        return round((2.0 * unit - 1.0) * self.noise_amplitude, 6)

    def estimate(self, query: str, features, model, seed: int) -> QualityEstimate:
        actual = self.actual_quality(query, features, model)
        error = self.prediction_error(query, model.name, seed)
        predicted = round(clamp01(actual + error), 6)
        return QualityEstimate(
            predicted_quality=predicted,
            actual_quality=actual,
            prediction_error=error,
        )
