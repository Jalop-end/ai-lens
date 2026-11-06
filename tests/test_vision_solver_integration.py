"""Integration tests for isolated solver rerouting in AI Lens vision_engine."""
import json
import os
import tempfile
import time
import unittest

from ai_lens.vision_engine import (
    EphemeralAlgorithmicAccelerator,
    _extract_algo_tags_balanced,
    _extract_conclusion_from_thought,
    get_shared_solver_service,
    close_shared_solver_service,
)
from ai_lens.isolated_solver import Limits, SolverService, solve, LatestOnly


class VisionSolverIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.accel = EphemeralAlgorithmicAccelerator()

    def tearDown(self):
        self.accel.clear()

    def test_dijkstra_routing(self):
        spec = "@ALGO[DIJKSTRA | n=4, source=0, edges=[[0,1,4],[0,2,1],[2,1,2],[1,3,1],[2,3,5]]]"
        res = self.accel.synthesize_and_execute_algorithm(spec)
        self.assertEqual(res["algorithm"], "DIJKSTRA")
        self.assertTrue(res["mc_verified"])
        self.assertEqual(res["result"]["distances"], [0, 3, 1, 4])
        self.assertEqual(res["result"]["parents"], [None, 2, 0, 1])

    def test_bfs_routing(self):
        spec = "@ALGO[BFS | n=4, source=0, edges=[[0,1],[1,2]]]"
        res = self.accel.synthesize_and_execute_algorithm(spec)
        self.assertEqual(res["algorithm"], "BFS")
        self.assertTrue(res["mc_verified"])
        self.assertEqual(res["result"]["distances"], [0, 1, 2, None])

    def test_bellman_ford_routing(self):
        spec = "@ALGO[BELLMAN_FORD | n=3, source=0, edges=[[0,1,4],[0,2,8],[1,2,-2]]]"
        res = self.accel.synthesize_and_execute_algorithm(spec)
        self.assertEqual(res["algorithm"], "BELLMAN_FORD")
        self.assertTrue(res["mc_verified"])
        self.assertEqual(res["result"]["distances"], [0, 4, 2])

    def test_dfs_routing(self):
        spec = "@ALGO[DFS | n=4, source=0, edges=[[0,1],[1,2],[0,2]]]"
        res = self.accel.synthesize_and_execute_algorithm(spec)
        self.assertEqual(res["algorithm"], "DFS")
        self.assertTrue(res["mc_verified"])
        self.assertEqual(res["result"]["discovery_order"], [0, 1, 2])
        self.assertEqual(res["result"]["finish_order"], [2, 1, 0])

    def test_topological_sort_routing(self):
        spec = "@ALGO[TOPOLOGICAL_SORT | n=4, edges=[[0,2],[1,2],[2,3]]]"
        res = self.accel.synthesize_and_execute_algorithm(spec)
        self.assertEqual(res["algorithm"], "TOPOLOGICAL_SORT")
        self.assertTrue(res["mc_verified"])
        self.assertEqual(res["result"]["order"], [0, 1, 2, 3])

    def test_negative_cycle_rejection(self):
        spec = "@ALGO[BELLMAN_FORD | n=2, source=0, edges=[[0,1,-1],[1,0,0]]]"
        res = self.accel.synthesize_and_execute_algorithm(spec)
        self.assertEqual(res["status"], "NEGATIVE_CYCLE")
        self.assertIsNone(res["result"])
        self.assertFalse(res["mc_verified"])

    def test_negative_dijkstra_rejection(self):
        spec = "@ALGO[DIJKSTRA | n=2, source=0, edges=[[0,1,-1]]]"
        res = self.accel.synthesize_and_execute_algorithm(spec)
        self.assertEqual(res["status"], "INVALID_INPUT")
        self.assertIsNone(res["result"])
        self.assertFalse(res["mc_verified"])

    def test_topological_cycle_rejection(self):
        spec = "@ALGO[TOPOLOGICAL_SORT | n=2, edges=[[0,1],[1,0]]]"
        res = self.accel.synthesize_and_execute_algorithm(spec)
        self.assertEqual(res["status"], "CYCLE_DETECTED")
        self.assertIsNone(res["result"])
        self.assertFalse(res["mc_verified"])

    def test_nested_brackets_tag_extraction(self):
        text = "Thinking... @ALGO[DIJKSTRA | n=4, source=0, edges=[[0,1,4],[0,2,1],[2,1,2]]] done."
        tags = _extract_algo_tags_balanced(text)
        self.assertEqual(len(tags), 1)
        full, inner = tags[0]
        self.assertTrue(full.startswith("@ALGO["))
        self.assertTrue(full.endswith("]"))
        self.assertIn("edges=[[0,1,4],[0,2,1],[2,1,2]]", inner)

    def test_inspect_and_accelerate_text(self):
        text = "Graph exploration: @ALGO[DIJKSTRA | n=4, source=0, edges=[[0,1,4],[0,2,1],[2,1,2],[1,3,1],[2,3,5]]] finished."
        out = self.accel.inspect_and_accelerate_text(text)
        self.assertIsNotNone(out)
        self.assertIn("ALGO[DIJKSTRA]", out)
        self.assertIn("distances=[0, 3, 1, 4]", out)

    def test_json_payload_inspection(self):
        payload = {
            "schema_version": 1,
            "algorithm": "BFS",
            "params": {"n": 3, "edges": [[0, 1], [1, 2]], "source": 0},
        }
        text = f"We have structured request: {json.dumps(payload)} to evaluate."
        out = self.accel.inspect_and_accelerate_text(text)
        self.assertIsNotNone(out)
        self.assertIn("SOLVER[BFS]", out)

    def test_floyd_warshall_rerouted(self):
        adj = [
            [0.0, 4.0, 1.0, float("inf")],
            [float("inf"), 0.0, float("inf"), 1.0],
            [float("inf"), 2.0, 0.0, 5.0],
            [float("inf"), float("inf"), float("inf"), 0.0],
        ]
        fw = self.accel.solve_and_verify_graph_floyd_warshall(adj)
        self.assertEqual(fw["distances"][0], [0, 3, 1, 4])
        self.assertTrue(fw["mc_verified"])

    def test_floyd_warshall_preserves_fractional_weights(self):
        adj = [
            [0.0, 1.5, float("inf")],
            [float("inf"), 0.0, 2.25],
            [float("inf"), float("inf"), 0.0],
        ]
        fw = self.accel.solve_and_verify_graph_floyd_warshall(adj)
        self.assertEqual(fw["distances"][0][2], 3.75)

    def test_zero_disk_persistence(self):
        """Verifies that running solve does not create temporary files or directories in tempdir."""
        temp_dir = tempfile.gettempdir()
        initial_entries = set(os.listdir(temp_dir))
        req = {
            "schema_version": 1,
            "request_id": "test_zero_disk",
            "algorithm": "BFS",
            "params": {"n": 3, "edges": [[0, 1], [1, 2]], "source": 0},
        }
        ans = solve(req, limits=Limits(require_memory=False))
        self.assertEqual(ans["status"], "OK")
        current_entries = set(os.listdir(temp_dir))
        new_entries = [e for e in (current_entries - initial_entries) if e.startswith("solver-p1")]
        self.assertEqual(new_entries, [], "Expected zero temporary files on disk from solver execution")


if __name__ == "__main__":
    unittest.main()
