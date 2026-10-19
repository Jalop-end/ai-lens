# AI Lens (100% Offline Screen Capture & Local VLM Assistant)

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Ollama](https://img.shields.io/badge/AI-Ollama%20(Local)-orange)](https://ollama.com/)

**AI Lens** is a lightweight, 100% offline desktop screen-capture assistant designed for instantaneous screen analysis using local Vision-Language Models (VLMs) like `gemma4:latest`, `qwen2.5-vl`, or `minicpm-v`.

With a single hotkey (**`Alt + F8`**) or one click on the floating mini-dock, your screen is instantly frozen (< 15 ms). You can freely circle any area with your mouse (lasso selection), and receive real-time streaming answers, code explanations, error diagnoses, or translations from your local AI model—without sending a single byte outside your computer.

---

## Key Features

- **100% Local & Private:** Runs entirely on `127.0.0.1` via local Ollama. Zero external cloud APIs, zero tracking, zero telemetry.
- **Ultra-Fast Capture (< 15 ms):** Captures the screen buffer directly into RAM using high-performance screen capture with automatic high-DPI scaling (up to 4K+).
- **Freehand Lasso Tool:** Draw naturally around any text, terminal error, diagram, or UI element. The bounding box is automatically calculated with customizable padding.
- **Floating Popover Card:**
  - Displays real-time streaming tokens with Markdown and code block syntax rendering.
  - Smart collision detection: automatically repositions to prevent overflowing screen boundaries.
  - Interactive multi-turn follow-up question input at the bottom.
- **Triple-Engine Hotkey Detection:**
  - Supports **`Alt + F8`**, **`F8`**, and **`Ctrl + Alt + Shift + G`**.
  - Powered by native Win32 `RegisterHotKey`, a 15ms `GetAsyncKeyState` hardware key poller, and low-level keyboard hooks to guarantee responsiveness regardless of Windows language switches (`CS`/`EN`) or keyboard rollover limits.
- **Floating Mini-Dock:** A sleek, draggable floating pill (`AI Lens (Alt+F8)`) that provides 1-click mouse activation and visual confirmation that the assistant is running.
- **Firewall & Sandbox Friendly:** Zero listening TCP network ports opened by the application, eliminating Windows Defender Firewall blockages.
- **Console QuickEdit Protection:** Automatically disables Windows Console QuickEdit pause mode so clicking in the terminal never freezes background threads.

---

## Architecture Pipeline

```mermaid
flowchart TD
    subgraph S1 ["1. Activation & Hotkeys"]
        A["Hotkey: Alt+F8 / F8 / Ctrl+Alt+Shift+G"] --> B["Dual Win32 / Hardware Poller"]
        C["Floating Mini-Dock Click"] --> B
        B --> D["Trigger Screen Capture"]
    end

    subgraph S2 ["2. Frame Capture & Overlay"]
        D --> E["Raw Framebuffer into RAM (<15 ms)"]
        E --> F["Frameless Fullscreen Qt Window"]
        F --> G["Frozen Screen Background + 3px Glowing Border"]
    end

    subgraph S3 ["3. Freehand Lasso & Crop"]
        G --> H["Mouse Drag: QPainterPath Trajectory"]
        H --> I["Bounding Box Calculation (+padding)"]
        I --> J["High-DPI Clean Sub-Region Crop into RAM"]
    end

    subgraph S4 ["4. Local VLM Inference"]
        J --> K["QThread Async Worker"]
        K --> L["Local Ollama API (127.0.0.1:11434)"]
        L --> M["Visual Grounding (think=True) + Fast Streaming"]
    end

    subgraph S5 ["5. Popover UI"]
        M --> N["Floating QFrame near Selection"]
        N --> O["Styled HTML: Highlighted Answers & Serif Citations"]
        O --> P["Follow-up Question Field (Multi-turn)"]
        P --> Q["[Esc] / Right Click: Hide back to standby"]
    end
```

---

## Requirements

1. **Operating System:** Windows 10 / 11 (64-bit), Linux (X11 / Wayland), macOS.
2. **Python:** Python 3.10, 3.11, 3.12, or 3.13.
3. **Local AI Engine:** [Ollama](https://ollama.com/) running locally:
   ```bash
   ollama pull gemma4:latest
   # Or optionally:
   # ollama pull qwen2.5vl:3b
   ```

---

## Installation

You do **not** need a virtual environment (`venv`) to install and run AI Lens—after cloning and installing, you can launch it directly with a single command.

1. **Clone the repository:**
   ```bash
   git clone https://github.com/Jalop-end/ai-lens.git
   cd ai-lens
   ```

2. **Install dependencies directly:**
   ```powershell
   pip install -e .
   ```
   *(If `pip` is not on your PATH on Windows, use `py -m pip install -e .` or `python -m pip install -e .`)*

> [!TIP]
> **Using a Virtual Environment (`venv`) is Optional but Ideal:**
> While a `venv` is not required, using one is recommended if you want to keep project dependencies isolated from your global Python installation:
> ```powershell
> # Create virtual environment (use 'py -m venv .venv' on Windows if 'python' opens the MS Store)
> python -m venv .venv
>
> # Activate in PowerShell (bypass script execution policy for the current session if needed):
> Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
> .\.venv\Scripts\Activate.ps1
>
> # Or activate in CMD:
> .\.venv\Scripts\activate.bat
>
> pip install -e .
> ```

---

## Quick Start

### 1. Launch in Standby Mode (with Optional Language Code)
After `pip install -e .`, simply run `ai-lens` (or `.\ai-lens.bat` / `python -m ai_lens`) followed by an optional language shortcut (`cs`, `en`, `de`, `sk`, etc.):

```powershell
# Launch with default language (Czech - cs):
ai-lens
# or:
ai-lens cs

# Launch in English:
ai-lens en

# Or via the Windows batch launcher (works with or without .venv):
.\ai-lens.bat cs
.\ai-lens.bat en
```

- A floating pill **`AI Lens (Alt+F8)`** will appear in the top-right corner of your screen.
- Press **`Alt + F8`** (or **`F8`**, or simply click the floating button).
- The screen freezes with a crisp white & cyan border and a top HUD banner.
- **Draw a circle** with your left mouse button around what you want to analyze:
  - **Images, Animals, Objects, Places:** Accurately describes what is visible and provides natural context like a classic AI model.
  - **Questions, Quizzes, Tests:** Describes what is shown, **always provides the direct answer** (highlighted larger & bolder), and **explains why** it is correct.
  - **Fill-in-the-Blank Sentences (e.g., `"něco je _____ proto"`):** First describes the visible sentence and context, and **only after describing what it sees** provides the missing answer and explanation.
  - **Citations & Quotes:** Automatically wrapped in `""` and rendered in an italic serif citation font (`Georgia` / `Times New Roman`).
- Press **`Esc`** or right-click anywhere to dismiss the overlay and return to standby.

### 2. Immediate One-Shot Trigger
If you want to trigger the overlay directly without waiting for a hotkey:
```powershell
ai-lens trigger
# Or with a specific response language:
ai-lens trigger en
```

---

## Supported Language Shortcuts

Pass any of the following language codes directly after `ai-lens` (e.g. `ai-lens en` or `.\ai-lens.bat de`):

| Code | Language | Example Command |
|---|---|---|
| `cs` *(or `cz`)* | Czech (Čeština) — *Default* | `ai-lens cs` |
| `en` | English (Angličtina) | `ai-lens en` |
| `sk` | Slovak (Slovenčina) | `ai-lens sk` |
| `de` | German (Deutsch) | `ai-lens de` |
| `es` | Spanish (Español) | `ai-lens es` |
| `fr` | French (Français) | `ai-lens fr` |
| `pl` | Polish (Polski) | `ai-lens pl` |
| `uk` *(or `ua`)* | Ukrainian (Українська) | `ai-lens uk` |
| `it` | Italian (Italiano) | `ai-lens it` |
| `pt` | Portuguese (Português) | `ai-lens pt` |
| `ru` | Russian (Русский) | `ai-lens ru` |
| `nl` | Dutch (Nederlands) | `ai-lens nl` |
| `zh` *(or `cn`)* | Chinese (中文) | `ai-lens zh` |
| `ja` *(or `jp`)* | Japanese (日本語) | `ai-lens ja` |
| `ko` *(or `kr`)* | Korean (한국어) | `ai-lens ko` |

---

## CLI Reference

`ai-lens` provides a rich set of command-line tools:

| Command | Description |
|---|---|
| `ai-lens` / `ai-lens <lang>` | Starts the daemon in standby mode (e.g., `ai-lens`, `ai-lens cs`, `ai-lens en`). |
| `ai-lens start --now` | Starts the daemon and immediately triggers the overlay on launch. |
| `ai-lens trigger [lang]` | Sends a trigger signal to the running instance, or opens the overlay directly. |
| `ai-lens languages` | Lists all supported language codes and highlights the currently configured language. |
| `ai-lens status` | Displays the current running state, active hotkey, model, and response language. |
| `ai-lens stop` | Cleanly stops the running AI Lens background process. |
| `ai-lens config` | Views or updates configuration parameters in `config.json`. |

### Configuration Options
You can configure options either in `config.json` or via CLI:
```powershell
# Change the default response language
ai-lens config --lang en

# Change the local model
ai-lens config --model qwen2.5vl:3b

# Change the default hotkey
ai-lens config --hotkey "<alt>+<f8>"

# Adjust selection padding
ai-lens config --padding 20
```

---

## Project Structure

```text
ai-lens/
├── ai_lens/
│   ├── __init__.py          # Package metadata
│   ├── __main__.py          # Direct python -m ai_lens execution entry point
│   ├── cli.py               # Typer CLI commands (start, stop, status, trigger, config)
│   ├── daemon.py            # Win32 background loop, hotkey engine, floating dock
│   ├── capture.py           # Sub-15ms screen capture & high-DPI bounding box crop
│   ├── overlay.py           # PyQt6 frameless fullscreen overlay with lasso painter
│   ├── popover.py           # Floating result card, markdown renderer, collision detection
│   └── vision_engine.py     # Local Ollama stream worker (QThread), auto-start helper
├── ai-lens.bat              # Quick Windows launcher
├── config.json              # Configurable shortcuts, models, padding, and prompts
├── pyproject.toml           # Project dependencies and entry points
├── .gitignore               # Clean git exclusions
└── README.md                # English documentation
```

---

## License

This project is licensed under the [MIT License](LICENSE).
