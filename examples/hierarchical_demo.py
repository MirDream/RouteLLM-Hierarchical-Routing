"""Three-model, two-node demonstration of hierarchical resource-aware routing."""

from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from routellm.hierarchical_controller import HierarchicalController, JsonlDecisionLogger
from routellm.config.experiment_config import load_experiment_config
from routellm.monitor.resource_monitor import NodeState, SimulatedResourceMonitor
from routellm.routers.multimodel_router import ModelProfile, MultiModelRouter
from routellm.scheduler.resource_scheduler import ResourceAwareScheduler


def build_demo(log_path: Path) -> HierarchicalController:
    config = load_experiment_config()
    profiles = [
        ModelProfile("model-a", 0.98, 0.95, 20, 400, 0.030, ("proof", "证明", "matrix", "矩阵")),
        ModelProfile("model-b", 0.86, 0.70, 10, 220, 0.010, ("code", "python", "代码", "算法")),
        ModelProfile("model-c", 0.70, 0.45, 6, 120, 0.003, ("summary", "总结")),
    ]
    # model-a ranks first by capability, but cloud is intentionally congested.
    # model-b can also execute on the lightly loaded edge node.
    monitor = SimulatedResourceMonitor(
        [
            NodeState(
                node="cloud",
                available_models=("model-a", "model-b"),
                gpu_utilization=0.95,
                total_vram_gb=80,
                free_vram_gb=20,
                queue_length=8,
                network_latency_ms=80,
                throughput_tokens_per_sec=35,
            ),
            NodeState(
                node="edge-1",
                available_models=("model-b", "model-c"),
                gpu_utilization=0.25,
                total_vram_gb=24,
                free_vram_gb=18,
                queue_length=1,
                network_latency_ms=10,
                throughput_tokens_per_sec=70,
            ),
        ]
    )
    router = MultiModelRouter(profiles)
    scheduler = ResourceAwareScheduler(
        router.models,
        weights=config.utility_weights,
        q_min=config.q_min,
        latency_scale_ms=config.latency_scale_ms,
    )
    return HierarchicalController(
        router=router,
        monitor=monitor,
        scheduler=scheduler,
        top_k=config.top_k,
        decision_logger=JsonlDecisionLogger(log_path),
    )


def main() -> None:
    log_path = PROJECT_ROOT / "demo_output" / "decisions.jsonl"
    if log_path.exists():
        log_path.unlink()
    controller = build_demo(log_path)
    query = "请分析一个包含矩阵运算的 Python 调度算法，并解释复杂度。"
    response = controller.chat.completions.create(
        messages=[{"role": "user", "content": query}],
        temperature=0.0,
    )
    decision = response.routing_decision
    print(json.dumps(decision.to_dict(), ensure_ascii=False, indent=2))
    print(f"\nFINAL: {response.model}@{response.node}")
    print(f"LOG: {log_path}")


if __name__ == "__main__":
    main()
