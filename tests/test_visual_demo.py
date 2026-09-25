from __future__ import annotations

import unittest
from unittest.mock import patch

from visual_demo import (
    HIERARCHICAL_DEFAULT_QUERY,
    run_hierarchical_routing,
    run_official_routing,
)
from routellm.controller import Controller
from routellm.hierarchical_controller import HierarchicalController


class VisualDemoIntegrationTests(unittest.TestCase):
    def test_official_mode_calls_official_controller_and_is_repeatable(self):
        original = Controller.route
        calls = []

        def observed(controller, *args, **kwargs):
            calls.append((args, kwargs))
            return original(controller, *args, **kwargs)

        with patch.object(Controller, "route", observed):
            first = run_official_routing("What is 2 + 2?", threshold=0.60)
        second = run_official_routing("What is 2 + 2?", threshold=0.60)
        self.assertEqual(len(calls), 1)
        self.assertEqual(first, second)
        self.assertIn(first.selected_model, (first.strong_model, first.weak_model))
        self.assertEqual(
            first.selected_tier,
            "Strong Model" if first.routing_score >= first.threshold else "Weak Model",
        )
        self.assertIn("Controller.route", first.call_path)

    def test_hierarchical_mode_calls_real_controller(self):
        original = HierarchicalController.decide
        calls = []

        def observed(controller, query):
            calls.append(query)
            return original(controller, query)

        with patch.object(HierarchicalController, "decide", observed):
            result = run_hierarchical_routing(
                HIERARCHICAL_DEFAULT_QUERY, "Cloud Congestion"
            )
        self.assertEqual(calls, [HIERARCHICAL_DEFAULT_QUERY])
        selected = [
            row
            for row in result.record.final_utility_scores
            if row["model"] == result.record.selected_model
            and row["node"] == result.record.selected_node
        ]
        self.assertEqual(len(selected), 1)

    def test_scenarios_change_real_scheduler_decision(self):
        low = run_hierarchical_routing(HIERARCHICAL_DEFAULT_QUERY, "Low Load")
        cloud_busy = run_hierarchical_routing(
            HIERARCHICAL_DEFAULT_QUERY, "Cloud Congestion"
        )
        edge_busy = run_hierarchical_routing(
            HIERARCHICAL_DEFAULT_QUERY, "Edge Congestion"
        )
        self.assertEqual((low.record.selected_model, low.record.selected_node), ("model-a", "cloud"))
        self.assertEqual(
            (cloud_busy.record.selected_model, cloud_busy.record.selected_node),
            ("model-b", "edge-1"),
        )
        self.assertEqual(
            (edge_busy.record.selected_model, edge_busy.record.selected_node),
            ("model-a", "cloud"),
        )

    def test_rankings_respond_to_query_and_keep_true_top_k(self):
        first = run_hierarchical_routing(HIERARCHICAL_DEFAULT_QUERY, "Low Load")
        second = run_hierarchical_routing(
            "Review this Python function and explain the algorithm.", "Low Load"
        )
        first_scores = [item.predicted_quality for item in first.all_candidates]
        second_scores = [item.predicted_quality for item in second.all_candidates]
        self.assertNotEqual(first_scores, second_scores)
        self.assertEqual(
            [item["model"] for item in first.record.top_k_candidates],
            [item.model for item in first.all_candidates[:2]],
        )

    def test_quality_fallback_status_comes_from_scheduler(self):
        result = run_hierarchical_routing(
            HIERARCHICAL_DEFAULT_QUERY,
            "Cloud Congestion",
            q_min=0.99,
        )
        self.assertTrue(result.record.quality_fallback)
        self.assertEqual(result.record.quality_threshold, 0.99)

    def test_selected_utility_matches_scheduler_maximum(self):
        result = run_hierarchical_routing(
            HIERARCHICAL_DEFAULT_QUERY, "Cloud Congestion"
        )
        eligible = [
            row
            for row in result.record.final_utility_scores
            if row["meets_quality_constraint"]
        ]
        best = max(eligible, key=lambda row: row["utility"])
        self.assertEqual(
            (best["model"], best["node"]),
            (result.record.selected_model, result.record.selected_node),
        )


if __name__ == "__main__":
    unittest.main()
