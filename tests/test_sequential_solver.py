"""Deterministic reference tests, parser boundaries and mocked live stream path."""
import itertools
import json
import random
import time
import unittest
from unittest.mock import patch

import httpx

from ai_lens.solver_engine import (
    MARKER, MAX_VALUES, MAX_REQUEST_CHARS, SOLVER_INSTRUCTION,
    TreeOutputGate, parse_legacy_params, solve_tree, strict_json,
)
from ai_lens.vision_engine import EphemeralAlgorithmicAccelerator, VisionInferenceWorker


def request(values, algorithm="BST_INSERT", **kw):
    return {"algorithm": algorithm, "params": {
        "values": values, "duplicate_policy": "reject", **kw}}


def reference_bst(values, duplicate="reject"):
    """Separate nested-tuple implementation for small reference cases."""
    def add(t, x):
        if t is None:
            return (x, None, None)
        key, left, right = t
        if x == key and duplicate == "ignore":
            return t
        if x < key or (x == key and duplicate == "left"):
            return (key, add(left, x), right)
        return (key, left, add(right, x))
    def traversal(t, mode):
        if t is None:
            return []
        key, left, right = t
        a, b = traversal(left, mode), traversal(right, mode)
        return {"preorder": [key] + a + b, "inorder": a + [key] + b,
                "postorder": a + b + [key]}[mode]
    tree = None
    for value in values:
        tree = add(tree, value)
    return {name: traversal(tree, name) for name in ("preorder", "inorder", "postorder")}


class SequentialTrees(unittest.TestCase):
    def test_bst_preserves_order(self):
        for values, root in (([1, 2, 3], 1), ([3, 2, 1], 3), ([2, 1, 3], 2)):
            answer = solve_tree(request(values))
            self.assertEqual(answer["result"]["root"], root)
            self.assertEqual(answer["result"]["input_order"], values)

    def test_all_permutations_up_to_seven(self):
        count = 0
        for n in range(8):
            for values in itertools.permutations(range(n)):
                values = list(values)
                actual = solve_tree(request(values))
                self.assertEqual(actual["status"], "ok")
                expected = reference_bst(values)
                for key in expected:
                    self.assertEqual(actual["result"][key], expected[key])
                count += 1
        self.assertEqual(count, 5914)

    def test_duplicate_policies(self):
        rng = random.Random(12489)
        for policy in ("left", "right", "ignore"):
            for _ in range(100):
                values = [rng.randrange(-4, 5) for _ in range(20)]
                result = solve_tree(request(values, duplicate_policy=policy))
                self.assertEqual(result["status"], "ok")
                for k, expected in reference_bst(values, policy).items():
                    self.assertEqual(result["result"][k], expected)

    def test_duplicates_rejected(self):
        self.assertEqual(solve_tree(request([1, 1]))["status"], "invalid_input")

    def test_policy_must_be_explicit(self):
        self.assertEqual(solve_tree({"algorithm": "BST_INSERT", "params": {"values": [1]}})["status"],
                         "invalid_input")

    def test_empty_tree(self):
        r = solve_tree(request([]))["result"]
        self.assertIsNone(r["root"])
        self.assertEqual(r["height_edges"], -1)

    def test_limit_without_truncation(self):
        self.assertEqual(solve_tree(request(list(range(MAX_VALUES + 1))))["status"], "resource_limit")
        result = solve_tree(request(list(range(MAX_VALUES))))["result"]
        self.assertEqual(result["height_edges"], MAX_VALUES - 1)

    def test_exact_large_negative_keys(self):
        self.assertEqual(solve_tree(request([-10**100, 0, 10**100]))["status"], "ok")

    def test_no_float_bool_string_keys(self):
        for values in ([1.5], [True], ["1"], [float("nan")]):
            self.assertEqual(solve_tree(request(values))["status"], "invalid_input")

    def test_unknown_operation(self):
        for name in ("AVL_INSERT", "BINARY_TREE", "SORT", "", [], None):
            self.assertEqual(solve_tree({"algorithm": name, "params": {}})["status"], "unsupported")

    def test_nonempty_initial_state_rejected(self):
        self.assertEqual(solve_tree(request([1], initial_tree={"root": 3}))["status"], "invalid_input")

    def test_btree_order(self):
        for values, root in (([4, 3, 2, 1], [3]), ([1, 2, 3, 4], [2])):
            result = solve_tree(request(values, "BTREE_INSERT", max_keys=2, split_median="lower"))
            self.assertEqual(result["status"], "ok")
            self.assertEqual(result["result"]["root"], root)

    def test_btree_median(self):
        for median, root in (("lower", [2]), ("upper", [3])):
            result = solve_tree(request([1, 2, 3, 4], "BTREE_INSERT", max_keys=3, split_median=median))
            self.assertEqual(result["result"]["root"], root)

    def test_btree_requires_conventions(self):
        for kw in ({}, {"max_keys": 3}, {"max_keys": 1, "split_median": "lower"},
                   {"max_keys": True, "split_median": "upper"}):
            self.assertEqual(solve_tree(request([1], "BTREE_INSERT", **kw))["status"], "invalid_input")

    def test_btree_random_invariants(self):
        rng = random.Random(372)
        for capacity in range(2, 10):
            for median in ("lower", "upper"):
                for _ in range(30):
                    values = rng.sample(range(-200, 200), 80)
                    r = solve_tree(request(values, "BTREE_INSERT", max_keys=capacity, split_median=median))
                    self.assertEqual(r["status"], "ok")
                    flat = [k for level in r["result"]["levels"] for node in level for k in node]
                    self.assertEqual(sorted(flat), sorted(values))
                    self.assertTrue(all(len(node) <= capacity for level in r["result"]["levels"] for node in level))


