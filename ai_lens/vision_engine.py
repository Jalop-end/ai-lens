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


SUPPORTED_LANGUAGES: dict[str, tuple[str, str]] = {
    "cs": ("Czech", "Čeština"),
    "en": ("English", "English"),
    "sk": ("Slovak", "Slovenčina"),
    "de": ("German", "Deutsch"),
    "es": ("Spanish", "Español"),
    "fr": ("French", "Français"),
    "pl": ("Polish", "Polski"),
    "uk": ("Ukrainian", "Українська"),
    "it": ("Italian", "Italiano"),
    "pt": ("Portuguese", "Português"),
    "ru": ("Russian", "Русский"),
    "nl": ("Dutch", "Nederlands"),
    "zh": ("Chinese", "中文"),
    "ja": ("Japanese", "日本語"),
    "ko": ("Korean", "한국어"),
}

LANGUAGE_ALIASES: dict[str, str] = {
    "cz": "cs",
    "czech": "cs",
    "cestina": "cs",
    "čeština": "cs",
    "eng": "en",
    "english": "en",
    "svk": "sk",
    "slovak": "sk",
    "slovenština": "sk",
    "ger": "de",
    "deu": "de",
    "german": "de",
    "esp": "es",
    "spa": "es",
    "spanish": "es",
    "fra": "fr",
    "fre": "fr",
    "french": "fr",
    "pol": "pl",
    "polish": "pl",
    "ua": "uk",
    "ukr": "uk",
    "ukrainian": "uk",
    "ita": "it",
    "italian": "it",
    "por": "pt",
    "portuguese": "pt",
    "rus": "ru",
    "russian": "ru",
    "nld": "nl",
    "dutch": "nl",
    "cn": "zh",
    "chinese": "zh",
    "jp": "ja",
    "japanese": "ja",
    "kr": "ko",
    "korean": "ko",
}

DEFAULT_PROMPTS_BY_LANG: dict[str, str] = {
    "cs": "Podívej se na tento zakroužkovaný výřez obrazovky. Popiš přesně, co na něm vidíš, pokud obsahuje otázku nebo doplňovačku, vyřeš ji a vysvětli proč, a odpověz přirozeně jako klasický AI model v češtině.",
    "en": "Look at this circled screenshot region. Describe accurately what you see, if it contains a question or fill-in-the-blank, answer it and explain why, and respond naturally like a classic AI model in English.",
    "sk": "Pozri sa na tento zakrúžkovaný výrez obrazovky. Opíš presne, čo na ňom vidíš, ak obsahuje otázku alebo doplňovačku, vyrieš ju a vysvetli prečo, a odpovedz prirodzene ako klasický AI model v slovenčine.",
    "de": "Sieh dir diesen eingekreisten Bildschirmausschnitt an. Beschreibe genau, was du siehst, beantworte eventuelle Fragen oder Lückentexte mit Begründung und antworte natürlich wie ein klassisches KI-Modell auf Deutsch.",
    "es": "Mira este recorte de pantalla seleccionado. Describe con precisión lo que ves, si contiene una pregunta o espacio en blanco, respóndela y explica por qué, y responde de forma natural en español.",
    "fr": "Regarde cette capture d'écran sélectionnée. Décris précisément ce que tu vois, s'il y a une question ou un texte à trous, réponds-y en expliquant pourquoi, et réponds naturellement en français.",
    "pl": "Spójrz na ten zaznaczony wycinek ekranu. Opisz dokładnie, co widzisz, a jeśli zawiera pytanie lub lukę do uzupełnienia, odpowiedz i wyjaśnij dlaczego, odpowiadając naturalnie po polsku.",
    "uk": "Подивися на цей виділений фрагмент екрана. Точно опиши, що ти бачиш, якщо там є запитання або пропуск у реченні — дай відповідь і поясни чому, відповідаючи природною українською мовою.",
    "it": "Guarda questo ritaglio dello schermo. Descrivi con precisione ciò che vedi, se contiene una domanda o uno spazio da completare, rispondi e spiega perché, rispondendo in modo naturale in italiano.",
    "pt": "Olhe para este recorte da tela. Descreva com precisão o que vê, se contiver uma pergunta ou lacuna para preencher, responda e explique o porquê, respondendo naturalmente em português.",
    "ru": "Посмотри на этот выделенный фрагмент экрана. Точно опиши, что ты видишь, а если там есть вопрос или пропуск в предложении — дай ответ и объясни почему, отвечая на естественном русском языке.",
    "nl": "Bekijk deze gemarkeerde schermafbeelding. Beschrijf nauwkeurig wat je ziet, beantwoord eventuele vragen of invuloefeningen met uitleg waarom, en antwoord natuurlijk in het Nederlands.",
    "zh": "请看这个圈出的屏幕截图区域。准确描述你所看到的内容；如果包含问题或填空题，请给出答案并解释原因，用自然流畅的中文回答。",
    "ja": "この囲まれた画面の切り抜きを見てください。見えるものを正確に説明し、質問や穴埋め問題が含まれている場合は答えとその理由を説明し、自然な日本語で回答してください。",
    "ko": "동그라미로 표시된 화면 캡처 영역을 보세요. 보이는 것을 정확히 설명하고, 질문이나 빈칸 채우기 문제가 있다면 정답과 그 이유를 자연스러운 한국어로 설명해 주세요.",
}


