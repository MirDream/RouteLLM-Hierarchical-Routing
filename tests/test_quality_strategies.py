from __future__ import annotations

import unittest

from routellm.config.experiment_config import load_experiment_config
from routellm.monitor.resource_monitor import NodeState
from routellm.routers.multimodel_router import CapabilityCandidate, MultiModelRouter
from routellm.scheduler.resource_scheduler import ResourceAwareScheduler
from routellm.strategies import build_strategy
from simulation.simulator import build_profiles, simulate
from simulation.workload import build_request_trace, trace_fingerprint


class QualityAndStrategyTests(unittest.TestCase):
    def setUp(self):
        self.config = load_experiment_config()
        self.profiles = build_profiles()
        self.router = MultiModelRouter(self.profiles)
        self.scheduler = ResourceAwareScheduler(
            self.router.models,
            weights=self.config.utility_weights,
            q_min=self.config.q_min,
            latency_scale_ms=self.config.latency_scale_ms,
        )

    def test_quality_constraint_filters_low_quality_model(self):
        candidates = [
            CapabilityCandidate("model-a", predicted_quality=0.82, rank=1),
            CapabilityCandidate("model-b", predicted_quality=0.62, rank=2),
        ]
        states = {
            "cloud": NodeState("cloud", ("model-a",), 0.95, 80, 20, 8, 80, 35),
            "edge-1": NodeState("edge-1", ("model-b",), 0.05, 24, 20, 0, 5, 100),
        }
        decision = self.scheduler.schedule(candidates, states)
        self.assertEqual(decision.selected_model, "model-a")
        self.assertFalse(decision.quality_fallback)

    def test_quality_fallback_selects_highest_prediction(self):
        candidates = [
            CapabilityCandidate("model-a", predicted_quality=0.68, rank=1),
            CapabilityCandidate("model-b", predicted_quality=0.62, rank=2),
        ]
        states = {
            "cloud": NodeState("cloud", ("model-a",), 0.8, 80, 20, 5, 70, 40),
            "edge-1": NodeState("edge-1", ("model-b",), 0.1, 24, 20, 0, 5, 100),
        }
        decision = self.scheduler.schedule(candidates, states)
        self.assertTrue(decision.quality_fallback)
        self.assertEqual(decision.selected_model, "model-a")

    def test_idle_cloud_restores_high_quality_model(self):
        strategy = build_strategy("hierarchical", self.router, self.scheduler, self.config)
        states = {
            "cloud": NodeState("cloud", ("model-a", "model-b"), 0.08, 80, 60, 0, 20, 100),
            "edge-1": NodeState("edge-1", ("model-b", "model-c"), 0.85, 24, 10, 7, 10, 35),
        }
        decision = strategy.decide("Prove a matrix scheduling invariant.", states, seed=1)
        self.assertEqual((decision.selected_model, decision.selected_node), ("model-a", "cloud"))

    def test_resource_only_can_select_low_quality_model(self):
        strategy = build_strategy("resource_only", self.router, self.scheduler, self.config)
        states = {
            "cloud": NodeState("cloud", ("model-a", "model-b"), 0.95, 80, 20, 9, 80, 30),
            "edge-1": NodeState("edge-1", ("model-b", "model-c"), 0.05, 24, 20, 0, 5, 110),
        }
        query = "Prove a matrix scheduling invariant and explain each step."
        decision = strategy.decide(query, states, seed=2)
        actual = self.router.actual_quality(query, decision.selected_model)
        self.assertEqual(decision.selected_node, "edge-1")
        self.assertLess(actual, self.config.q_min)

    def test_hierarchical_never_selects_unsupported_node(self):
        strategy = build_strategy("hierarchical", self.router, self.scheduler, self.config)
        states = {
            "cloud": NodeState("cloud", ("model-b",), 0.3, 80, 60, 0, 20, 90),
            "edge-1": NodeState("edge-1", ("model-c",), 0.1, 24, 20, 0, 5, 100),
        }
        decision = strategy.decide("Review Python code.", states, seed=3)
        self.assertIn(decision.selected_model, states[decision.selected_node].available_models)

    def test_predicted_quality_is_imperfect_but_reproducible(self):
        query = "Review Python code and prove a matrix invariant."
        candidates_a = self.router.rank(query, top_k=3, seed=4)
        candidates_b = self.router.rank(query, top_k=3, seed=4)
        self.assertEqual(candidates_a, candidates_b)
        self.assertTrue(
            any(
                candidate.predicted_quality
                != self.router.actual_quality(query, candidate.model)
                for candidate in candidates_a
            )
        )

    def test_same_seed_repeats_exactly(self):
        trace = build_request_trace(self.config, "medium_load", seed=5, count=40)
        records_a, summary_a = simulate(
            "hierarchical", "medium_load", 5, trace, self.config
        )
        records_b, summary_b = simulate(
            "hierarchical", "medium_load", 5, trace, self.config
        )
        self.assertEqual(records_a, records_b)
        self.assertEqual(summary_a, summary_b)

    def test_four_strategies_share_identical_trace(self):
        trace = build_request_trace(self.config, "high_load", seed=1, count=30)
        expected = trace_fingerprint(trace)
        fingerprints = set()
        for name in self.config.strategies:
            records, summary = simulate(name, "high_load", 1, trace, self.config)
            fingerprints.add(summary["trace_fingerprint"])
            self.assertTrue(all(record.trace_fingerprint == expected for record in records))
        self.assertEqual(fingerprints, {expected})


if __name__ == "__main__":
    unittest.main()