class ParsingAndDispatch(unittest.TestCase):
    def setUp(self):
        self.accel = EphemeralAlgorithmicAccelerator()

    def tearDown(self):
        self.accel.clear()

    def test_bst_alias_not_eytzinger(self):
        r = self.accel.synthesize_and_execute_algorithm("@ALGO[BST | X=[3,2,1]]")
        self.assertEqual(r["algorithm"], "BST_INSERT")
        self.assertEqual(r["result"]["root"], 3)

    def test_eytzinger_remains_explicit(self):
        r = self.accel.synthesize_and_execute_algorithm("EYTZINGER_BUILD", {"x": [3, 2, 1]})
        self.assertEqual(r["result"]["root"], 2)

    def test_btree_ambiguous_alias_refused(self):
        for name in ("BTREE", "BINARY_TREE", "IMPLICIT_BTREE"):
            r = self.accel.synthesize_and_execute_algorithm(name, {"x": [3, 2, 1]})
            self.assertEqual(r["status"], "unsupported")
            self.assertFalse(r["mc_verified"])

    def test_unknown_not_sort(self):
        for name in ("AVL_INSERT", "NOT_AN_ALGORITHM", "KMP"):
            r = self.accel.synthesize_and_execute_algorithm(name, {"x": [3, 1, 2]})
            self.assertEqual(r["status"], "unsupported")

    def test_no_numeric_heuristic(self):
        self.assertIsNone(self.accel.inspect_and_accelerate_text(
            "Do prazdneho BST vkladame postupne 1, 2, 3. Jaky je koren?"))

    def test_failed_requests_not_verified(self):
        self.assertIsNone(self.accel.inspect_and_accelerate_text("@ALGO[UNKNOWN | X=[1,2,3]]"))
        self.assertEqual(self.accel.latest_verified_conclusion, "")

    def test_nested_parser(self):
        result = parse_legacy_params('X=[1,2,3], R=[[1,2]], directed=false, name="a,b"')
        self.assertEqual(result, {"x": [1, 2, 3], "r": [[1, 2]], "directed": False, "name": "a,b"})

    def test_decimal_not_fragmented(self):
        self.assertEqual(parse_legacy_params("X=[1.5,2.5]")["x"], [1.5, 2.5])
        self.assertEqual(self.accel.synthesize_and_execute_algorithm(
            "@ALGO[MULTI_SORT | X=[1.5,2.5]]")["status"], "invalid_input")

    def test_bad_parser_input(self):
        for text in ("x=[1,2", "x=[1] evil", "x=[1],", "x=[1], x=[2]", "x=__import__('os')"):
            with self.assertRaises((ValueError, TypeError)):
                parse_legacy_params(text)

    def test_ranges_reach_solver(self):
        r = self.accel.synthesize_and_execute_algorithm(
            "@ALGO[FENWICK_SEGMENT_TREE | X=[1,2,3,4], R=[[1,3]]]")
        self.assertEqual(r["result"]["range_results"], [{"l": 1, "r": 3, "sum": 9, "min": 2, "max": 4}])

    def test_invalid_ranges_not_clamped(self):
        for ranges in ([[-1, 2]], [[1, 8]], [[2, 1]], [], [[0.5, 1]]):
            r = self.accel.synthesize_and_execute_algorithm("RMQ", {"x": [1, 2, 3], "r": ranges})
            self.assertEqual(r["status"], "invalid_input")

    def test_duplicate_json_keys(self):
        with self.assertRaises(ValueError):
            strict_json('{"algorithm":"BST_INSERT","algorithm":"SORT"}')


