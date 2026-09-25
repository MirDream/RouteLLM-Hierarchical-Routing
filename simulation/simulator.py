"""Deterministic cloud/edge simulator shared by all routing strategies."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass

from routellm.config.experiment_config import ExperimentConfig
from routellm.monitor.resource_monitor import NodeState
from routellm.routers.multimodel_router import ModelProfile, MultiModelRouter
from routellm.scheduler.resource_scheduler import ResourceAwareScheduler
from routellm.strategies import build_strategy
from simulation.metrics import summarize_records
from simulation.workload import WorkloadItem, trace_fingerprint


@dataclass(frozen=True)
class SimulationRecord:
    strategy: str
    workload: str
    seed: int
    trace_fingerprint: str
    request_id: int
    simulated_time_s: float
    query_type: str
    selected_model: str
    selected_node: str
    predicted_quality: float
    actual_quality: float
    quality_threshold: float
    quality_violation: bool
    quality_fallback: bool
    utility: float
    predicted_latency_ms: float
    actual_latency_ms: float
    request_cost: float
    routing_overhead_ms: float
    selected_queue_before: float
    cloud_queue_after: float
    edge_queue_after: float
    sla_violation: bool

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class QueueState:
    cloud: float = 0.0
    edge_1: float = 0.0

    def decay(self, elapsed_s: float, service_rates: dict[str, float]) -> None:
        self.cloud = max(0.0, self.cloud - service_rates["cloud"] * elapsed_s)
        self.edge_1 = max(0.0, self.edge_1 - service_rates["edge-1"] * elapsed_s)

    def add(self, node: str) -> None:
        if node == "cloud":
            self.cloud += 1.0
        elif node == "edge-1":
            self.edge_1 += 1.0
        else:
            raise KeyError(node)


def build_profiles() -> list[ModelProfile]:
    return [
        ModelProfile(
            "model-a", 0.98, 0.95, 20, 270, 0.020,
            ("proof", "prove", "证明", "matrix", "矩阵", "equation"),
        ),
        ModelProfile(
            "model-b", 0.86, 0.70, 10, 220, 0.010,
            ("code", "python", "代码", "算法", "function"),
        ),
        ModelProfile(
            "model-c", 0.70, 0.45, 6, 125, 0.003,
            ("summary", "summarize", "总结"),
        ),
    ]


def node_states(queues: QueueState) -> dict[str, NodeState]:
    cloud_gpu = min(0.98, 0.24 + 0.075 * queues.cloud)
    edge_gpu = min(0.96, 0.18 + 0.090 * queues.edge_1)
    return {
        "cloud": NodeState(
            node="cloud",
            available_models=("model-a", "model-b"),
            gpu_utilization=cloud_gpu,
            total_vram_gb=80,
            free_vram_gb=max(20.0, 64.0 - 2.8 * queues.cloud),
            queue_length=math.ceil(queues.cloud),
            network_latency_ms=72,
            throughput_tokens_per_sec=max(22.0, 78.0 - 3.0 * queues.cloud),
        ),
        "edge-1": NodeState(
            node="edge-1",
            available_models=("model-b", "model-c"),
            gpu_utilization=edge_gpu,
            total_vram_gb=24,
            free_vram_gb=max(10.0, 20.0 - 1.4 * queues.edge_1),
            queue_length=math.ceil(queues.edge_1),
            network_latency_ms=9,
            throughput_tokens_per_sec=max(28.0, 92.0 - 4.0 * queues.edge_1),
        ),
    }


def simulate(
    strategy_name: str,
    workload_name: str,
    seed: int,
    trace: list[WorkloadItem],
    config: ExperimentConfig,
) -> tuple[list[SimulationRecord], dict]:
    profiles = build_profiles()
    profiles_by_name = {profile.name: profile for profile in profiles}
    router = MultiModelRouter(profiles)
    scheduler = ResourceAwareScheduler(
        router.models,
        weights=config.utility_weights,
        q_min=config.q_min,
        latency_scale_ms=config.latency_scale_ms,
    )
    strategy = build_strategy(strategy_name, router, scheduler, config)
    queues = QueueState()
    elapsed = 0.0
    fingerprint = trace_fingerprint(trace)
    records: list[SimulationRecord] = []

    for item in trace:
        elapsed += item.arrival_gap_s
        queues.decay(item.arrival_gap_s, config.service_rates)
        states = node_states(queues)
        decision = strategy.decide(item.query, states, seed)
        pair = next(
            score
            for score in decision.pair_scores
            if score.model == decision.selected_model and score.node == decision.selected_node
        )
        selected_queue = queues.cloud if decision.selected_node == "cloud" else queues.edge_1
        actual_latency_ms = round(pair.estimated_latency_ms * item.latency_jitter, 6)
        actual_quality = router.actual_quality(item.query, decision.selected_model)
        profile = profiles_by_name[decision.selected_model]
        input_tokens = max(1, math.ceil(len(item.query) / 4))
        request_cost = round(
            profile.cost_per_1k_tokens * (input_tokens + item.output_tokens) / 1000.0,
            8,
        )
        queues.add(decision.selected_node)
        records.append(
            SimulationRecord(
                strategy=strategy_name,
                workload=workload_name,
                seed=seed,
                trace_fingerprint=fingerprint,
                request_id=item.request_id,
                simulated_time_s=round(elapsed, 6),
                query_type=item.query_type,
                selected_model=decision.selected_model,
                selected_node=decision.selected_node,
                predicted_quality=decision.predicted_quality,
                actual_quality=actual_quality,
                quality_threshold=config.q_min,
                quality_violation=actual_quality < config.q_min,
                quality_fallback=decision.quality_fallback,
                utility=decision.utility,
                predicted_latency_ms=pair.estimated_latency_ms,
                actual_latency_ms=actual_latency_ms,
                request_cost=request_cost,
                routing_overhead_ms=decision.routing_overhead_ms,
                selected_queue_before=round(selected_queue, 6),
                cloud_queue_after=round(queues.cloud, 6),
                edge_queue_after=round(queues.edge_1, 6),
                sla_violation=actual_latency_ms > config.sla_ms,
            )
        )
    summary = summarize_records(records, q_min=config.q_min, sla_ms=config.sla_ms)
    summary.update(
        {
            "strategy": strategy_name,
            "workload": workload_name,
            "seed": seed,
            "trace_fingerprint": fingerprint,
        }
    )
    return records, summary
