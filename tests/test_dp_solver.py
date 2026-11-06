import itertools
import json
import unittest
from unittest.mock import patch
import httpx

from ai_lens.dp_solver import solve_dp, render_dp
from ai_lens.solver_engine import TreeOutputGate
from ai_lens.vision_engine import EphemeralAlgorithmicAccelerator, VisionInferenceWorker


def request(weights, capacity, meaning="last_weight", policy="first", tail=5):
    params = {"weights": weights, "capacity": capacity, "cell_meaning": meaning, "tail_count": tail}
    if meaning.startswith("last_"):
        params["update_policy"] = policy
    return {"algorithm": "KNAPSACK_01_TABLE", "params": params}


class DPTests(unittest.TestCase):
    def test_user_example_first_weight(self):
        r = solve_dp(request([7, 4, 5, 9, 2], 17))
        self.assertEqual(r["status"], "ok")
        self.assertEqual(r["result"]["last_k"], [9, 9, 2, 5, 0])
        self.assertEqual(r["result"]["indices"], [13, 14, 15, 16, 17])
        self.assertFalse(r["result"]["reachable_target"])

    def test_user_example_max_weight_is_different_not_arithmetic_error(self):
        r = solve_dp(request([7, 4, 5, 9, 2], 17, "max_weight"))
        self.assertEqual(r["result"]["dp"], [
            0, 0, 2, 2, 4, 5, 6, 7, 7, 9, 9, 11, 12, 13, 14, 15, 16, 16])
        self.assertEqual(r["result"]["last_k"], [13, 14, 15, 16, 16])

    def test_user_example_other_meanings(self):
        weights = [7, 4, 5, 9, 2]
        r = solve_dp(request(weights, 17, "last_weight", "overwrite"))
        self.assertEqual(r["result"]["last_k"], [2, 2, 2, 2, 0])
        r = solve_dp(request(weights, 17, "reachable"))
        self.assertEqual(r["result"]["last_k"], [True, True, True, True, False])
        r = solve_dp(request(weights, 17, "last_item_index"))
        self.assertEqual(r["result"]["last_k"], [4, 4, 5, 3, 0])

    def test_no_implicit_meaning(self):
        r = request([1, 2], 3, tail=2)
        del r["params"]["cell_meaning"]
        self.assertEqual(solve_dp(r)["status"], "invalid_input")

    def test_no_implicit_update_policy(self):
        r = request([1, 2], 3, tail=2)
        del r["params"]["update_policy"]
        self.assertEqual(solve_dp(r)["status"], "invalid_input")

    def test_item_not_reused(self):
        r = solve_dp(request([2], 4, "max_weight"))
        self.assertEqual(r["result"]["dp"], [0, 0, 2, 2, 2])
        self.assertFalse(r["result"]["reachable_target"])

    def test_duplicates_are_distinct_items(self):
        r = solve_dp(request([2, 2], 4, "max_weight"))
        self.assertEqual(r["result"]["dp"], [0, 0, 2, 2, 4])

    def test_order_preserved(self):
        a = solve_dp(request([2, 3, 5], 5))["result"]
        b = solve_dp(request([5, 3, 2], 5))["result"]
        self.assertEqual(a["dp"][5], 3)
        self.assertEqual(b["dp"][5], 5)

    def test_invalid_types_and_limits(self):
        for weights, capacity, tail in [
            ([True], 4, 5), ([1.5], 4, 5), ([0], 4, 5), ([-1], 4, 5),
            ([1], True, 1), ([1], 2.5, 1), ([1], -1, 1), ([1], 3, 5), ([1], 3, 0),
        ]:
            self.assertEqual(solve_dp(request(weights, capacity, tail=tail))["status"], "invalid_input")
        for weights, capacity in [([1], 10001), ([1] * 257, 4), ([1] * 256, 10000)]:
            self.assertEqual(solve_dp(request(weights, capacity, tail=1))["status"], "resource_limit")

    def test_empty_and_zero_capacity(self):
        self.assertEqual(solve_dp(request([], 0, "reachable", tail=1))["result"]["last_k"], [True])
        self.assertEqual(solve_dp(request([], 0, "max_weight", tail=1))["result"]["last_k"], [0])
        self.assertEqual(solve_dp(request([], 0, tail=1))["result"]["last_k"], [0])

    def test_large_item_not_allocated_or_clamped(self):
        r = solve_dp(request([10**100, 2], 4, "max_weight"))
        self.assertEqual(r["result"]["dp"], [0, 0, 2, 2, 2])

    def test_unknown_params_rejected(self):
        r = request([1], 1, tail=1)
        r["params"]["profits"] = [42]
        self.assertEqual(solve_dp(r)["status"], "invalid_input")

    def test_exhaustive_against_subsets_and_2d_reference(self):
        count = 0
        for n in range(5):
            for weights in itertools.product(range(1, 5), repeat=n):
                weights = list(weights)
                sums = {sum(weights[i] for i in range(n) if mask & (1 << i))
                        for mask in range(1 << n)}
                for capacity in range(13):
                    tail = min(5, capacity + 1)
                    for meaning in ("max_weight", "reachable", "last_weight", "last_item_index"):
                        for policy in (("first", "overwrite") if meaning.startswith("last_") else ("first",)):
                            r = solve_dp(request(weights, capacity, meaning, policy, tail))
                            self.assertEqual(r["status"], "ok")
                            if meaning == "max_weight":
                                ref = [max(s for s in sums if s <= c) for c in range(capacity + 1)]
                            elif meaning == "reachable":
                                ref = [c in sums for c in range(capacity + 1)]
                            else:
                                rows = [[0] * (capacity + 1)]
                                attainable = [{0}]
                                for index, w in enumerate(weights, 1):
                                    row, previous = rows[-1].copy(), attainable[-1]
                                    for c in range(w, capacity + 1):
                                        if c - w in previous and (policy == "overwrite" or c not in previous):
                                            row[c] = w if meaning == "last_weight" else index
                                    rows.append(row)
                                    attainable.append(previous | {s + w for s in previous if s + w <= capacity})
                                ref = rows[-1]
                            self.assertEqual(r["result"]["dp"], ref)
                            count += 1
        self.assertEqual(count, 26598)

    def test_short_render_does_not_emit_full_row(self):
        r = solve_dp(request([7, 4, 5, 9, 2], 17))
        text = render_dp(r)
        self.assertIn("[9, 9, 2, 5, 0]", text)
        self.assertNotIn(str(r["result"]["dp"]), text)
        self.assertLess(len(text), 200)

    def test_marker_all_splits(self):
        text = "@SOLVER_REQUEST" + json.dumps(request([7, 4, 5, 9, 2], 17))
        for pos in range(len(text) + 1):
            output = []
            gate = TreeOutputGate(output.append)
            gate.push(text[:pos])
            gate.push(text[pos:])
            self.assertEqual(output, [])
            gate.finish()
            self.assertIn("[9, 9, 2, 5, 0]", "".join(output))

    def test_legacy_dp_semantics_unchanged(self):
        a = EphemeralAlgorithmicAccelerator()
        try:
            r = a.table_state_transition_1d([7, 4, 5, 9, 2], 17)
            self.assertEqual(r["last_k"], [9, 9, 2, 5, 0])
            with self.assertRaises(ValueError):
                a.table_state_transition_1d([1], 10001)
        finally:
            a.clear()

    def test_dispatch_explicit_meaning(self):
        a = EphemeralAlgorithmicAccelerator()
        try:
            r = a.synthesize_and_execute_algorithm("KNAPSACK_01_TABLE",
                request([7, 4, 5, 9, 2], 17, "max_weight")["params"])
            self.assertEqual(r["result"]["last_k"], [13, 14, 15, 16, 16])
        finally:
            a.clear()

    def test_dp_request_through_worker_without_second_model_call(self):
        text = "@SOLVER_REQUEST" + json.dumps(request([7, 4, 5, 9, 2], 17))
        events = [
            {"candidates": [{"content": {"parts": [{"text": text}]}}]},
            {"candidates": [{"finishReason": "STOP"}]},
        ]
        body = "\n\n".join("data: " + json.dumps(e) for e in events)
        calls, tokens = [], []
        def handler(req):
            calls.append(req)
            return httpx.Response(200, text=body)
        worker = VisionInferenceWorker(None, "", model="gemini-3.5-flash", language="cs")
        worker.tokenReceived.connect(tokens.append)
        try:
            with httpx.Client(transport=httpx.MockTransport(handler)) as client:
                with patch("ai_lens.vision_engine._pace_gemini_request"):
                    outcome = worker._stream_gemini_chat(client, "https://test.invalid", {},
                                                         {"tools": [{"codeExecution": {}}]})
            self.assertTrue(outcome[0])
            self.assertEqual(len(calls), 1)
            self.assertIn("[9, 9, 2, 5, 0]", "".join(tokens))
            self.assertFalse(worker._code_execution_used)
            self.assertEqual(worker.thinking_level, "high")
        finally:
            worker.clear_memory()


if __name__ == "__main__":
    unittest.main()