class StreamGateTests(unittest.TestCase):
    def test_every_split_position(self):
        text = MARKER + json.dumps(request([3, 2, 1]))
        for cut in range(len(text) + 1):
            emitted = []
            gate = TreeOutputGate(emitted.append)
            gate.push(text[:cut])
            gate.push(text[cut:])
            self.assertEqual(emitted, [])
            gate.finish()
            self.assertIn("Kořen: 3", "".join(emitted))
            self.assertNotIn(MARKER, "".join(emitted))

    def test_character_stream(self):
        emitted = []
        gate = TreeOutputGate(emitted.append)
        for c in " \n" + MARKER + json.dumps(request([1, 2, 3])):
            gate.push(c)
        gate.finish()
        gate.finish()
        self.assertEqual(len(emitted), 1)
        self.assertIn("Kořen: 1", emitted[0])

    def test_regular_text_stream_unchanged(self):
        emitted = []
        gate = TreeOutputGate(emitted.append)
        for text in ("Toto ", "je ", "běžná odpověď."):
            gate.push(text)
        self.assertEqual("".join(emitted), "Toto je běžná odpověď.")
        gate.finish()

    def test_truncated_request_never_executes(self):
        for text in ("@TREE", MARKER + '{"algorithm":', MARKER + json.dumps(request([1, 2]))):
            emitted = []
            gate = TreeOutputGate(emitted.append)
            gate.push(text)
            with patch("ai_lens.solver_engine.solve_tree") as solver:
                gate.finish(complete=False)
                solver.assert_not_called()
            self.assertIn("nebyl ověřen", "".join(emitted))

    def test_malformed_and_trailing_text(self):
        for body in ("{", json.dumps(request([1])) + " answer: 2", "[]", "null"):
            emitted = []
            gate = TreeOutputGate(emitted.append)
            gate.push(MARKER + body)
            gate.finish()
            self.assertIn("nebyl ověřen", "".join(emitted))

    def test_size_limit(self):
        emitted = []
        gate = TreeOutputGate(emitted.append)
        gate.push(MARKER + " " * MAX_REQUEST_CHARS)
        gate.finish()
        self.assertIn("nebyl ověřen", "".join(emitted))

    def test_empty_no_output(self):
        emitted = []
        gate = TreeOutputGate(emitted.append)
        gate.finish()
        self.assertEqual(emitted, [])

    def test_cancelled_request_never_emits(self):
        emitted = []
        gate = TreeOutputGate(emitted.append)
        gate.push(MARKER + json.dumps(request([1])))
        gate.discard()
        gate.finish()
        self.assertEqual(emitted, [])

    def test_incomplete_prose_is_labelled(self):
        emitted = []
        gate = TreeOutputGate(emitted.append)
        gate.push("Částečný postup")
        gate.finish(complete=False)
        self.assertIn("nebyla dokončena", "".join(emitted))


