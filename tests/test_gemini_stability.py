"""Offline regression tests. MockTransport results are NOT live API timings."""
from contextlib import ExitStack
import json
import os
import time
import unittest
from unittest.mock import patch

import httpx
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import ai_lens.vision_engine as vision
from ai_lens.code_execution import CODE_EXECUTION_INSTRUCTION
from ai_lens.gemini_errors import error_details, format_error, retain_error, retry_delay
from ai_lens.solver_engine import SOLVER_INSTRUCTION


MODEL = "gemini-3-flash-preview"


def event(parts=None, reason=None):
    candidate = {"content": {"parts": parts or []}}
    if reason:
        candidate["finishReason"] = reason
    return "data: " + json.dumps({"candidates": [candidate]}) + "\n\n"


class ErrorEvidenceTests(unittest.TestCase):
    def test_structured_retry_info_is_retained(self):
        body = json.dumps({"error": {"message": "Resource exhausted", "details": [
            {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "75.2s"},
            {"@type": "type.googleapis.com/google.rpc.QuotaFailure",
             "violations": [{"quotaMetric": "tokens_per_minute"}]},
        ]}})
        kept = retain_error(body)
        self.assertEqual(error_details(kept)["details"], error_details(body)["details"])
        self.assertEqual(retry_delay(kept), 75.2)
        self.assertEqual(vision._extract_retry_after_seconds(kept), 75.2)

    def test_retry_header_not_shortened(self):
        self.assertEqual(retry_delay(retain_error("busy", "120")), 120)
        self.assertEqual(retry_delay(retain_error("retry in 20s", "120")), 120)

    def test_retry_http_date(self):
        self.assertGreater(retry_delay("busy", "Wed, 01 Jan 2098 00:00:00 GMT"), 0)

    def test_malformed_errors_are_safe(self):
        for body in ("", "<html>unavailable</html>", "null", "[]", '{"error": []}'):
            self.assertIsInstance(format_error(503, retain_error(body), MODEL), str)
        self.assertIsNone(retry_delay('{"error":{"details":[null, 2, {}]}}', "not-a-date"))

    def test_no_synthetic_zero_quota(self):
        body = retain_error('{"error":{"message":"Permission denied"}}')
        self.assertNotIn("limit: 0", body)

    def test_access_errors_not_quota_exhaustion(self):
        for code in (401, 403, 404):
            message = format_error(code, "denied", MODEL)
            self.assertNotIn("kvóta 429", message)
            self.assertNotIn("všech", message)
            self.assertIn(f"kód {code}", message)

    def test_invalid_key_400_classified_as_auth(self):
        self.assertIn("autentizace", format_error(400, "API key not valid", MODEL))

    def test_429_no_key_rotation_or_fictitious_reset_time(self):
        message = format_error(429, "daily quota exceeded", MODEL)
        self.assertNotIn("nový API klíč", message)
        self.assertNotIn("minutu", message)
        self.assertIn("nebyl uveden", message)
        self.assertIn("76 s", format_error(429, "retry in 75.2s", MODEL))

    def test_local_cooldown_not_claimed_as_new_provider_error(self):
        message = format_error(429, json.dumps({"error": {
            "local_cooldown": True, "retry_after": 14}}), MODEL)
        self.assertIn("Nový API požadavek nebyl odeslán", message)
        self.assertNotIn("API uvádí", message)


