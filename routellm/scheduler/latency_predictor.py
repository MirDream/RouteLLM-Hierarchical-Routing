"""Transparent latency estimator for simulated scheduling experiments."""

from __future__ import annotations

from routellm.monitor.resource_monitor import NodeState
from routellm.routers.multimodel_router import ModelProfile


class LatencyPredictor:
    def predict_ms(self, model: ModelProfile, node: NodeState) -> float:
        compute_ms = model.base_latency_ms * (1.0 + 1.5 * node.gpu_utilization)
        queue_ms = node.queue_length * 60.0
        throughput_penalty_ms = 400.0 / max(node.throughput_tokens_per_sec, 1.0)
        return round(
            compute_ms + queue_ms + node.network_latency_ms + throughput_penalty_ms,
            6,
        )

