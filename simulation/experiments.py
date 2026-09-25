"""Run and aggregate strategy x workload x seed experiments."""

from __future__ import annotations

import csv
import json
import statistics
from pathlib import Path

from routellm.config.experiment_config import load_experiment_config
from simulation.simulator import simulate
from simulation.workload import build_request_trace


RAW_METRICS = (
    "requests",
    "q_min",
    "mean_actual_quality",
    "median_actual_quality",
    "quality_violation_rate",
    "quality_fallback_count",
    "mean_latency_ms",
    "median_latency_ms",
    "p95_latency_ms",
    "max_latency_ms",
    "sla_ms",
    "sla_violation_rate",
    "total_cost",
    "mean_cost_per_request",
    "peak_cloud_queue",
    "peak_edge_queue",
    "average_cloud_queue",
    "average_edge_queue",
    "cloud_ratio",
    "edge_ratio",
    "mean_routing_overhead_ms",
)


def _mean(values):
    return statistics.fmean(values)


def _std(values):
    return statistics.stdev(values) if len(values) > 1 else 0.0


def _rounded(value):
    return round(float(value), 6)


def aggregate_group(runs: list[dict]) -> dict:
    first = runs[0]
    row = {
        "strategy": first["strategy"],
        "workload": first["workload"],
        "run_count": len(runs),
        "requests_per_run": first["requests"],
        "q_min": first["q_min"],
        "sla_ms": first["sla_ms"],
    }
    mappings = {
        "mean_actual_quality": ("mean_actual_quality", "std_actual_quality"),
        "median_actual_quality": ("median_actual_quality", "std_median_actual_quality"),
        "quality_violation_rate": ("quality_violation_rate", "std_quality_violation_rate"),
        "quality_fallback_count": ("quality_fallback_count", "std_quality_fallback_count"),
        "mean_latency_ms": ("mean_latency_ms", "std_latency_ms"),
        "median_latency_ms": ("median_latency_ms", "std_median_latency_ms"),
        "p95_latency_ms": ("p95_latency_ms", "std_p95_latency_ms"),
        "max_latency_ms": ("max_latency_ms", "std_max_latency_ms"),
        "sla_violation_rate": ("sla_violation_rate", "std_sla_violation_rate"),
        "total_cost": ("total_cost", "std_total_cost"),
        "mean_cost_per_request": ("mean_cost_per_request", "std_mean_cost_per_request"),
        "peak_cloud_queue": ("peak_cloud_queue", "std_peak_cloud_queue"),
        "peak_edge_queue": ("peak_edge_queue", "std_peak_edge_queue"),
        "average_cloud_queue": ("average_cloud_queue", "std_average_cloud_queue"),
        "average_edge_queue": ("average_edge_queue", "std_average_edge_queue"),
        "cloud_ratio": ("cloud_ratio", "std_cloud_ratio"),
        "edge_ratio": ("edge_ratio", "std_edge_ratio"),
        "mean_routing_overhead_ms": (
            "mean_routing_overhead_ms",
            "std_routing_overhead_ms",
        ),
    }
    for source, (mean_name, std_name) in mappings.items():
        values = [float(run[source]) for run in runs]
        row[mean_name] = _rounded(_mean(values))
        row[std_name] = _rounded(_std(values))
    row["model_selection_counts"] = {
        model: _rounded(_mean([run["model_selection_counts"].get(model, 0) for run in runs]))
        for model in ("model-a", "model-b", "model-c")
    }
    row["node_selection_counts"] = {
        node: _rounded(_mean([run["node_selection_counts"].get(node, 0) for run in runs]))
        for node in ("cloud", "edge-1")
    }
    return row


def _csv_safe(row: dict) -> dict:
    result = dict(row)
    for key in ("model_selection_counts", "node_selection_counts"):
        if key in result:
            result[key] = json.dumps(result[key], ensure_ascii=False, sort_keys=True)
    return result


def print_comparison_table(summary_rows: list[dict]) -> None:
    order = ("capability_only", "resource_only", "joint_single_stage", "hierarchical")
    for workload in ("low_load", "medium_load", "high_load"):
        print(f"\nWorkload: {workload.upper()}")
        print(
            f"{'Strategy':22} {'Quality':>8} {'Q-Viol':>8} {'Latency':>10} {'P95':>10} "
            f"{'SLA-Viol':>10} {'Cost':>10} {'Cloud%':>8}"
        )
        by_name = {row["strategy"]: row for row in summary_rows if row["workload"] == workload}
        for name in order:
            row = by_name[name]
            print(
                f"{name:22} "
                f"{row['mean_actual_quality']:8.3f} "
                f"{100.0 * row['quality_violation_rate']:7.1f}% "
                f"{row['mean_latency_ms']:10.1f} "
                f"{row['p95_latency_ms']:10.1f} "
                f"{100.0 * row['sla_violation_rate']:9.1f}% "
                f"{row['total_cost']:10.4f} "
                f"{100.0 * row['cloud_ratio']:7.1f}%"
            )


def run_experiments(output_dir: Path, config_path: str | Path | None = None) -> dict:
    config = load_experiment_config(config_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    raw_runs: list[dict] = []

    for workload in config.workloads:
        for seed in config.seeds:
            trace = build_request_trace(config, workload, seed)
            expected_fingerprint = None
            for strategy in config.strategies:
                _, summary = simulate(strategy, workload, seed, trace, config)
                if expected_fingerprint is None:
                    expected_fingerprint = summary["trace_fingerprint"]
                elif summary["trace_fingerprint"] != expected_fingerprint:
                    raise RuntimeError("Strategies did not receive the same request trace")
                raw_runs.append(summary)

    raw_path = output_dir / "raw_results.csv"
    raw_rows = [_csv_safe(row) for row in raw_runs]
    with raw_path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(raw_rows[0].keys()))
        writer.writeheader()
        writer.writerows(raw_rows)

    summary_rows: list[dict] = []
    for workload in config.workloads:
        for strategy in config.strategies:
            group = [
                row
                for row in raw_runs
                if row["workload"] == workload and row["strategy"] == strategy
            ]
            summary_rows.append(aggregate_group(group))

    summary_path = output_dir / "summary.csv"
    csv_rows = [_csv_safe(row) for row in summary_rows]
    with summary_path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(csv_rows[0].keys()))
        writer.writeheader()
        writer.writerows(csv_rows)

    result = {
        "experiment": {
            "strategies": list(config.strategies),
            "workloads": list(config.workloads),
            "seeds": list(config.seeds),
            "request_count": config.request_count,
            "run_count": len(raw_runs),
            "real_vllm_used": False,
        },
        "raw_runs": raw_runs,
        "summary": summary_rows,
    }
    (output_dir / "summary.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print_comparison_table(summary_rows)
    print(f"\nRAW: {raw_path}")
    print(f"SUMMARY CSV: {summary_path}")
    print(f"SUMMARY JSON: {output_dir / 'summary.json'}")
    return result


def main() -> None:
    project_root = Path(__file__).resolve().parents[1]
    run_experiments(project_root / "results")


if __name__ == "__main__":
    main()