class RequestStabilityTests(unittest.TestCase):
    def setUp(self):
        vision._GEMINI_FORBIDDEN_MODELS.clear()
        vision._GEMINI_MODEL_COOLDOWN_UNTIL.clear()
        self.w = vision.VisionInferenceWorker(None, "test", model=MODEL)
        self.tokens, self.errors, self.finished, self.requests = [], [], [], []
        self.w.tokenReceived.connect(self.tokens.append)
        self.w.errorOccurred.connect(self.errors.append)
        self.w.finishedInference.connect(self.finished.append)

    def tearDown(self):
        self.w.clear_memory()
        vision._GEMINI_FORBIDDEN_MODELS.clear()
        vision._GEMINI_MODEL_COOLDOWN_UNTIL.clear()

    def run_request(self, handler):
        def capture(req):
            self.requests.append((str(req.url), json.loads(req.content), req.extensions["timeout"]))
            return handler(req)
        with ExitStack() as stack:
            client = stack.enter_context(httpx.Client(transport=httpx.MockTransport(capture)))
            stack.enter_context(patch.object(vision, "_get_shared_gemini_client", return_value=client))
            stack.enter_context(patch.object(vision, "_pace_gemini_request"))
            stack.enter_context(patch.object(vision, "get_volatile_gemini_api_key", return_value="test-placeholder"))
            stack.enter_context(patch.object(vision, "is_valid_ascii_gemini_api_key", return_value=True))
            stack.enter_context(patch.object(vision, "resolve_live_gemini_model_id", return_value=MODEL))
            self.w._t0 = time.perf_counter()
            self.w._run_gemini(self.w._t0, {}, "synthetic-image-placeholder")

    def test_plain_answer_single_request_no_python_and_high(self):
        self.run_request(lambda _: httpx.Response(200, text=event([{"text": "Odpověď."}], "STOP")))
        self.assertEqual(len(self.requests), 1)
        payload = self.requests[0][1]
        self.assertNotIn("tools", payload)
        prompt = payload["systemInstruction"]["parts"][0]["text"]
        self.assertNotIn(CODE_EXECUTION_INSTRUCTION, prompt)
        self.assertIn(SOLVER_INSTRUCTION, prompt)
        self.assertEqual(payload["generationConfig"]["thinkingConfig"]["thinkingLevel"], "high")
        self.assertEqual(self.tokens, ["Odpověď."])
        self.assertEqual(len(self.finished), 1)
        self.assertEqual(self.errors, [])
        self.assertGreater(self.requests[0][2]["read"], 30)

    def test_each_http_failure_makes_only_one_attempt(self):
        for status in (400, 401, 403, 404, 429, 500, 502, 503):
            with self.subTest(status=status):
                self.requests.clear()
                self.errors.clear()
                vision._GEMINI_MODEL_COOLDOWN_UNTIL.clear()
                self.run_request(lambda _, s=status: httpx.Response(s, json={"error": {"message": "failure"}}))
                self.assertEqual(len(self.requests), 1)
                self.assertEqual(len(self.errors), 1)
                self.assertIn(f"kód {status}", self.errors[0])
                self.assertEqual(self.finished, [])
                self.assertEqual(vision._GEMINI_FORBIDDEN_MODELS, set())

    def test_429_cooldown_retains_model_and_suppresses_next_request(self):
        self.run_request(lambda _: httpx.Response(429, headers={"Retry-After": "120"},
                                                 json={"error": {"message": "rate limit"}}))
        self.assertGreater(vision._GEMINI_MODEL_COOLDOWN_UNTIL[MODEL] - time.monotonic(), 119)
        self.assertEqual(vision.resolve_live_gemini_model_id(MODEL, [MODEL]), MODEL)
        self.run_request(lambda _: self.fail("Cooldown must prevent a second API call"))
        self.assertEqual(len(self.requests), 1)
        self.assertIn("nebyl odeslán", self.errors[-1])

    def test_temporary_pro_429_is_not_permanent_denial(self):
        self.w.model = "gemini-3.1-pro-preview"
        with patch.object(vision, "is_paid_exclusive_gemini_model", return_value=True):
            self.run_request(lambda _: httpx.Response(429, json={"error": {"message": "retry in 70s"}}))
        self.assertEqual(vision._GEMINI_FORBIDDEN_MODELS, set())
        self.assertEqual(len(self.requests), 1)

    def test_expired_cooldown_allows_same_model(self):
        vision._GEMINI_MODEL_COOLDOWN_UNTIL[MODEL] = time.monotonic() - 1
        self.run_request(lambda _: httpx.Response(200, text=event([{"text": "OK"}], "STOP")))
        self.assertEqual(len(self.requests), 1)
        self.assertEqual(self.errors, [])

    def test_no_implicit_retry_after_empty_output(self):
        self.run_request(lambda _: httpx.Response(200, text=event(reason="STOP")))
        self.assertEqual(len(self.requests), 1)
        self.assertEqual(self.finished, [])
        self.assertIn("kód 204", self.errors[0])

    def test_missing_stop_is_not_success(self):
        self.run_request(lambda _: httpx.Response(200, text=event([{"text": "Část odpovědi"}])))
        self.assertEqual(len(self.requests), 1)
        self.assertEqual(self.finished, [])
        self.assertIn("MISSING_FINISH_REASON", self.errors[0])

    def test_max_tokens_is_not_success(self):
        self.run_request(lambda _: httpx.Response(200, text=event([{"text": "Část"}], "MAX_TOKENS")))
        self.assertEqual(self.finished, [])
        self.assertIn("MAX_TOKENS", self.errors[0])
        self.assertEqual(len(self.requests), 1)

    def test_partial_transport_failure_is_not_success_or_retried(self):
        class Interrupted(httpx.SyncByteStream):
            def __iter__(self):
                yield event([{"text": "Část\n"}]).encode()
                raise httpx.ReadError("dropped connection")
        self.run_request(lambda _: httpx.Response(200, stream=Interrupted()))
        self.assertEqual(len(self.requests), 1)
        self.assertEqual(self.finished, [])
        self.assertIn("STREAM_INTERRUPTED", self.errors[0])

    def test_stop_finishes_without_waiting_for_eof(self):
        tail_reads = []
        class OpenAfterStop(httpx.SyncByteStream):
            def __iter__(self):
                yield event([{"text": "Hotovo"}], "STOP").encode()
                tail_reads.append(True)
                raise AssertionError("Must not read beyond the terminal event")
        self.run_request(lambda _: httpx.Response(200, stream=OpenAfterStop()))
        self.assertEqual(self.errors, [])
        self.assertEqual(len(self.finished), 1)
        self.assertEqual(self.tokens, ["Hotovo"])
        self.assertEqual(tail_reads, [])

    def test_sse_error_preserves_429_and_details(self):
        body = 'data: {"error":{"code":429,"message":"rate limit","details":[{"retryDelay":"90s"}]}}\n\n'
        self.run_request(lambda _: httpx.Response(200, text=body))
        self.assertEqual(len(self.requests), 1)
        self.assertIn("kód 429", self.errors[0])
        self.assertIn("90 s", self.errors[0])

    def test_code_opt_in_unsupported_tool_retry_is_bounded(self):
        self.w.enable_code_execution = True
        self.w.system_prompt += "\n" + CODE_EXECUTION_INSTRUCTION
        def handler(_):
            if len(self.requests) == 1:
                return httpx.Response(400, json={"error": {"message": "Code execution is not supported"}})
            return httpx.Response(429, json={"error": {"message": "quota"}})
        self.run_request(handler)
        self.assertEqual(len(self.requests), 2)
        self.assertIn("tools", self.requests[0][1])
        self.assertNotIn("tools", self.requests[1][1])
        for _, payload, _ in self.requests:
            self.assertEqual(payload["generationConfig"]["thinkingConfig"]["thinkingLevel"], "high")
        self.assertIn("kód 429", self.errors[0])

    def test_tool_error_without_opt_in_does_not_retry(self):
        self.run_request(lambda _: httpx.Response(400, json={"error": {
            "message": "Code execution unsupported"}}))
        self.assertEqual(len(self.requests), 1)

    def test_only_boolean_true_enables_code_execution(self):
        for value in (None, False, "false", "true", 1):
            w = vision.VisionInferenceWorker(None, "", model=MODEL, enable_code_execution=value)
            try:
                self.assertFalse(w.enable_code_execution)
                self.assertNotIn(CODE_EXECUTION_INSTRUCTION, w.system_prompt)
            finally:
                w.clear_memory()

    def test_expired_deadline_sends_nothing(self):
        with patch.object(self.w, "_remaining_budget", return_value=0):
            self.run_request(lambda _: self.fail("Request after deadline"))
        self.assertEqual(self.requests, [])
        self.assertEqual(self.finished, [])
        self.assertIn("kód 408", self.errors[0])

    def test_key_redacted_before_excerpt_truncation(self):
        self.run_request(lambda _: httpx.Response(400, json={"error": {
            "message": "x" * 445 + "test-placeholder"}}))
        self.assertNotIn("test-", self.errors[0])
        self.assertEqual(len(self.requests), 1)

    def test_cancelled_request_sends_nothing(self):
        self.w.cancel()
        self.run_request(lambda _: self.fail("Request after cancellation"))
        self.assertEqual(self.requests, [])
        self.assertEqual(self.errors, [])
        self.assertEqual(self.finished, [])


if __name__ == "__main__":
    unittest.main()
