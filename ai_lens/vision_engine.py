"""Local offline Vision-Language Model engine via Ollama (127.0.0.1) with QThread streaming."""

from __future__ import annotations

import base64
import io
import json
import time
from typing import Any, Optional

import httpx
from PIL import Image
from PyQt6.QtCore import QThread, pyqtSignal


import subprocess
import sys


def encode_pil_to_base64(image: Image.Image, fmt: str = "PNG") -> str:
    """Encodes a PIL Image directly in RAM to a base64 string for local VLM inference."""
    buf = io.BytesIO()
    image.save(buf, format=fmt)
    return base64.b64encode(buf.getvalue()).decode("ascii")


def _try_start_ollama_service() -> None:
    """Attempts to start 'ollama serve' silently if the local Ollama service is not running."""
    try:
        flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        subprocess.Popen(
            ["ollama", "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=flags,
        )
        time.sleep(1.5)
    except Exception:
        pass


def warmup_local_model(
    ollama_host: str = "http://127.0.0.1:11434",
    model: str = "gemma4:latest",
    keep_alive: str = "30m",
) -> bool:
    """
    Preloads the VLM into VRAM/RAM via the local loopback Ollama API so that
    subsequent hotkey triggers respond without cold-start disk loading delay.
    """
    url = f"{ollama_host.rstrip('/')}/api/chat"
    payload = {
        "model": model,
        "messages": [],
        "keep_alive": keep_alive,
    }
    for attempt in range(2):
        try:
            with httpx.Client(timeout=30.0, trust_env=False) as client:
                resp = client.post(url, json=payload)
                return resp.status_code == 200
        except httpx.ConnectError:
            if attempt == 0:
                _try_start_ollama_service()
        except Exception:
            break
    return False


class VisionInferenceWorker(QThread):
    """
    Asynchronous QThread worker that sends the cropped image + prompt to the local
    Ollama server (127.0.0.1) and streams back generated tokens in real time.
    """

    tokenReceived = pyqtSignal(str)
    thinkingProgress = pyqtSignal()
    finishedInference = pyqtSignal(float)  # elapsed seconds
    errorOccurred = pyqtSignal(str)

    def __init__(
        self,
        image: Image.Image,
        prompt: str,
        ollama_host: str = "http://127.0.0.1:11434",
        model: str = "gemma4:latest",
        history: Optional[list[dict[str, Any]]] = None,
        parent: Optional[Any] = None,
    ) -> None:
        super().__init__(parent)
        self.image = image
        self.prompt = prompt
        self.ollama_host = ollama_host.rstrip("/")
        self.model = model
        self.history = list(history) if history else []
        self._cancelled = False

    def cancel(self) -> None:
        """Signals the streaming loop to abort cleanly."""
        self._cancelled = True

    def _stream_chat(self, client: httpx.Client, url: str, payload: dict[str, Any]) -> tuple[bool, str]:
        """Executes streaming POST request; returns (success, error_message)."""
        with client.stream("POST", url, json=payload) as response:
            if response.status_code != 200:
                body = response.read().decode("utf-8", errors="replace")
                return False, body

            for line in response.iter_lines():
                if self._cancelled:
                    return True, ""
                if not line:
                    continue
                try:
                    chunk = json.loads(line)
                except json.JSONDecodeError:
                    continue

                if "error" in chunk:
                    return False, str(chunk["error"])

                msg = chunk.get("message") or {}
                token = msg.get("content", "")
                if token:
                    self.tokenReceived.emit(token)
                elif msg.get("thinking"):
                    self.thinkingProgress.emit()

                if chunk.get("done", False):
                    break

        return True, ""

    def run(self) -> None:
        t0 = time.perf_counter()
        url = f"{self.ollama_host}/api/chat"

        try:
            b64_img = encode_pil_to_base64(self.image, fmt="PNG")
        except Exception as exc:
            self.errorOccurred.emit(f"Chyba při kódování výřezu do RAM: {exc}")
            return

        messages: list[dict[str, Any]] = []
        if not self.history:
            messages.append(
                {
                    "role": "user",
                    "content": self.prompt,
                    "images": [b64_img],
                }
            )
        else:
            messages.extend(self.history)
            messages.append(
                {
                    "role": "user",
                    "content": self.prompt,
                }
            )

        # Disable long hidden reasoning chains (think=False) on models like gemma4
        # so visible tokens stream in <0.5s instead of waiting 15s on hidden thinking tokens.
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "think": False,
            "stream": True,
            "keep_alive": "30m",
        }

        try:
            with httpx.Client(timeout=httpx.Timeout(120.0, connect=5.0), trust_env=False) as client:
                ok, err_body = self._stream_chat(client, url, payload)
                if not ok and "think" in err_body.lower():
                    # Fallback for older models that don't accept the "think" parameter
                    payload.pop("think", None)
                    ok, err_body = self._stream_chat(client, url, payload)

                if not ok:
                    self.errorOccurred.emit(f"Lokální Ollama vrátila chybu: {err_body}")
                    return

            if not self._cancelled:
                elapsed = time.perf_counter() - t0
                self.finishedInference.emit(elapsed)

        except httpx.ConnectError:
            self.errorOccurred.emit(
                f"Nelze se připojit k lokálnímu AI enginu na `{self.ollama_host}`.\n\n"
                f"Ujisti se, že běží lokální Ollama (`ollama serve`) a máš stažený model `{self.model}`."
            )
        except Exception as exc:
            if not self._cancelled:
                self.errorOccurred.emit(f"Chyba při lokální VLM inferenci: {exc}")
