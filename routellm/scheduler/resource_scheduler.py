"""Resource-aware selection of the best feasible Model x Node pair."""

from __future__ import annotations

from dataclasses import asdict, dataclass

from routellm.monitor.resource_monitor import NodeState
from routellm.routers.multimodel_router import CapabilityCandidate, ModelProfile
from routellm.scheduler.latency_predictor import LatencyPredictor
from routellm.scheduler.scoring import UtilityWeights, resource_load, utility_score


@dataclass(frozen=True)
class PairScore:
    model: str
    node: str
    predicted_quality: float
    estimated_latency_ms: float
    normalized_latency: float
    normalized_cost: float
    resource_load: float
    utility: float
    meets_quality_constraint: bool

    @property
    def capability_score(self) -> float:
        return self.predicted_quality

    def to_dict(self) -> dict:
        data = asdict(self)
        data["capability_score"] = self.predicted_quality
        return data


@dataclass(frozen=True)
class ScheduleDecision:
    selected_model: str
    selected_node: str
    utility: float
    predicted_quality: float
    quality_fallback: bool
    q_min: float
    pair_scores: tuple[PairScore, ...]


class ResourceAwareScheduler:
    def __init__(
        self,
        model_profiles: dict[str, ModelProfile],
        weights: UtilityWeights | None = None,
        latency_predictor: LatencyPredictor | None = None,
        q_min: float = 0.70,
        latency_scale_ms: float = 2500.0,
    ):
        self.model_profiles = model_profiles
        self.weights = weights or UtilityWeights()
        self.latency_predictor = latency_predictor or LatencyPredictor()
        if not 0.0 <= q_min <= 1.0:
            raise ValueError("q_min must be in [0, 1]")
        if latency_scale_ms <= 0:
            raise ValueError("latency_scale_ms must be positive")
        self.q_min = q_min
        self.latency_scale_ms = latency_scale_ms

    def schedule(
        self,
        candidates: list[CapabilityCandidate],
        resource_states: dict[str, NodeState],
        *,
        use_quality_constraint: bool = True,
        use_resource_awareness: bool = True,
        use_cost: bool = True,
        weights: UtilityWeights | None = None,
    ) -> ScheduleDecision:
        active_weights = weights or self.weights
        max_cost = max((profile.cost_per_1k_tokens for profile in self.model_profiles.values()), default=1.0)
        scores: list[PairScore] = []
        for candidate in candidates:
            profile = self.model_profiles[candidate.model]
            for state in resource_states.values():
                if candidate.model not in state.available_models:
                    continue
                if state.free_vram_gb < profile.required_vram_gb:
                    continue
                latency_ms = self.latency_predictor.predict_ms(profile, state)
                load = resource_load(state)
                normalized_latency = min(max(latency_ms / self.latency_scale_ms, 0.0), 1.0)
                normalized_cost = profile.cost_per_1k_tokens / max(max_cost, 1e-12)
                utility = utility_score(
                    predicted_quality=candidate.predicted_quality,
                    normalized_latency=normalized_latency if use_resource_awareness else 0.0,
                    normalized_cost=normalized_cost if use_cost else 0.0,
                    normalized_resource_load=load if use_resource_awareness else 0.0,
                    weights=active_weights,
                )
                scores.append(
                    PairScore(
                        model=candidate.model,
                        node=state.node,
                        predicted_quality=candidate.predicted_quality,
                        estimated_latency_ms=latency_ms,
                        normalized_latency=round(normalized_latency, 6),
                        normalized_cost=round(normalized_cost, 6),
                        resource_load=load,
                        utility=utility,
                        meets_quality_constraint=candidate.predicted_quality >= self.q_min,
                    )
                )
        if not scores:
            raise RuntimeError("No feasible Model x Node pair for the Top-K candidates")
        quality_fallback = False
        eligible = scores
        if use_quality_constraint:
            eligible = [score for score in scores if score.meets_quality_constraint]
            if not eligible:
                quality_fallback = True
                highest_quality = max(score.predicted_quality for score in scores)
                eligible = [
                    score for score in scores if score.predicted_quality == highest_quality
                ]
        scores.sort(key=lambda item: (-item.utility, -item.predicted_quality, item.model, item.node))
        eligible.sort(
            key=lambda item: (-item.utility, -item.predicted_quality, item.model, item.node)
        )
        best = eligible[0]
        return ScheduleDecision(
            selected_model=best.model,
            selected_node=best.node,
            utility=best.utility,
            predicted_quality=best.predicted_quality,
            quality_fallback=quality_fallback,
            q_min=self.q_min,
            pair_scores=tuple(scores),
        )
