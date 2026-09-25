"""Utility scoring primitives for Model x Node scheduling."""

from __future__ import annotations

from dataclasses import dataclass

from routellm.monitor.resource_monitor import NodeState


@dataclass(frozen=True)
class UtilityWeights:
    alpha_quality: float = 0.45
    beta_latency: float = 0.30
    gamma_cost: float = 0.10
    delta_resource_load: float = 0.15

    def __post_init__(self) -> None:
        values = (
            self.alpha_quality,
            self.beta_latency,
            self.gamma_cost,
            self.delta_resource_load,
        )
        if any(value < 0 for value in values):
            raise ValueError("Utility weights cannot be negative")
        if abs(sum(values) - 1.0) > 1e-9:
            raise ValueError("Utility weights must sum to 1.0")


def resource_load(node: NodeState) -> float:
    queue_pressure = min(node.queue_length / 10.0, 1.0)
    memory_pressure = 1.0 - min(node.free_vram_gb / node.total_vram_gb, 1.0)
    return round(
        0.45 * node.gpu_utilization + 0.30 * queue_pressure + 0.25 * memory_pressure,
        6,
    )


def utility_score(
    predicted_quality: float,
    normalized_latency: float,
    normalized_cost: float,
    normalized_resource_load: float,
    weights: UtilityWeights,
) -> float:
    values = (
        predicted_quality,
        normalized_latency,
        normalized_cost,
        normalized_resource_load,
    )
    if any(value < 0.0 or value > 1.0 for value in values):
        raise ValueError("Utility inputs must be normalized to [0, 1]")
    utility = (
        weights.alpha_quality * predicted_quality
        - weights.beta_latency * normalized_latency
        - weights.gamma_cost * normalized_cost
        - weights.delta_resource_load * normalized_resource_load
    )
    return round(utility, 6)