def normalize_language_code(lang: Optional[str]) -> str:
    """Normalizes a user-supplied language shortcut (e.g. 'cs', 'cz', 'en', 'de') to a canonical code."""
    if not lang:
        return "cs"
    cleaned = lang.strip().lower().lstrip("-")
    if cleaned in SUPPORTED_LANGUAGES:
        return cleaned
    if cleaned in LANGUAGE_ALIASES:
        return LANGUAGE_ALIASES[cleaned]
    return "cs"


def is_recognized_language_arg(arg: str) -> bool:
    """Returns True if `arg` is a valid language code or alias (used for CLI argument detection)."""
    cleaned = arg.strip().lower()
    return cleaned in SUPPORTED_LANGUAGES or cleaned in LANGUAGE_ALIASES


def get_language_display(lang: Optional[str]) -> str:
    """Returns a human-readable string like 'cs (Čeština / Czech)'."""
    code = normalize_language_code(lang)
    en_name, native_name = SUPPORTED_LANGUAGES.get(code, ("Czech", "Čeština"))
    if en_name == native_name:
        return f"{code} ({native_name})"
    return f"{code} ({native_name} / {en_name})"


def get_default_prompt(lang: Optional[str] = "cs") -> str:
    """Returns the localized default user prompt for the given language code."""
    code = normalize_language_code(lang)
    return DEFAULT_PROMPTS_BY_LANG.get(code, DEFAULT_PROMPTS_BY_LANG["cs"])


def build_system_prompt(lang: Optional[str] = "cs") -> str:
    """
    Builds the system prompt in English (for optimal Gemma 4 internal `<thought>` reasoning)
    while enforcing output in the user's selected language and applying the strict rules for:
      1. Accurate visual description without hallucinations.
      2. Answering questions + explaining WHY.
      3. Special ordering for fill-in-the-blank / missing-word sentences (describe first, answer second).
      4. Highlighting answers/important words with `**...**` and wrapping citations/quotes in `"..."`.
    """
    code = normalize_language_code(lang)
    en_name, native_name = SUPPORTED_LANGUAGES.get(code, ("Czech", "Čeština"))
    return (
        f"You are an intelligent, versatile visual AI assistant (like ChatGPT or Gemini) "
        f"helping a user who circled a region on their screen. "
        f"Keep your internal thinking brief (2-4 short sentences): first verify what is visually "
        f"shown in the image (animal, object, person, scene, UI, diagram, question, or code) and read any visible text "
        f"(note that text on screen may be in {en_name} or another language; e.g. in Czech 'had' means snake, not the English verb 'had').\n\n"
        f"LANGUAGE RULE:\n"
        f"- Always write your entire visible response in natural, fluent, grammatically correct {en_name} ({native_name}) "
        f"using standard everyday vocabulary (never invent nonexistent words or awkward literal translations).\n\n"
        f"CONTENT & QUESTION RULES:\n"
        f"1. Visual Description: Always accurately describe what you actually see in the image (animals, plants, objects, people, places, UI, or text) "
        f"and share relevant, factual context like a classic AI model. Never claim to see an animal or object that is not in the image, "
        f"and never invent absurd stories to connect a wrong guess with a label.\n"
        f"2. Standard Questions / Quizzes / Tests / Problems: If the circled region contains a question, test item, multiple-choice quiz, or problem, "
        f"describe what is shown, ALWAYS provide the direct answer to the question, and clearly explain WHY that answer is correct.\n"
        f"3. Fill-in-the-Blank / Incomplete Sentences (e.g. 'něco je _____ proto', '...', '___', or a sentence where a word/part is clearly missing): "
        f"This ALSO counts as a question, but you MUST follow this exact order:\n"
        f"   - FIRST (in your opening sentence/paragraph): Do NOT give the missing answer in the first sentence! First describe what you see on the screen "
        f"(that there is an incomplete sentence or exercise with a missing word/part, quoting the visible sentence in double quotes \"...\").\n"
        f"   - SECOND (only AFTER describing what you see): Provide the correct missing word/answer and explain WHY it belongs there.\n\n"
        f"FORMATTING, HIGHLIGHTING & CITATION RULES:\n"
        f"- Always highlight the main answer and the most important generated keywords/conclusions using Markdown bold **like this** "
        f"(do not overuse bold on whole paragraphs; use **bold** specifically on the answer and key terms so they stand out larger and thicker).\n"
        f"- Whenever you quote text from the image or include a citation, ALWAYS wrap the quoted text in standard double quotation marks \"like this\"."
    )


