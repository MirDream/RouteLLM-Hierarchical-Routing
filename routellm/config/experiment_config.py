"""Typed loader for deterministic routing experiments."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from routellm.scheduler.scoring import UtilityWeights


@dataclass(frozen=True)
class AblationConfig:
    use_quality_constraint: bool = True
    use_resource_awareness: bool = True
    use_cost: bool = True
    use_topk: bool = True


@dataclass(frozen=True)
class ExperimentConfig:
    top_k: int
    q_min: float
    utility_weights: UtilityWeights
    latency_scale_ms: float
    ablation: AblationConfig
    seeds: tuple[int, ...]
    request_count: int
    sla_ms: float
    strategies: tuple[str, ...]
    workloads: dict[str, tuple[float, float]]
    service_rates: dict[str, float]
    default_nodes: dict[str, str]


def default_config_path() -> Path:
    return Path(__file__).resolve().parents[2] / "configs" / "experiment_config.json"


def load_experiment_config(path: str | Path | None = None) -> ExperimentConfig:
    source = Path(path) if path else default_config_path()
    data = json.loads(source.read_text(encoding="utf-8"))
    weights = data["utility_weights"]
    ablation = data["ablation"]
    experiment = data["experiment"]
    nodes = data["nodes"]
    workloads = {
        name: tuple(float(value) for value in item["arrival_gap_s"])
        for name, item in experiment["workloads"].items()
    }
    return ExperimentConfig(
        top_k=int(data["top_k"]),
        q_min=float(data["q_min"]),
        utility_weights=UtilityWeights(**weights),
        latency_scale_ms=float(data["normalization"]["latency_scale_ms"]),
        ablation=AblationConfig(**ablation),
        seeds=tuple(int(seed) for seed in experiment["seeds"]),
        request_count=int(experiment["request_count"]),
        sla_ms=float(experiment["sla_ms"]),
        strategies=tuple(experiment["strategies"]),
        workloads=workloads,
        service_rates={name: float(value) for name, value in nodes["service_rates"].items()},
        default_nodes=dict(nodes["default_nodes"]),
    )
