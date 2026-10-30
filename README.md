# AI Lens 🔍
### Instant Offline Screen Capture & Local Vision-Language Assistant

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Ollama](https://img.shields.io/badge/AI-Ollama%20(Local)-orange)](https://ollama.com/)
[![Google Gemini API](https://img.shields.io/badge/Google%20Gemini-API%20Mode-blue)](https://ai.google.dev/)
[![OS: Windows & macOS & Linux](https://img.shields.io/badge/OS-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey)](https://github.com/Jalop-end/ai-lens)
[![UI Languages: 15](https://img.shields.io/badge/UI%20%26%20AI%20Languages-15-success)](#-supported-languages-full-ui--ai-localization)
[![Thinking Tiers: Low | Medium | High](https://img.shields.io/badge/Thinking%20Depth-Low%20%7C%20Medium%20%7C%20High-blueviolet)](#-local-vlm-thinking-tiers-gpu-vs-cpu)

**AI Lens** is an ultra-fast desktop screen-capture assistant designed for instantaneous screen analysis using either 100% offline local Vision-Language Models (e.g. `gemma4:latest`, `qwen2.5-vl`, `minicpm-v`) or Google Gemini cloud intelligence.

With a single hotkey (**`Alt + F8`** / **`Ctrl + Alt + Shift + G`**), Secret Quick-Answer Mode (**`Ctrl + Alt + Shift + Q`**), or clicking the discrete green indicator dot, your screen is instantly frozen (< 15 ms). Circle any area or highlight text to receive real-time streaming answers, quiz solutions, code analysis, or translations—with zero data retention and strict privacy.

---

## 📑 Table of Contents

- [⚡ Quick Start](#-quick-start)
  - [Windows](#windows)
  - [macOS & Linux](#macos--linux)
- [🎯 Modes & Features Comparison](#-modes--features-comparison)
- [🚀 Launch Modes](#-launch-modes)
  - [Mode A: Google Gemini API (Free & Paid + Billing Guard)](#mode-a-google-gemini-api)
  - [Mode B: Local VLM (GPU vs. CPU Thinking Tiers)](#mode-b-local-vlm-thinking-tiers)
- [⌨️ Hotkeys & Gestures](#-hotkeys--shortcuts)
- [🌐 Supported Languages (15)](#-supported-languages-full-ui--ai-localization)
- [💻 CLI Reference](#-cli-reference)
- [📁 Project Directory Layout](#-project-directory-layout)
- [🛡️ Security, Privacy & Zero-Retention](#-security-privacy--zero-retention)
- [🧠 Architecture, Brain & Processing Pipeline](#-architecture-brain--processing-pipeline)
- [⚡ Performance Benchmarks & Hardware Notice](#-performance-benchmarks--hardware-notice)
- [📜 License & Attributions](#-license--attributions)

---

## ⚡ Quick Start

### Windows

1. **Clone repository & install dependencies:**
   ```powershell
   git clone https://github.com/Jalop-end/ai-lens.git
   cd ai-lens
   pip install -e .
   ```

2. **Launch immediately:**
   ```powershell
   # Mode 1: Cloud Intelligence with Google Gemini API
   .\ai-lens.bat start with Gemini

   # Mode 2: 100% Offline Local Model (Default: GPU Acceleration)
   .\ai-lens.bat cs High          # Czech, High thinking depth
   .\ai-lens.bat en High          # English, High thinking depth

   # Mode 3: Lightweight CPU Mode (for laptops / weak GPUs)
   .\ai-lens.bat cs Low CPU       # Fast CPU inference in 1.5–3 seconds
   ```

---

### macOS & Linux

1. **Clone repository & run one-time setup:**
   ```bash
   git clone https://github.com/Jalop-end/ai-lens.git
   cd ai-lens
   pip install -e .
   chmod +x *.sh ai-lens start
   ./setup-mac.sh                 # Registers convenient system-wide aliases
   ```

2. **Launch immediately:**
   ```bash
   # Mode 1: Cloud Intelligence with Google Gemini API
   ./ai-lens.sh start with Gemini
   # or simply:
   ./start with Gemini

   # Mode 2: Local Model (GPU / Apple Silicon Metal acceleration)
   ./ai-lens.sh cs High
   ./ai-lens.sh en High

   # Mode 3: Lightweight CPU Mode
   ./ai-lens.sh cs Low CPU
   ```

---

## 🎯 Modes & Features Comparison

AI Lens offers two purpose-built modes depending on whether you need deep encyclopedic study or rapid, discreet answers:

| Feature / Property | Standard Mode (Lasso) | Secret Mode (Quick-Answer) |
|---|---|---|
| **Primary Hotkey (Win)** | **`Alt + F8`** or **`Ctrl + Alt + Shift + G`** or **`F8`** | **`Ctrl + Alt + Shift + Q`** (or `Ctrl + Shift + Alt + Q`) |
| **Primary Hotkey (Mac)** | **`Option + F8`** or **`Cmd + Shift + G`** or **`F8`** | **`Cmd + Option + Shift + Q`** (or `Cmd + Shift + Option + Q`) |
| **CLI Launch** | `.\ai-lens.bat trigger` | `.\ai-lens.bat secret` |
| **Selection Gesture** | **Freehand mouse lasso** around any screen element | **Text-selection drag** (like selecting text in browser/Word) |
| **Selection Visibility** | Smooth animated contour with 4px tight crop | **Vanishes immediately upon mouse release** (screen stays 100% clean) |
| **Display Interface** | Floating `PopoverCard` anchored next to selection | Glassmorphic `SecretTopBar` along top screen edge |
| **Reasoning & Depth** | **Comprehensive & deep:** +25% rich text depth, citations, follow-up chat | **Direct & concise:** Minimal text, immediate answer without filler |
| **Thinking in UI** | Shown in collapsible thought block (when enabled) | **Zero thoughts in UI:** Internal reasoning stays strictly in background |
| **Math Formatting** | Clean styled LaTeX / KaTeX equations | **Human-friendly chat math:** (e.g. `11 % × 0.81 = 8.91 %` or `x - 5`) |
| **Question Options** | Detailed rationale of each choice | **Smart checkmarks:** Correct marked with `✓`, incorrect with `✗` |
| **Language Logic** | Follows configured app language | **Context-aware:** Fills English tests in English; translates only when asked |
| **Dismissal & RAM** | Click outside, press `Esc`, or right-click to wipe | Click `✕`, copy button, or click outside to instantly wipe RAM |

---

## 🚀 Launch Modes

### Mode A: Google Gemini API

Launch with:
```powershell
.\ai-lens.bat start with Gemini     # Windows
./ai-lens.sh start with Gemini      # macOS / Linux
```

#### 1. Subscription Gate & Model Selection
AI Lens queries whether you have an active Google Cloud / AI Studio paid billing subscription:

| Model ID | Subscription Tier | Role / Specialization | Reasoning Mode |
|---|---|---|---|
| **`gemini-2.5-flash`** *(Recommended)* | **Free & Paid** | Next-gen lightning-fast multimodal model. High accuracy, instant response. | Reasoning with dynamic budget |
| **`gemini-3.5-flash-lite`** | **Free & Paid** | Ultra-lightweight model with lowest latency and highest request throughput. | Snappy direct inference |
| **`gemini-3.1-pro`** | **Paid (Billing Required)** | Flagship model for complex code, advanced mathematics, logic, and deep analysis. | High thinking depth (+0.5–1.0s) |
| **`gemini-3.5-flash`** | **Paid (Billing Required)** | Superior reasoning speed & intelligence balance for complex multi-modal prompts. | High thinking depth (+0.5–1.0s) |
| **`gemini-3.8-flash`** | *(Currently Disabled)* | *Kept in menu for reference, disabled due to upstream preview rate-limits.* | Low-thinking locked |
| **`custom`** | **Free & Paid** | Enter any Google Gemini model identifier manually. | Dynamically configured |

> [!IMPORTANT]
> **Gemini Billing Guard (Automatic Fallback Protection):**
> If you choose a Pro model (`gemini-3.1-pro` or `gemini-3.5-flash`) but provide an API key belonging to a free project without billing, AI Lens **will not crash or print raw error JSON**. 
> Instead, it immediately catches the 403/404 billing refusal, prints a clear friendly warning in your terminal, and **automatically switches your session to `gemini-2.5-flash`**.

#### 2. Strict RAM-Only API Key Security
- Your Gemini API key is entered at startup and verified live against Google's `/v1beta/models` endpoint.
- **100% Volatile Memory:** The key is stored **strictly in process RAM** and is **never written to disk**, `config.json`, or log files.
- **Instant Auto-Wipe:** Exiting the app (`[Esc]`, clicking `✕`, or `stop`) immediately clears the key variable and calls `gc.collect()`.

---

### Mode B: Local VLM (Thinking Tiers: GPU vs. CPU)

Launch with:
```powershell
.\ai-lens.bat [language] [Low|Medium|High] [CPU]
```

AI Lens features an intelligent **Dual-Profile Architecture**:

#### 1. GPU Acceleration Profile (Default)
Offloads all neural network layers and KV-cache directly into VRAM for maximum encyclopedic depth and rich answers (+25% text tokens):

| Tier | Tokens (`num_predict`) | Context (`num_ctx`) | Image Resolution | Thinking Loop | Typical Response Time |
|---|---|---|---|---|---|
| **`Low`** | **3 200 tokens** | 5 120 tokens | 1024 px | `think=False` | **~1.5 – 3 seconds** (instant start) |
| **`Medium`** | **5 120 tokens** | 10 240 tokens | 1280 px | `think=True` | **~4 – 8 seconds** (thorough reasoning) |
| **`High`** | **6 400 tokens** | 12 800 tokens | 1280 px | `think=True` | **~6 – 14 seconds** (exhaustive depth) |

#### 2. CPU Lightweight Profile (Add `CPU` or `@\`)
When running on CPU (e.g. `.\ai-lens.bat cs Low CPU`), AI Lens automatically activates an ultra-efficient profile designed to prevent system lag and deliver verified answers in seconds:

| Tier | Tokens (`num_predict`) | Context (`num_ctx`) | Image Resolution | Thinking Loop | Typical Response Time on CPU |
|---|---|---|---|---|---|
| **`Low`** | **480 tokens** | 1 920 tokens | 640 px | `think=False` | **~1.5 – 3 seconds** (ultra-fast direct answer) |
| **`Medium`** | **960 tokens** | 3 200 tokens | 768 px | `think=True` | **~4 – 8 seconds** (balanced 1–2 paragraphs) |
| **`High`** | **1 600 tokens** | 5 120 tokens | 896 px | `think=True` | **~8 – 15 seconds** (thorough verification) |

---

## ⌨️ Hotkeys & Shortcuts

| Action | Windows Shortcut | macOS Shortcut | Description |
|---|---|---|---|
| **Standard Lasso Capture** | **`Alt + F8`** or **`Ctrl + Alt + Shift + G`** or **`F8`** | **`Option + F8`** or **`Cmd + Shift + G`** or **`F8`** | Freehand mouse lasso; opens PopoverCard with +25% rich depth. |
| **Secret Quick-Answer Mode** | **`Ctrl + Alt + Shift + Q`** | **`Cmd + Option + Shift + Q`** | Text-selection highlight drag; opens concise Glassmorphic SecretTopBar. |
| **Dismiss / Cancel** | **`Esc`** or Right-Click | **`Esc`** or Two-Finger Tap | Immediately closes overlay and flushes RAM. |
| **Clean Process Exit** | **Click Green Dot** (top-right) | **Click Green Dot** (top-right) | Turns red on hover; 1-click immediate safe shutdown. |

---

## 🌐 Supported Languages (Full UI + AI Localization)

Pass any language code as a launch argument (e.g. `.\ai-lens.bat de High` or `.\ai-lens.bat cs Medium`). Both the **AI answers** and the **entire desktop UI** (status badges, timer badges, placeholders) localize instantly:

| Code | Language | Native Name | Code | Language | Native Name |
|---|---|---|---|---|---|
| **`cs`** *(default)* | Czech | Čeština | **`it`** | Italian | Italiano |
| **`en`** | English | English | **`pt`** | Portuguese | Português |
| **`sk`** | Slovak | Slovenčina | **`ru`** | Russian | Русский |
| **`de`** | German | Deutsch | **`nl`** | Dutch | Nederlands |
| **`es`** | Spanish | Español | **`zh`** | Chinese | 中文 |
| **`fr`** | French | Français | **`ja`** | Japanese | 日本語 |
| **`pl`** | Polish | Polski | **`ko`** | Korean | 한국어 |
| **`uk`** | Ukrainian | Українська | | | |

---

## 💻 CLI Reference

| Command (Windows) | Command (macOS / Linux) | Action & Description |
|---|---|---|
| `.\ai-lens.bat start with Gemini` | `./ai-lens.sh start with Gemini` | Starts AI Lens in **Google Gemini API** mode with interactive model selector. |
| `.\ai-lens.bat [lang] [Low\|Medium\|High]` | `./ai-lens.sh [lang] [level]` | Starts local VLM daemon with specified language and thinking tier on GPU. |
| `.\ai-lens.bat [lang] [level] CPU` | `./ai-lens.sh [lang] [level] CPU` | Starts local VLM daemon with lightweight CPU profile. |
| `.\ai-lens.bat secret` | `./ai-lens.sh secret` | Triggers **Secret Quick-Answer Mode** immediately. |
| `.\ai-lens.bat trigger` | `./ai-lens.sh trigger` | Triggers standard lasso overlay immediately. |
| `.\ai-lens.bat diag` | `./ai-lens.sh diag` | Prints real-time system diagnostics (RAM, CPU, active model, security audit). |
| `.\ai-lens.bat levels` | `./ai-lens.sh levels` | Displays detailed parameters for `Low`, `Medium`, and `High` tiers. |
| `.\ai-lens.bat languages` | `./ai-lens.sh languages` | Lists all 15 supported languages and shows the currently active language. |
| `.\ai-lens.bat status` | `./ai-lens.sh status` | Checks if background daemon is running. |
| `.\ai-lens.bat stop` | `./ai-lens.sh stop` | Gracefully terminates background daemon and clears memory. |
| `.\ai-lens.bat config --lang cs` | `./ai-lens.sh config --lang cs` | Persistently updates defaults in `config.json`. |

---

## 📁 Project Directory Layout

The codebase is organized into clean, modular layers with dedicated platform subfolders:

```text
ai-lens/
├── ai_lens/                 # Core Python application package
│   ├── cli.py               # Typer CLI with cross-platform commands and shortcuts
│   ├── daemon.py            # Win32/POSIX background daemon, hotkeys, status dock
│   ├── capture.py           # Sub-15ms screen capture & high-DPI bounding box crop
│   ├── overlay.py           # PyQt6 frameless fullscreen overlay with zero-retention wipe
│   ├── popover.py           # Floating result card & SecretTopBar (HTML renderer)
│   └── vision_engine.py     # Local Ollama & Google Gemini API engines, Low/Medium/High tiers
├── scripts/                 # Platform-specific helpers and shortcuts
│   ├── windows/             # Windows scripts (CPU.bat, GPU.bat, Gemini.bat, enable-cpu-syntax.ps1)
│   └── mac/                 # macOS/Linux scripts (setup-mac.sh, CPU.sh, GPU.sh, Gemini.sh)
├── ai-lens.bat              # Primary Windows entry point
├── ai-lens.sh / ai-lens     # Primary macOS / Linux entry point
├── start.bat / start.sh     # Quick start launchers (e.g. start with Gemini)
├── setup-mac.sh             # Quick macOS shell integration setup
├── enable-cpu-syntax.ps1    # PowerShell integration bridge
├── config.json              # Persistent user configuration
├── pyproject.toml           # Project dependencies & build configuration
├── SPECIFICATIONS.md        # Detailed technical specifications (Czech)
└── README.md                # Project documentation & reference
```

---

## 🛡️ Security, Privacy & Zero-Retention

AI Lens is built with strict privacy and defensive security standards:

- **Zero-Retention RAM Policy:** Screen captures, crop buffers, and prompt history are held exclusively in RAM during active interaction. The moment the result window is closed (`[Esc]`, right-click, or `✕`), all image handles are closed and memory is immediately reclaimed via `gc.collect()`.
- **Zero Disk Persistence:** No screenshots, temporary images, or conversation logs are ever written to disk or `%TEMP%`.
- **Strict SSRF & Localhost Enforcement:** The Ollama client validates host URLs to ensure requests only route to local loopback (`127.0.0.1`, `localhost`).
- **Proxy Bypass Immunity:** HTTP clients enforce `trust_env=False`, ignoring system-level `HTTP_PROXY` redirects to prevent MitM snooping.
- **XSS & Link Hardening:** Markdown output is strictly HTML-escaped before display, and all external navigation links are disabled.
- **Volatile Gemini Key Storage:** API keys reside only in process RAM and are instantly wiped on shutdown.

For complete audit logs and threat vector analysis, see [**`SPECIFICATIONS.md`**](SPECIFICATIONS.md).

---

## 🧠 Architecture, Brain & Processing Pipeline

<details>
<summary><b>📐 Compact Application Architecture & Data Flow (Click to expand diagram)</b></summary>
<br>

```mermaid
flowchart LR
    subgraph S1 ["1. Standby & Triggers"]
        direction TB
        CLI["CLI / Daemon"] --> CFG["Config & Tiers"]
        CFG --> HK["Hotkeys:<br/>Alt+F8 / Ctrl+Alt+Shift+Q"]
        CFG --> DOT["Green Dot<br/>(1-click exit)"]
    end

    subgraph S2 ["2. Capture & Crop"]
        direction TB
        HK --> CAP["Freeze Screen<br/>(&lt;15ms in RAM)"]
        CAP --> OVR["Fullscreen Overlay"]
        OVR -->|"Standard"| LASSO["Lasso (4px crop)"]
        OVR -->|"Secret"| RECT["Text Highlight<br/>(vanishes instantly)"]
        LASSO --> CROP["Base64 RAM Buffer"]
        RECT --> CROP
    end

    subgraph S3 ["3. AI Brain Engine"]
        direction TB
        CROP --> ROUTE{"Engine Router"}
        ROUTE -->|"Local Ollama"| LOCAL["Ollama VLM (GPU/CPU)<br/>Low / Med / High"]
        ROUTE -->|"Google Gemini"| CLOUD["Gemini 2.5 / 3.x Flash<br/>+ Billing Guard Fallback"]
    end

    subgraph S4 ["4. Display & RAM Wipe"]
        direction TB
        LOCAL --> DISP["Stream Response"]
        CLOUD --> DISP
        DISP -->|"Standard"| POP["PopoverCard (+25% depth)"]
        DISP -->|"Secret"| BAR["SecretTopBar (concise)"]
        POP --> WIPE["Zero-Retention Wipe<br/>(RAM cleared, gc.collect)"]
        BAR --> WIPE
    end

    S1 ==> S2 ==> S3 ==> S4
```

</details>

<details>
<summary><b>🧠 Processing Pipeline: How the AI Lens Brain Works (Click to expand)</b></summary>
<br>

1. **Step 1: Low-Latency Event Interception (< 1 ms)**
   - Uses native Win32 `RegisterHotKey` / `GetAsyncKeyState` on Windows or POSIX signals / `pynput` on macOS and Linux.
   - Zero CPU overhead in standby (~0.0% CPU, 45–65 MB RAM).
2. **Step 2: Instant Screen Freeze (< 15 ms)**
   - Captures the exact display framebuffer using high-speed screen APIs directly into RAM.
   - Automatically handles multi-monitor coordinates and DPI scaling (100% to 200%+ up to 4K).
3. **Step 3: Adaptive Bounding-Box Selection**
   - **Standard Mode:** User draws a lasso around any UI element, object, diagram, or text. AI Lens calculates a tightly fitted bounding box with an exact 4px margin.
   - **Secret Mode:** User drags a rectangular text highlight. The moment the mouse button is released, the blue highlight **completely vanishes**—leaving the screen 100% clean and unmodified.
   - The cropped region is encoded in memory as a compressed JPEG base64 buffer without touching disk.
4. **Step 4: AI Brain Processing & Reasoning**
   - **Local VLM (Ollama):** Applies system prompt guards against prompt injection, bounds KV-cache allocation, and dynamically configures thinking budgets.
   - **Google Gemini API:** Injects the volatile RAM-only API key, sets thinking levels (`low` for Gemini 3.8 Flash to guarantee rapid 1.5–2.5 s response), and runs Billing Guard.
   - Emits tokens asynchronously via dedicated background threads (`QThread`) with live progress reporting.
5. **Step 5: High-Precision Formatting & Typography**
   - Answers in bold 16px text (`#E5E7EB`), citations in italic serif font, LaTeX equations converted into natural chat math (e.g. `11 % × 0.81 = 8.91 %`), and multiple-choice options marked with `✓` and `✗`.
   - Secret Mode suppresses all internal thought text (thoughts stay 100% in background).
6. **Step 6: Zero-Retention RAM Wipe**
   - Upon pressing `[Esc]`, clicking the copy/close button, or clicking outside the card, all image buffers, history dictionaries, and Qt documents are cleared, followed by immediate Python garbage collection (`gc.collect()`).

</details>

---

## ⚡ Performance Benchmarks & Hardware Notice

### Typical Speed & Latency Benchmarks

| Pipeline Stage | Local GPU (RTX 3060 / 4060) | Local CPU (8–16 Cores) | Cloud (Google Gemini 2.5 Flash) |
|---|---|---|---|
| **Screen Capture & Freeze** | **< 15 ms** | **< 15 ms** | **< 15 ms** |
| **Selection & Crop to RAM** | **< 5 ms** | **< 5 ms** | **< 5 ms** |
| **Time to First Token (TTFT)** | **~0.5 – 1.5 s** | **~1.0 – 2.5 s** | **~0.4 – 1.0 s** *(network latency)* |
| **Generation Speed** | **40 – 80 tokens/sec** | **4 – 8 tokens/sec** | **80 – 120 tokens/sec** |
| **Total Query Time (`Low`)** | **~1.5 – 3 s** | **~1.5 – 3 s** *(compact tokens)* | **~1.5 – 2.5 s** |
| **Total Query Time (`Medium`)** | **~4 – 8 s** | **~4 – 8 s** *(compact tokens)* | **~2.5 – 4 s** |
| **Total Query Time (`High`)** | **~6 – 14 s** | **~8 – 15 s** *(compact tokens)* | **~4 – 7 s** |
| **RAM Footprint (Standby)** | **45 – 65 MB** | **45 – 65 MB** | **45 – 65 MB** |
| **RAM / VRAM (During Query)** | **+ 350 – 1100 MB VRAM** | **+ 150 – 600 MB RAM** | **+ 20 – 40 MB RAM** |
| **Cleanup & Memory Wipe** | **< 20 ms** | **< 20 ms** | **< 20 ms** |

---

> [!IMPORTANT]
> ### ⚠️ Critical Notice: Local AI Duration Depends on Your Hardware
> 
> The generation times listed above (e.g. `1.5–3 s` on `Low`, `4–8 s` on `Medium`, `6–14 s` on `High`) are **real-world benchmarks measured on standard modern hardware** (e.g., NVIDIA RTX 3060/4060, Apple Silicon M2/M3, PCIe Gen4 NVMe SSD, and 3200+ MHz RAM).
> 
> **Because local AI runs 100% on your computer, actual generation duration will vary according to your hardware:**
> 
> 1. **GPU Architecture & VRAM Bandwidth:**
>    - High-end GPUs (RTX 4070/4080/4090, Apple M-Pro/Max) with 300–1000 GB/s memory bandwidth process tokens at **60–100+ tokens/s**, completing even deep encyclopedic queries in a few seconds.
>    - Entry-level GPUs (GTX 1650, RTX 3050 mobile) or older graphics cards with narrow 64-bit or 128-bit memory buses (~100–190 GB/s) will take proportionally longer (~1.5× to 2.5× longer).
> 2. **CPU Mode & System RAM Speed (DDR4 vs. DDR5):**
>    - When running with `CPU` or `@\`, the primary hardware bottleneck is **system memory bandwidth**. Modern dual-channel DDR5 RAM (5600–6400 MT/s) will run almost **twice as fast** as older single-channel DDR4 RAM (2400–2666 MT/s).
>    - Number of CPU cores also matters: modern 8–16 core CPUs with AVX2/AVX-512 extensions will deliver 6–10 tokens/s, whereas 4-core mobile laptop CPUs may generate 2–4 tokens/s.
> 3. **Cold Start vs. Warm Cache:**
>    - The **very first query** after starting Ollama or booting your computer may take an additional **2 to 6 seconds** while model weights (~3.5–5.5 GB) are loaded from your disk into RAM/VRAM.
>    - All **subsequent queries** remain cached in memory and run at full instant speed. (Running on a fast NVMe SSD minimizes cold-start delay compared to an HDD).
> 4. **Cloud Gemini API Mode:**
>    - Does **not** use your local GPU or CPU. Performance is virtually identical on any computer and depends solely on your internet connection and Google Cloud API latency.

---

## 📜 License & Attributions

- **Code License:** [MIT License](LICENSE) © 2026 Jalop-end.
- **Google Gemini API:** Google Gemini services are governed by the [Google APIs Terms of Service](https://developers.google.com/terms) and [Gemini Additional Terms](https://ai.google.dev/gemini-api/terms).
- **Model Weights:** Google Gemma (Gemma Terms of Use), Qwen2.5-VL (Apache 2.0), MiniCPM-V (Model License).
- **Libraries:** PyQt6 (Riverbank / Qt Company), httpx, Pillow, mss, pynput, typer, numpy. See [**`NOTICE`**](NOTICE) for full legal disclosures.

*Disclaimer: AI Lens is an independent open-source tool and is not affiliated with or endorsed by Google LLC, Alibaba Cloud, OpenBMB, or The Qt Company.*
