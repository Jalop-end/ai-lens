"""Offline tests for provider tool events, deadlines and visible UI status."""
import ast
import json
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch

import httpx
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PyQt6.QtWidgets import QApplication

from ai_lens.code_execution import CodeExecutionState, CODE_EXECUTION_INSTRUCTION, status_text
from ai_lens.vision_engine import VisionInferenceWorker


def code(text="print(2 + 2)", identifier=None):
    d = {"language": "PYTHON", "code": text}
    if identifier is not None:
        d["id"] = identifier
    return {"executableCode": d}


def result(outcome="OUTCOME_OK", identifier=None):
    d = {"outcome": outcome, "output": "4\n"}
    if identifier is not None:
        d["id"] = identifier
    return {"codeExecutionResult": d}


class ToolStateTests(unittest.TestCase):
    def setUp(self):
        self.stages = []
        self.s = CodeExecutionState(self.stages.append)

    def test_success(self):
        self.s.observe(code())
        self.s.observe(result())
        self.s.buffer("Výsledek: 4")
        self.assertEqual(self.stages, ["running", "result"])
        self.assertEqual(self.s.final_text(True), "Výsledek: 4")

    def test_unfinished_code_not_success(self):
        self.s.observe(code())
        self.s.buffer("I guessed the answer")
        self.assertIsNone(self.s.final_text(True))

    def test_execution_failure(self):
        for outcome in ("OUTCOME_FAILED", "OUTCOME_DEADLINE_EXCEEDED", "OUTCOME_UNSPECIFIED"):
            s = CodeExecutionState(lambda _: None)
            s.observe(code())
            s.observe(result(outcome))
            s.buffer("Unreliable answer")
            self.assertIsNone(s.final_text(True))

    def test_failure_then_corrected_code(self):
        self.s.observe(code())
        self.s.observe(result("OUTCOME_FAILED"))
        self.s.buffer("Wrong")
        self.s.observe(code("print(4)"))
        self.s.observe(result())
        self.s.buffer("Corrected: 4")
        self.assertEqual(self.s.final_text(True), "Corrected: 4")

    def test_pending_second_call(self):
        self.s.observe(code(identifier="a"))
        self.s.observe(code(identifier="b"))
        self.s.observe(result(identifier="a"))
        self.s.buffer("Premature result")
        self.assertIsNone(self.s.final_text(True))

    def test_wrong_result_id(self):
        self.s.observe(code(identifier="a"))
        self.s.observe(result(identifier="b"))
        self.assertIsNone(self.s.final_text(True))

    def test_result_without_code(self):
        self.s.observe(result())
        self.s.buffer("4")
        self.assertIsNone(self.s.final_text(True))

    def test_nonpython_rejected(self):
        self.s.observe({"executableCode": {"language": "BASH", "code": "touch x"}})
        self.s.observe(result())
        self.assertIsNone(self.s.final_text(True))

    def test_size_limit(self):
        self.s.observe(code())
        self.s.observe(result())
        self.s.buffer("x" * 131073)
        self.assertIsNone(self.s.final_text(True))

    def test_incomplete_generation(self):
        self.s.observe(code())
        self.s.observe(result())
        self.s.buffer("4")
        self.assertIsNone(self.s.final_text(False))

    def test_prose_does_not_claim_execution(self):
        self.assertFalse(self.s.observe({"text": "I am running Python now"}))
        self.assertFalse(self.s.used)
        self.assertEqual(self.stages, [])


