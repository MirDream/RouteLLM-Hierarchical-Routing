"""Coordinator for capability routing, resource scheduling and inference."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Callable, Optional

from routellm.monitor.resource_monitor import ResourceMonitor
from routellm.routers.multimodel_router import MultiModelRouter
from routellm.scheduler.resource_scheduler import ResourceAwareScheduler


@dataclass(frozen=True)
class DecisionRecord:
    timestamp: str
    query: str
    query_features: dict
    capability_scores: dict[str, float]
    predicted_qualities: dict[str, float]
    top_k_candidates: list[dict]
    resource_states: dict[str, dict]
    final_utility_scores: list[dict]
    selected_model: str
    selected_node: str
    selected_predicted_quality: float
    quality_threshold: float
    quality_fallback: bool

    def to_dict(self) -> dict:
        return asdict(self)


class JsonlDecisionLogger:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def write(self, record: DecisionRecord) -> None:
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record.to_dict(), ensure_ascii=False) + "\n")


class HierarchicalController:
    def __init__(
        self,
        router: MultiModelRouter,
        monitor: ResourceMonitor,
        scheduler: ResourceAwareScheduler,
        top_k: int = 2,
        inference_client: Optional[Callable] = None,
        decision_logger: JsonlDecisionLogger | None = None,
        seed: int = 0,
    ):
        self.router = router
        self.monitor = monitor
        self.scheduler = scheduler
        self.top_k = top_k
        self.inference_client = inference_client or self._simulated_inference
        self.decision_logger = decision_logger
        self.seed = seed
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.completion))

    @staticmethod
    def _simulated_inference(*, model: str, node: str, messages: list[dict], **kwargs):
        del kwargs
        return SimpleNamespace(
            model=model,
            node=node,
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content=f"simulated response from {model}@{node}")
                )
            ],
        )

    def decide(self, query: str) -> DecisionRecord:
        candidates = self.router.rank(query, top_k=self.top_k, seed=self.seed)
        states = self.monitor.snapshot()
        schedule = self.scheduler.schedule(candidates, states)
        features = self.router.last_features.to_dict() if self.router.last_features else {}
        record = DecisionRecord(
            timestamp=datetime.now(timezone.utc).isoformat(),
            query=query,
            query_features=features,
            capability_scores={candidate.model: candidate.score for candidate in candidates},
            predicted_qualities={
                candidate.model: candidate.predicted_quality for candidate in candidates
            },
            top_k_candidates=[candidate.to_dict() for candidate in candidates],
            resource_states={name: state.to_dict() for name, state in states.items()},
            final_utility_scores=[score.to_dict() for score in schedule.pair_scores],
            selected_model=schedule.selected_model,
            selected_node=schedule.selected_node,
            selected_predicted_quality=schedule.predicted_quality,
            quality_threshold=schedule.q_min,
            quality_fallback=schedule.quality_fallback,
        )
        if self.decision_logger:
            self.decision_logger.write(record)
        return record

    def completion(self, *, messages: list[dict], **kwargs):
        query = messages[-1]["content"]
        decision = self.decide(query)
        response = self.inference_client(
            model=decision.selected_model,
            node=decision.selected_node,
            messages=messages,
            **kwargs,
        )
        response.routing_decision = decision
        return response
