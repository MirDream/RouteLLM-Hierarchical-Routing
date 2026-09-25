"""Unified routing strategies used by deterministic simulations."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from routellm.config.experiment_config import ExperimentConfig
from routellm.monitor.resource_monitor import NodeState
from routellm.routers.multimodel_router import CapabilityCandidate, MultiModelRouter
from routellm.scheduler.resource_scheduler import PairScore, ResourceAwareScheduler
from routellm.scheduler.scoring import UtilityWeights


@dataclass(frozen=True)
class StrategyDecision:
    strategy: str
    selected_model: str
    selected_node: str
    predicted_quality: float
    utility: float
    quality_fallback: bool
    routing_overhead_ms: float
    candidates: tuple[CapabilityCandidate, ...]
    pair_scores: tuple[PairScore, ...]


class RoutingStrategy(ABC):
    name: str

    def __init__(
        self,
        router: MultiModelRouter,
        scheduler: ResourceAwareScheduler,
        config: ExperimentConfig,
    ):
        self.router = router
        self.scheduler = scheduler
        self.config = config

    @staticmethod
    def _overhead(name: str, candidate_count: int, pair_count: int) -> float:
        base = {
            "capability_only": 0.035,
            "resource_only": 0.045,
            "joint_single_stage": 0.060,
            "hierarchical": 0.070,
        }[name]
        return round(base + 0.012 * candidate_count + 0.007 * pair_count, 6)

    @abstractmethod
    def decide(
        self,
        query: str,
        resource_states: dict[str, NodeState],
        seed: int,
    ) -> StrategyDecision:
        raise NotImplementedError

    def _all_candidates(self, query: str, seed: int) -> list[CapabilityCandidate]:
        return self.router.rank(query, top_k=len(self.router.models), seed=seed)


class CapabilityOnlyStrategy(RoutingStrategy):
    name = "capability_only"

    def decide(self, query, resource_states, seed) -> StrategyDecision:
        candidates = self._all_candidates(query, seed)
        selected_candidate = candidates[0]
        schedule = self.scheduler.schedule(
            [selected_candidate],
            resource_states,
            use_quality_constraint=False,
        )
        default_node = self.config.default_nodes[selected_candidate.model]
        default_pair = next(
            (
                pair
                for pair in schedule.pair_scores
                if pair.model == selected_candidate.model and pair.node == default_node
            ),
            None,
        )
        selected_pair = default_pair or schedule.pair_scores[0]
        return StrategyDecision(
            strategy=self.name,
            selected_model=selected_pair.model,
            selected_node=selected_pair.node,
            predicted_quality=selected_pair.predicted_quality,
            utility=selected_pair.utility,
            quality_fallback=False,
            routing_overhead_ms=self._overhead(self.name, len(candidates), len(schedule.pair_scores)),
            candidates=tuple(candidates),
            pair_scores=schedule.pair_scores,
        )


class ResourceOnlyStrategy(RoutingStrategy):
    name = "resource_only"

    def decide(self, query, resource_states, seed) -> StrategyDecision:
        candidates = self._all_candidates(query, seed)
        resource_weights = UtilityWeights(
            alpha_quality=0.0,
            beta_latency=0.65,
            gamma_cost=0.0,
            delta_resource_load=0.35,
        )
        schedule = self.scheduler.schedule(
            candidates,
            resource_states,
            use_quality_constraint=False,
            use_cost=False,
            weights=resource_weights,
        )
        return StrategyDecision(
            strategy=self.name,
            selected_model=schedule.selected_model,
            selected_node=schedule.selected_node,
            predicted_quality=schedule.predicted_quality,
            utility=schedule.utility,
            quality_fallback=False,
            routing_overhead_ms=self._overhead(self.name, len(candidates), len(schedule.pair_scores)),
            candidates=tuple(candidates),
            pair_scores=schedule.pair_scores,
        )


class JointSingleStageStrategy(RoutingStrategy):
    name = "joint_single_stage"

    def decide(self, query, resource_states, seed) -> StrategyDecision:
        candidates = self._all_candidates(query, seed)
        schedule = self.scheduler.schedule(
            candidates,
            resource_states,
            use_quality_constraint=False,
            use_resource_awareness=True,
            use_cost=True,
        )
        return StrategyDecision(
            strategy=self.name,
            selected_model=schedule.selected_model,
            selected_node=schedule.selected_node,
            predicted_quality=schedule.predicted_quality,
            utility=schedule.utility,
            quality_fallback=False,
            routing_overhead_ms=self._overhead(self.name, len(candidates), len(schedule.pair_scores)),
            candidates=tuple(candidates),
            pair_scores=schedule.pair_scores,
        )


class HierarchicalStrategy(RoutingStrategy):
    name = "hierarchical"

    def decide(self, query, resource_states, seed) -> StrategyDecision:
        top_k = self.config.top_k if self.config.ablation.use_topk else len(self.router.models)
        candidates = self.router.rank(query, top_k=top_k, seed=seed)
        schedule = self.scheduler.schedule(
            candidates,
            resource_states,
            use_quality_constraint=self.config.ablation.use_quality_constraint,
            use_resource_awareness=self.config.ablation.use_resource_awareness,
            use_cost=self.config.ablation.use_cost,
        )
        return StrategyDecision(
            strategy=self.name,
            selected_model=schedule.selected_model,
            selected_node=schedule.selected_node,
            predicted_quality=schedule.predicted_quality,
            utility=schedule.utility,
            quality_fallback=schedule.quality_fallback,
            routing_overhead_ms=self._overhead(self.name, len(candidates), len(schedule.pair_scores)),
            candidates=tuple(candidates),
            pair_scores=schedule.pair_scores,
        )


def build_strategy(
    name: str,
    router: MultiModelRouter,
    scheduler: ResourceAwareScheduler,
    config: ExperimentConfig,
) -> RoutingStrategy:
    strategies = {
        "capability_only": CapabilityOnlyStrategy,
        "resource_only": ResourceOnlyStrategy,
        "joint_single_stage": JointSingleStageStrategy,
        "hierarchical": HierarchicalStrategy,
    }
    try:
        strategy_type = strategies[name]
    except KeyError as error:
        raise ValueError(f"Unknown routing strategy: {name}") from error
    return strategy_type(router, scheduler, config)