class MockedVisionPipeline(unittest.TestCase):
    def setUp(self):
        self.worker = VisionInferenceWorker(None, "", model="gemini-3.5-flash", language="cs")
        self.emitted = []
        self.worker.tokenReceived.connect(self.emitted.append)

    def tearDown(self):
        self.worker.clear_memory()

    def test_high_and_instruction_retained(self):
        self.assertEqual(self.worker.thinking_level, "high")
        for fast in (False, True):
            cfg = self.worker._build_gemini_generation_config("gemini-3.5-flash", fast_fallback=fast)
            self.assertEqual(cfg["thinkingConfig"]["thinkingLevel"], "high")
        self.assertIn(SOLVER_INSTRUCTION, self.worker.system_prompt)

    def gemini_stream(self, text, reason="STOP"):
        chunks = [{"candidates": [{"content": {"parts": [{"text": text[i:i + 7]}]}}]}
                  for i in range(0, len(text), 7)]
        chunks.append({"candidates": [{"finishReason": reason}]})
        content = "\n\n".join("data: " + json.dumps(c) for c in chunks)
        client = httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(200, text=content)))
        with client, patch("ai_lens.vision_engine._pace_gemini_request"):
            return self.worker._stream_gemini_chat(client, "https://test.invalid", {}, {})

    def test_gemini_solver_reaches_ui(self):
        result = self.gemini_stream(MARKER + json.dumps(request([3, 2, 1])))
        self.assertTrue(result[0])
        self.assertIn("Kořen: 3", "".join(self.emitted))
        self.assertNotIn(MARKER, "".join(self.emitted))

    def test_gemini_token_limit_no_execution(self):
        with patch("ai_lens.solver_engine.solve_tree") as solver:
            self.gemini_stream(MARKER + json.dumps(request([3, 2, 1])), "MAX_TOKENS")
            solver.assert_not_called()
        self.assertIn("nebyl ověřen", "".join(self.emitted))

    def test_gemini_normal_response(self):
        self.gemini_stream("Běžná odpověď.")
        self.assertEqual("".join(self.emitted), "Běžná odpověď.")

    def test_ollama_solver_reaches_ui(self):
        text = MARKER + json.dumps(request([1, 2, 3]))
        chunks = [{"message": {"content": text[i:i + 9]}, "done": False}
                  for i in range(0, len(text), 9)]
        chunks.append({"message": {"content": ""}, "done": True, "done_reason": "stop"})
        content = "\n".join(json.dumps(c) for c in chunks)
        with httpx.Client(transport=httpx.MockTransport(
                lambda req: httpx.Response(200, text=content))) as client:
            result = self.worker._stream_chat(client, "http://127.0.0.1/api/chat", {})
        self.assertTrue(result[0])
        self.assertIn("Kořen: 1", "".join(self.emitted))

    def test_http400_does_not_restart_generation_or_remove_high(self):
        from contextlib import ExitStack
        from copy import deepcopy
        from unittest.mock import Mock
        import ai_lens.vision_engine as vision

        captured = []
        response = httpx.Response(200, json={"candidates": [{
            "finishReason": "STOP",
            "content": {"parts": [{"text": MARKER + json.dumps(request([3, 2, 1]))}]},
        }]})
        def post(*args, **kw):
            captured.append(deepcopy(kw["json"]))
            return response
        client = Mock()
        client.post.side_effect = post
        stream_payloads = []
        def stream(*args, **kw):
            stream_payloads.append(deepcopy(args[3]))
            return False, 400, "unsupported field"
        with ExitStack() as stack:
            stack.enter_context(patch.object(vision, "get_volatile_gemini_api_key", return_value="test-placeholder"))
            stack.enter_context(patch.object(vision, "is_valid_ascii_gemini_api_key", return_value=True))
            stack.enter_context(patch.object(vision, "resolve_live_gemini_model_id", return_value="gemini-3.5-flash"))
            stack.enter_context(patch.object(vision, "_get_shared_gemini_client", return_value=client))
            stack.enter_context(patch.object(vision, "_pace_gemini_request"))
            # This alias has only thinkingBudget, so an explicit High request must skip it.
            stack.enter_context(patch.object(self.worker, "_get_quota_safe_fallback_models",
                                            return_value=[("flash", "gemini-flash-latest")]))
            stack.enter_context(patch.object(self.worker, "_stream_gemini_chat", side_effect=stream))
            self.worker._run_gemini(time.perf_counter(), {}, "synthetic-image-placeholder")
        # No retry with thinkingConfig removed after a 400.
        self.assertEqual(len(stream_payloads), 1)
        self.assertEqual(len(captured), 0)
        client.post.assert_not_called()
        for payload in stream_payloads + captured:
            self.assertEqual(payload["generationConfig"]["thinkingConfig"]["thinkingLevel"], "high")
            self.assertIn(SOLVER_INSTRUCTION, payload["systemInstruction"]["parts"][0]["text"])
            self.assertNotIn("tools", payload)
        self.assertEqual(self.emitted, [])

    def test_unfinished_thought_not_salvaged(self):
        from ai_lens.vision_engine import StreamThinkingFilter
        f = StreamThinkingFilter()
        visible, _ = f.filter_chunk("<think>The answer is 999")
        self.assertEqual(visible + f.flush(), "")


if __name__ == "__main__":
    unittest.main()
