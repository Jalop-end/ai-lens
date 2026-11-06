"""Baseline-compatible reproductions: all network traffic is mocked."""
from contextlib import ExitStack
import json
import time
import unittest
from unittest.mock import Mock, patch
import httpx
import ai_lens.vision_engine as v


class RequestRegressions(unittest.TestCase):
    def setUp(self):
        v._GEMINI_FORBIDDEN_MODELS.clear()
        v._GEMINI_MODEL_COOLDOWN_UNTIL.clear()
        self.w = v.VisionInferenceWorker(None, "", model="gemini-3-flash-preview")

    def tearDown(self):
        self.w.clear_memory()
        v._GEMINI_FORBIDDEN_MODELS.clear()
        v._GEMINI_MODEL_COOLDOWN_UNTIL.clear()

    def run_generation(self, result):
        requests = []
        def stream(*args, **kwargs):
            requests.append(json.loads(json.dumps(args[3])))
            return result
        with ExitStack() as s:
            for name, value in (
                ("get_volatile_gemini_api_key", "test-placeholder"),
                ("is_valid_ascii_gemini_api_key", True),
                ("resolve_live_gemini_model_id", "gemini-3-flash-preview"),
                ("_get_shared_gemini_client", Mock()),
            ):
                s.enter_context(patch.object(v, name, return_value=value))
            s.enter_context(patch.object(self.w, "_get_quota_safe_fallback_models", return_value=[]))
            s.enter_context(patch.object(self.w, "_stream_gemini_chat", side_effect=stream))
            s.enter_context(patch.object(v.time, "sleep"))
            self.w._run_gemini(time.perf_counter(), {}, "mock-image")
        return requests

    def test_429_must_not_start_another_generation(self):
        self.assertEqual(len(self.run_generation((False, 429, "rate limit"))), 1)

    def test_default_request_must_not_offer_code_execution(self):
        payload = self.run_generation((True, 200, ""))[0]
        self.assertNotIn("tools", payload)

    def test_partial_disconnect_must_not_report_success(self):
        class Broken(httpx.SyncByteStream):
            def __iter__(self):
                yield b'data: {"candidates":[{"content":{"parts":[{"text":"partial\\n"}]}}]}\n\n'
                raise httpx.ReadError("disconnect")
        with httpx.Client(transport=httpx.MockTransport(
                lambda _: httpx.Response(200, stream=Broken()))) as c, patch.object(v, "_pace_gemini_request"):
            result = self.w._stream_gemini_chat(c, "https://test.invalid", {}, {})
        self.assertFalse(result[0])

    def test_stop_must_not_wait_for_eof(self):
        tail_reads = []
        class Open(httpx.SyncByteStream):
            def __iter__(self):
                yield b'data: {"candidates":[{"content":{"parts":[{"text":"done"}]},"finishReason":"STOP"}]}\n\n'
                tail_reads.append(True)
        with httpx.Client(transport=httpx.MockTransport(
                lambda _: httpx.Response(200, stream=Open()))) as c, patch.object(v, "_pace_gemini_request"):
            self.assertTrue(self.w._stream_gemini_chat(c, "https://test.invalid", {}, {})[0])
        self.assertEqual(tail_reads, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