class WorkerCodeTests(unittest.TestCase):
    def setUp(self):
        self.w = VisionInferenceWorker(None, "", model="gemini-3.5-flash", language="cs",
                                       enable_code_execution=True)
        self.tokens, self.stages = [], []
        self.resets = []
        self.w.tokenReceived.connect(self.tokens.append)
        self.w.executionStatus.connect(self.stages.append)
        self.w.answerReset.connect(lambda: (self.resets.append(True), self.tokens.clear()))

    def tearDown(self):
        self.w.clear_memory()

    def run_stream(self, parts, reason="STOP"):
        chunks = [{"candidates": [{"content": {"parts": [p]}}]} for p in parts]
        chunks.append({"candidates": [{"finishReason": reason}]})
        body = "\n\n".join("data: " + json.dumps(c) for c in chunks)
        with httpx.Client(transport=httpx.MockTransport(
            lambda req: httpx.Response(200, text=body))) as client:
            with patch("ai_lens.vision_engine._pace_gemini_request"):
                return self.w._stream_gemini_chat(client, "https://test.invalid", {},
                                                  {"tools": [{"codeExecution": {}}]})

    def test_cloud_result_reaches_ui(self):
        answer = self.run_stream([code(), result(), {"text": "Výsledek: 4"}])
        self.assertTrue(answer[0])
        self.assertIn("Výsledek: 4", "".join(self.tokens))
        self.assertNotIn("print(", "".join(self.tokens))
        self.assertIn("nejde o nezávisle ověřené", "".join(self.tokens))
        self.assertEqual(self.stages, [status_text("running"), status_text("result")])
        self.assertEqual(self.w.inference_limit, 60)

    def test_failed_tool_suppresses_answer(self):
        answer = self.run_stream([code(), result("OUTCOME_FAILED"), {"text": "WRONG ANSWER"}])
        self.assertEqual(answer[1], 422)
        self.assertNotIn("WRONG ANSWER", "".join(self.tokens))

    def test_interrupted_generation_retracts_provisional_answer(self):
        answer = self.run_stream([code(), result(), {"text": "INCOMPLETE"}], "MAX_TOKENS")
        self.assertEqual(answer[1], 422)
        self.assertNotIn("INCOMPLETE", "".join(self.tokens))
        self.assertEqual(len(self.resets), 1)

    def test_text_visible_before_generation_finishes(self):
        owner = self
        class ObservedStream(httpx.SyncByteStream):
            def __iter__(self):
                for p in [code(), result(), {"text": "První část"}, {"text": ", pokračování"}]:
                    chunk = {"candidates": [{"content": {"parts": [p]}}]}
                    yield ("data: " + json.dumps(chunk) + "\n\n").encode()
                owner.assertEqual("".join(owner.tokens), "První část, pokračování")
                yield b'data: {"candidates":[{"finishReason":"STOP"}]}\n\n'
        with httpx.Client(transport=httpx.MockTransport(
                lambda req: httpx.Response(200, stream=ObservedStream()))) as client:
            with patch("ai_lens.vision_engine._pace_gemini_request"):
                answer = self.w._stream_gemini_chat(client, "https://test.invalid", {}, {"tools": [{}]})
        self.assertTrue(answer[0])
        self.assertEqual("".join(self.tokens).count("První část"), 1)

    def test_retry_replaces_previous_provisional_answer(self):
        answer = self.run_stream([
            code(), result(), {"text": "First tentative answer"},
            code("print(5)"), result(), {"text": "Corrected answer"},
        ])
        self.assertTrue(answer[0])
        self.assertNotIn("First tentative", "".join(self.tokens))
        self.assertIn("Corrected answer", "".join(self.tokens))
        self.assertEqual(len(self.resets), 1)

    def test_no_host_execution(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "should_not_exist"
            self.run_stream([code(f"open({str(path)!r}, 'w').write('unsafe')"),
                             result(), {"text": "4"}])
            self.assertFalse(path.exists())

    def test_normal_response_unchanged(self):
        self.run_stream([{"text": "Běžná odpověď"}])
        self.assertEqual("".join(self.tokens), "Běžná odpověď")
        self.assertEqual(self.w.inference_limit, 40)
        self.assertEqual(self.stages, [])

    def test_deadline_is_total_not_extra(self):
        self.w._t0 = 100
        with patch("ai_lens.vision_engine.time.perf_counter", return_value=130):
            self.assertEqual(self.w._remaining_budget(), 10)
            self.w._on_code_stage("running")
            self.assertEqual(self.w._remaining_budget(), 30)
            self.w._on_code_stage("running")
            self.assertEqual(self.w._remaining_budget(), 30)
        with patch("ai_lens.vision_engine.time.perf_counter", return_value=160):
            self.assertEqual(self.w._remaining_budget(), 0)

    def test_late_tool_cannot_revive_expired_request(self):
        self.w._t0 = 100
        with patch("ai_lens.vision_engine.time.perf_counter", return_value=141):
            self.w._on_code_stage("running")
            self.assertEqual(self.w.inference_limit, 40)
            self.assertEqual(self.stages, [])

    def test_watchdog_closes_stalled_response(self):
        self.w._t0 = 100
        self.w._code_execution_used = True
        response = Mock()
        self.w._active_response = response
        with patch("ai_lens.vision_engine.time.perf_counter", return_value=161):
            self.w._deadline_watch()
        response.close.assert_called_once()
        self.assertTrue(self.w._timed_out)

    def test_watchdog_interrupts_a_silent_stream(self):
        released = threading.Event()
        worker = self.w

        class SilentStream(httpx.SyncByteStream):
            def __iter__(self):
                worker._t0 = time.perf_counter()
                event = {"candidates": [{"content": {"parts": [code()]}}]}
                yield ("data: " + json.dumps(event) + "\n\n").encode()
                watch.start()
                released.wait(2)
            def close(self):
                released.set()

        with patch.object(VisionInferenceWorker, "inference_limit",
                          new=property(lambda w: 0.15 if w._code_execution_used else 0.1)):
            watch = threading.Thread(target=self.w._deadline_watch, daemon=True)
            with httpx.Client(transport=httpx.MockTransport(
                    lambda req: httpx.Response(200, stream=SilentStream()))) as client:
                with patch("ai_lens.vision_engine._pace_gemini_request"):
                    answer = self.w._stream_gemini_chat(client, "https://test.invalid", {},
                                                       {"tools": [{"codeExecution": {}}]})
            watch.join(timeout=1)
        self.assertTrue(released.is_set())
        self.assertFalse(watch.is_alive())
        self.assertTrue(self.w._timed_out)
        self.assertFalse(answer[0])
        self.assertEqual(answer[1], 408)

    def test_no_status_after_cancel(self):
        self.w.cancel()
        self.w._on_code_stage("running")
        self.assertEqual(self.stages, [])

    def test_high_retained(self):
        self.assertIn(CODE_EXECUTION_INSTRUCTION, self.w.system_prompt)
        cfg = self.w._build_gemini_generation_config("gemini-3.5-flash")
        self.assertEqual(cfg["thinkingConfig"]["thinkingLevel"], "high")

    def test_ollama_not_offered_cloud_execution(self):
        w = VisionInferenceWorker(None, "", compute_device="cpu")
        try:
            self.assertNotIn(CODE_EXECUTION_INSTRUCTION, w.system_prompt)
        finally:
            w.clear_memory()

    def test_unsupported_tool_keeps_high_and_normal_answers(self):
        from contextlib import ExitStack
        from copy import deepcopy
        import ai_lens.vision_engine as vision
        captured = []
        def stream(*args, **kw):
            captured.append(deepcopy(args[3]))
            if len(captured) == 1:
                return False, 400, "Code execution is not supported for this model"
            self.w.tokenReceived.emit("Běžná odpověď")
            return True, 200, ""
        with ExitStack() as stack:
            stack.enter_context(patch.object(vision, "get_volatile_gemini_api_key", return_value="test-placeholder"))
            stack.enter_context(patch.object(vision, "is_valid_ascii_gemini_api_key", return_value=True))
            stack.enter_context(patch.object(vision, "resolve_live_gemini_model_id", return_value="gemini-3.5-flash"))
            stack.enter_context(patch.object(vision, "_get_shared_gemini_client", return_value=Mock()))
            stack.enter_context(patch.object(self.w, "_get_quota_safe_fallback_models", return_value=[]))
            stack.enter_context(patch.object(self.w, "_stream_gemini_chat", side_effect=stream))
            self.w._run_gemini(time.perf_counter(), {}, "synthetic-image-placeholder")
        self.assertEqual(len(captured), 2)
        self.assertIn("tools", captured[0])
        self.assertNotIn("tools", captured[1])
        self.assertEqual(captured[1]["generationConfig"]["thinkingConfig"]["thinkingLevel"], "high")
        self.assertNotIn(CODE_EXECUTION_INSTRUCTION, captured[1]["systemInstruction"]["parts"][0]["text"])
        self.assertEqual(self.w.inference_limit, 40)
        self.assertIn("Běžná odpověď", "".join(self.tokens))
        self.assertIn("není", "".join(self.stages))


class StatusWidgetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_normal_widget_status_reset(self):
        from ai_lens.popover import PopoverCard
        widget = PopoverCard()
        try:
            widget.start_loading()
            widget.on_execution_status(status_text("running"))
            self.assertIn("Python", widget.status_label.text())
            widget.on_thinking_progress()
            widget._tick_loading()
            self.assertIn("Python", widget.status_label.text())
            widget.start_loading()
            self.assertEqual(widget._execution_status, "")
            widget.set_markdown_content("An earlier answer")
            widget.set_markdown_content("")
            self.assertEqual(widget.response_browser.toPlainText(), "")
        finally:
            widget.close()

    def test_secret_widget_status_reset(self):
        from ai_lens.popover import SecretTopBar
        widget = SecretTopBar()
        try:
            widget.start_loading()
            widget.on_execution_status(status_text("running"))
            self.assertIn("Python", widget.content_label.text())
            widget.on_thinking_progress()
            self.assertIn("Python", widget.content_label.text())
            widget.start_loading()
            self.assertEqual(widget._execution_status, "")
        finally:
            widget.close()

    def overlay_method(self, name):
        # No screen capture, pynput or global hotkeys required for controller tests.
        p = Path(__file__).parents[1] / "ai_lens/overlay.py"
        root = ast.parse(p.read_text())
        cls = next(n for n in root.body if isinstance(n, ast.ClassDef) and n.name == "OverlayWindow")
        method = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == name)
        ns = {"VisionInferenceWorker": VisionInferenceWorker}
        exec(compile(ast.Module(body=[method], type_ignores=[]), str(p), "exec"), ns)
        return ns[name]

    def test_obsolete_worker_status_ignored(self):
        controller = Mock()
        controller._worker = object()
        self.overlay_method("_on_execution_status")(controller, Mock(), "Late status")
        controller._watchdog_timer.start.assert_not_called()

    def test_ui_timer_uses_remaining_budget(self):
        controller = Mock()
        worker = Mock()
        worker._remaining_budget.return_value = 21.5
        controller._worker = worker
        controller._is_inferring = True
        controller._is_secret_mode = False
        self.overlay_method("_on_execution_status")(controller, worker, "Python")
        controller._watchdog_timer.start.assert_called_once_with(21500)
        controller.popover.on_execution_status.assert_called_once_with("Python")

    def test_retract_current_answer_only(self):
        controller, worker = Mock(), Mock()
        controller._worker = worker
        controller._is_inferring = True
        controller._is_secret_mode = False
        controller._current_reply_buffer = "Provisional"
        self.overlay_method("_on_answer_reset")(controller, worker)
        self.assertEqual(controller._current_reply_buffer, "")
        controller.popover.set_markdown_content.assert_called_once_with("")
        controller.popover.reset_mock()
        self.overlay_method("_on_answer_reset")(controller, Mock())
        controller.popover.set_markdown_content.assert_not_called()


if __name__ == "__main__":
    unittest.main()
