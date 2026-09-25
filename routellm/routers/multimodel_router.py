"""Capability-aware Top-K routing for multiple candidate models.

This module is additive: the original two-model routers in routers.py remain
unchanged and continue to support the RouteLLM baseline.
"""

from __future__ import annotations

import math
import re
from dataclasses import asdict, dataclass
from typing import Iterable

from routellm.routers.quality import DeterministicQualityModel


@dataclass(frozen=True)
class QueryFeatures:
    token_estimate: int
    complexity: float
    code_signal: float
    math_signal: float
    non_ascii_ratio: float

    def to_dict(self) -> dict:
        return asdict(self)


class QueryEncoder:
    """Lightweight deterministic encoder used by the experimental prototype."""

    CODE_TERMS = {"code", "python", "function", "class", "算法", "代码", "调试"}
    MATH_TERMS = {"proof", "equation", "integral", "matrix", "证明", "方程", "矩阵"}

    def encode(self, query: str) -> QueryFeatures:
        words = re.findall(r"[\w]+", query.lower(), flags=re.UNICODE)
        token_estimate = max(1, math.ceil(len(query) / 4))
        punctuation = sum(query.count(mark) for mark in ("?", "？", ":", "：", "(", ")"))
        length_score = min(token_estimate / 160.0, 1.0)
        structure_score = min(punctuation / 8.0, 1.0)
        complexity = min(1.0, 0.2 + 0.6 * length_score + 0.2 * structure_score)
        code_hits = sum(term in words or term in query.lower() for term in self.CODE_TERMS)
        math_hits = sum(term in words or term in query.lower() for term in self.MATH_TERMS)
        non_ascii = sum(ord(char) > 127 for char in query)
        return QueryFeatures(
            token_estimate=token_estimate,
            complexity=round(complexity, 6),
            code_signal=min(code_hits / 2.0, 1.0),
            math_signal=min(math_hits / 2.0, 1.0),
            non_ascii_ratio=round(non_ascii / max(len(query), 1), 6),
        )


@dataclass(frozen=True)
class ModelProfile:
    name: str
    capability_prior: float
    capability_level: float
    required_vram_gb: float
    base_latency_ms: float
    cost_per_1k_tokens: float
    specialties: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for field_name in ("capability_prior", "capability_level"):
            value = getattr(self, field_name)
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{field_name} must be in [0, 1]")


@dataclass(frozen=True)
class CapabilityCandidate:
    model: str
    predicted_quality: float
    rank: int

    @property
    def score(self) -> float:
        """Backward-compatible alias used by the original demo and tests."""
        return self.predicted_quality

    def to_dict(self) -> dict:
        data = asdict(self)
        data["score"] = self.predicted_quality
        return data


class MultiModelRouter:
    """Scores all model profiles and returns a capability-ranked Top-K list."""

    def __init__(
        self,
        models: Iterable[ModelProfile],
        encoder: QueryEncoder | None = None,
        quality_model: DeterministicQualityModel | None = None,
    ):
        self.models = {model.name: model for model in models}
        if not self.models:
            raise ValueError("At least one model profile is required")
        self.encoder = encoder or QueryEncoder()
        self.quality_model = quality_model or DeterministicQualityModel()
        self.last_features: QueryFeatures | None = None

    def score_models(self, query: str, seed: int = 0) -> dict[str, float]:
        features = self.encoder.encode(query)
        self.last_features = features
        scores: dict[str, float] = {}
        for profile in self.models.values():
            estimate = self.quality_model.estimate(query, features, profile, seed)
            scores[profile.name] = estimate.predicted_quality
        return scores

    def rank(self, query: str, top_k: int = 2, seed: int = 0) -> list[CapabilityCandidate]:
        if top_k < 1:
            raise ValueError("top_k must be at least 1")
        scores = self.score_models(query, seed=seed)
        ordered = sorted(scores.items(), key=lambda item: (-item[1], item[0]))[:top_k]
        return [
            CapabilityCandidate(model=model, predicted_quality=score, rank=index)
            for index, (model, score) in enumerate(ordered, start=1)
        ]

    def actual_quality(self, query: str, model_name: str) -> float:
        features = self.encoder.encode(query)
        return self.quality_model.actual_quality(query, features, self.models[model_name])
