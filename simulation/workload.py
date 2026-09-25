"""Reproducible request traces for low, medium and high load scenarios."""

from __future__ import annotations

import hashlib
import json
import random
from dataclasses import asdict, dataclass

from routellm.config.experiment_config import ExperimentConfig


@dataclass(frozen=True)
class WorkloadItem:
    request_id: int
    arrival_gap_s: float
    workload: str
    query_type: str
    query: str
    output_tokens: int
    latency_jitter: float


QUERIES = (
    ("simple", "Explain why the sky appears blue."),
    ("simple", "Give three practical tips for organizing study notes."),
    ("code", "Review this Python scheduling code and identify complexity bottlenecks."),
    ("code", "Write a Python function for queue scheduling and explain its complexity."),
    ("reasoning", "Prove a matrix scheduling invariant and explain each step."),
    ("reasoning", "Solve a constrained allocation problem using equations and justify the result."),
    ("summary", "Summarize a short deployment incident report."),
    ("summary", "总结这段系统运行日志，并指出最可能的拥塞原因。"),
)


def _stable_rng_seed(seed: int, workload: str) -> int:
    digest = hashlib.sha256(f"{seed}|{workload}".encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big")


def build_request_trace(
    config: ExperimentConfig,
    workload: str,
    seed: int,
    count: int | None = None,
) -> list[WorkloadItem]:
    if workload not in config.workloads:
        raise ValueError(f"Unknown workload: {workload}")
    request_count = count if count is not None else config.request_count
    low, high = config.workloads[workload]
    rng = random.Random(_stable_rng_seed(seed, workload))
    items: list[WorkloadItem] = []
    for request_id in range(request_count):
        query_type, query = QUERIES[rng.randrange(len(QUERIES))]
        items.append(
            WorkloadItem(
                request_id=request_id,
                arrival_gap_s=round(rng.uniform(low, high), 9),
                workload=workload,
                query_type=query_type,
                query=query,
                output_tokens=rng.randint(120, 260),
                latency_jitter=round(rng.uniform(0.94, 1.08), 9),
            )
        )
    return items


def trace_fingerprint(items: list[WorkloadItem]) -> str:
    payload = json.dumps(
        [asdict(item) for item in items],
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
