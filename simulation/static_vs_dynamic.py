"""Backward-compatible static vs dynamic simulation entry point.

``static`` maps to ``capability_only`` and ``dynamic`` maps to
``hierarchical``.  The richer four-strategy experiment lives in
``simulation.experiments`` and writes to ``results/``.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

from routellm.config.experiment_config import load_experiment_config
from simulation.simulator import simulate
from simulation.workload import build_request_trace


SEED = 20260924
REQUEST_COUNT = 300


def _legacy_summary(summary: dict) -> dict:
    return {
        "requests": summary["requests"],
        "mean_actual_quality": summary["mean_actual_quality"],
        "median_actual_quality": summary["median_actual_quality"],
        "quality_violation_rate": summary["quality_violation_rate"],
        "quality_fallback_count": summary["quality_fallback_count"],
        "mean_latency_ms": round(summary["mean_latency_ms"], 3),
        "median_latency_ms": round(summary["median_latency_ms"], 3),
        "p95_latency_ms": round(summary["p95_latency_ms"], 3),
        "max_latency_ms": round(summary["max_latency_ms"], 3),
        "sla_ms": summary["sla_ms"],
        "sla_violation_rate": summary["sla_violation_rate"],
        "sla_violation_rate_pct": round(100.0 * summary["sla_violation_rate"], 3),
        "total_cost": round(summary["total_cost"], 6),
        "mean_cost_per_request": summary["mean_cost_per_request"],
        "model_selections": summary["model_selection_counts"],
        "node_selections": summary["node_selection_counts"],
        "peak_cloud_queue": round(summary["peak_cloud_queue"], 3),
        "peak_edge_queue": round(summary["peak_edge_queue"], 3),
        "average_cloud_queue": summary["average_cloud_queue"],
        "average_edge_queue": summary["average_edge_queue"],
        "cloud_ratio": summary["cloud_ratio"],
        "edge_ratio": summary["edge_ratio"],
        "mean_routing_overhead_ms": summary["mean_routing_overhead_ms"],
    }


def _comparison(static: dict, dynamic: dict) -> dict:
    def reduction(metric: str) -> float:
        baseline = static[metric]
        return round(100.0 * (baseline - dynamic[metric]) / baseline, 3) if baseline else 0.0

    return {
        "mean_latency_reduction_pct": reduction("mean_latency_ms"),
        "p95_latency_reduction_pct": reduction("p95_latency_ms"),
        "sla_violation_reduction_points": round(
            static["sla_violation_rate_pct"] - dynamic["sla_violation_rate_pct"], 3
        ),
        "cost_reduction_pct": reduction("total_cost"),
        "cloud_peak_queue_reduction_pct": reduction("peak_cloud_queue"),
        "mean_quality_change": round(
            dynamic["mean_actual_quality"] - static["mean_actual_quality"], 6
        ),
    }


def run(output_dir: Path, count: int = REQUEST_COUNT, seed: int = SEED) -> dict:
    config = load_experiment_config()
    workload_name = "high_load"
    trace = build_request_trace(config, workload_name, seed, count=count)
    static_records, static_full = simulate(
        "capability_only", workload_name, seed, trace, config
    )
    dynamic_records, dynamic_full = simulate(
        "hierarchical", workload_name, seed, trace, config
    )
    static_summary = _legacy_summary(static_full)
    dynamic_summary = _legacy_summary(dynamic_full)
    result = {
        "simulation": {
            "seed": seed,
            "request_count": count,
            "workload": workload_name,
            "sla_ms": config.sla_ms,
            "q_min": config.q_min,
            "real_vllm_used": False,
            "resource_source": "deterministic simulated cloud and edge queues",
            "static_strategy": "capability_only",
            "dynamic_strategy": "hierarchical",
        },
        "static": static_summary,
        "dynamic": dynamic_summary,
        "comparison": _comparison(static_summary, dynamic_summary),
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "summary.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    rows = []
    for record in static_records:
        rows.append({**record.to_dict(), "strategy": "static"})
    for record in dynamic_records:
        rows.append({**record.to_dict(), "strategy": "dynamic"})
    with (output_dir / "requests.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    return result


def main() -> None:
    project_root = Path(__file__).resolve().parents[1]
    print(json.dumps(run(project_root / "simulation_output"), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
