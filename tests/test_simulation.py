from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from simulation.static_vs_dynamic import run


class SimulationTests(unittest.TestCase):
    def test_dynamic_router_improves_burst_workload(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = run(Path(tmp), count=300, seed=20260924)
            self.assertEqual(result["static"]["requests"], 300)
            self.assertEqual(result["dynamic"]["requests"], 300)
            self.assertLess(
                result["dynamic"]["mean_latency_ms"], result["static"]["mean_latency_ms"]
            )
            self.assertLess(
                result["dynamic"]["p95_latency_ms"], result["static"]["p95_latency_ms"]
            )
            self.assertLess(
                result["dynamic"]["peak_cloud_queue"], result["static"]["peak_cloud_queue"]
            )
            self.assertIn("edge-1", result["dynamic"]["node_selections"])
            self.assertTrue((Path(tmp) / "summary.json").exists())
            self.assertTrue((Path(tmp) / "requests.csv").exists())