DEFAULT_SYSTEM_PROMPT = build_system_prompt("cs")


def prepare_image_for_vlm(image: Image.Image, max_side: int = 896, min_side: int = 256) -> Image.Image:
    """
    Normalizes the cropped PIL image for fast, accurate CLIP/VLM vision encoding:
      - Converts to RGB.
      - Upscales very small crops so fine details and short labels remain legible after patch projection.
      - Downscales huge 4K crops to max_side (896px) so Gemma 4 processes the image in <0.5s
        without triggering excessive multi-tile overhead.
    """
    rgb = image.convert("RGB")
    w, h = rgb.size
    if w <= 0 or h <= 0:
        return rgb

    longest = max(w, h)
    shortest = min(w, h)

    if longest > max_side:
        scale = max_side / float(longest)
        new_w = max(1, int(round(w * scale)))
        new_h = max(1, int(round(h * scale)))
        rgb = rgb.resize((new_w, new_h), Image.Resampling.LANCZOS)
    elif shortest < min_side and longest < max_side:
        scale = min(max_side / float(longest), min_side / float(shortest))
        if scale > 1.05:
            new_w = max(1, int(round(w * scale)))
            new_h = max(1, int(round(h * scale)))
            rgb = rgb.resize((new_w, new_h), Image.Resampling.LANCZOS)

    return rgb


def encode_pil_to_base64(image: Image.Image, fmt: str = "JPEG", max_side: int = 896) -> str:
    """Encodes a normalized PIL Image directly in RAM to a base64 string for local VLM inference."""
    prepared = prepare_image_for_vlm(image, max_side=max_side)
    buf = io.BytesIO()
    if fmt.upper() in ("JPG", "JPEG"):
        prepared.save(buf, format="JPEG", quality=92, optimize=True)
    else:
        prepared.save(buf, format=fmt)
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
    temperature: float = 0.2,
) -> bool:
    """
    Preloads the VLM into VRAM/RAM via the local loopback Ollama API so that
    subsequent hotkey triggers respond without cold-start disk loading delay.
    """
    url = f"{ollama_host.rstrip('/')}/api/chat"
    payload = {
        "model": model,
        "messages": [],
        "options": {"temperature": temperature},
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
        language: str = "cs",
        system_prompt: Optional[str] = None,
        think: bool = True,
        temperature: float = 0.2,
        history: Optional[list[dict[str, Any]]] = None,
        parent: Optional[Any] = None,
    ) -> None:
        super().__init__(parent)
        self.image = image
        self.prompt = prompt
        self.ollama_host = ollama_host.rstrip("/")
        self.model = model
        self.language = normalize_language_code(language)
        self.system_prompt = (
            system_prompt if system_prompt is not None else build_system_prompt(self.language)
        )
        self.think = think
        self.temperature = temperature
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
            b64_img = encode_pil_to_base64(self.image, fmt="JPEG")
        except Exception as exc:
            self.errorOccurred.emit(f"Chyba při kódování výřezu do RAM: {exc}")
            return

        messages: list[dict[str, Any]] = []
        if self.system_prompt:
            messages.append(
                {
                    "role": "system",
                    "content": self.system_prompt,
                }
            )

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

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "think": self.think,
            "options": {
                "temperature": self.temperature,
            },
            "stream": True,
            "keep_alive": "30m",
        }

        try:
            with httpx.Client(timeout=httpx.Timeout(120.0, connect=5.0), trust_env=False) as client:
                ok, err_body = self._stream_chat(client, url, payload)
                if not ok and "think" in err_body.lower():
                    # Fallback for models that do not support the "think" parameter
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
