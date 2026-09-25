from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from examples.hierarchical_demo import build_demo
from routellm.monitor.resource_monitor import NodeState, SimulatedResourceMonitor
from routellm.routers.multimodel_router import ModelProfile, MultiModelRouter
from routellm.scheduler.resource_scheduler import ResourceAwareScheduler


class HierarchicalRouterTests(unittest.TestCase):
    def setUp(self):
        self.profiles = [
            ModelProfile("a", 0.98, 0.95, 20, 400, 0.030),
            ModelProfile("b", 0.86, 0.70, 10, 220, 0.010),
            ModelProfile("c", 0.70, 0.45, 6, 120, 0.003),
        ]

    def test_router_returns_sorted_top_k(self):
        router = MultiModelRouter(self.profiles)
        candidates = router.rank("Explain a moderately complex scheduling algorithm", top_k=2)
        self.assertEqual([item.model for item in candidates], ["a", "b"])
        self.assertGreaterEqual(candidates[0].score, candidates[1].score)

    def test_busy_first_model_causes_second_candidate_to_win(self):
        router = MultiModelRouter(self.profiles)
        candidates = router.rank("Explain a scheduling algorithm", top_k=2)
        monitor = SimulatedResourceMonitor(
            [
                NodeState("cloud", ("a", "b"), 0.95, 80, 20, 8, 80, 35),
                NodeState("edge", ("b", "c"), 0.25, 24, 18, 1, 10, 70),
            ]
        )
        decision = ResourceAwareScheduler(router.models).schedule(candidates, monitor.snapshot())
        self.assertEqual((decision.selected_model, decision.selected_node), ("b", "edge"))

    def test_insufficient_vram_filters_pair(self):
        router = MultiModelRouter(self.profiles)
        candidates = router.rank("Hard reasoning task", top_k=1)
        monitor = SimulatedResourceMonitor(
            [NodeState("small", ("a",), 0.1, 16, 16, 0, 5, 80)]
        )
        with self.assertRaisesRegex(RuntimeError, "No feasible"):
            ResourceAwareScheduler(router.models).schedule(candidates, monitor.snapshot())

    def test_controller_logs_required_decision_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "decisions.jsonl"
            controller = build_demo(log_path)
            response = controller.chat.completions.create(
                messages=[{"role": "user", "content": "Explain matrix scheduling code"}]
            )
            self.assertEqual((response.model, response.node), ("model-b", "edge-1"))
            record = json.loads(log_path.read_text(encoding="utf-8").strip())
            required = {
                "query",
                "capability_scores",
                "resource_states",
                "final_utility_scores",
                "selected_model",
                "selected_node",
            }
            self.assertTrue(required.issubset(record))


if __name__ == "__main__":
    unittest.main()

