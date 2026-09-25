"""Metrics for quality-aware routing simulations."""

from __future__ import annotations

import math
import statistics
from collections import Counter


def percentile(values: list[float], pct: float) -> float:
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, math.ceil(pct * len(ordered)) - 1))
    return ordered[index]


def summarize_records(records, q_min: float, sla_ms: float) -> dict:
    if not records:
        raise ValueError("At least one simulation record is required")
    qualities = [record.actual_quality for record in records]
    latencies = [record.actual_latency_ms for record in records]
    costs = [record.request_cost for record in records]
    overheads = [record.routing_overhead_ms for record in records]
    model_counts = Counter(record.selected_model for record in records)
    node_counts = Counter(record.selected_node for record in records)
    total = len(records)
    return {
        "requests": total,
        "q_min": q_min,
        "mean_actual_quality": round(statistics.fmean(qualities), 6),
        "median_actual_quality": round(statistics.median(qualities), 6),
        "quality_violation_rate": round(
            sum(value < q_min for value in qualities) / total, 6
        ),
        "quality_fallback_count": sum(record.quality_fallback for record in records),
        "mean_latency_ms": round(statistics.fmean(latencies), 6),
        "median_latency_ms": round(statistics.median(latencies), 6),
        "p95_latency_ms": round(percentile(latencies, 0.95), 6),
        "max_latency_ms": round(max(latencies), 6),
        "sla_ms": sla_ms,
        "sla_violation_rate": round(
            sum(value > sla_ms for value in latencies) / total, 6
        ),
        "total_cost": round(sum(costs), 8),
        "mean_cost_per_request": round(statistics.fmean(costs), 8),
        "peak_cloud_queue": round(max(record.cloud_queue_after for record in records), 6),
        "peak_edge_queue": round(max(record.edge_queue_after for record in records), 6),
        "average_cloud_queue": round(
            statistics.fmean(record.cloud_queue_after for record in records), 6
        ),
        "average_edge_queue": round(
            statistics.fmean(record.edge_queue_after for record in records), 6
        ),
        "model_selection_counts": dict(sorted(model_counts.items())),
        "node_selection_counts": dict(sorted(node_counts.items())),
        "cloud_ratio": round(node_counts.get("cloud", 0) / total, 6),
        "edge_ratio": round(node_counts.get("edge-1", 0) / total, 6),
        "mean_routing_overhead_ms": round(statistics.fmean(overheads), 6),
    }
