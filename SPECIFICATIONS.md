# Technické specifikace, spotřeba zdrojů a bezpečnostní diagnostika (AI Lens)

Tento dokument obsahuje kompletní technickou specifikaci aplikace **AI Lens**, přehled podporovaných lokálních modelů, přesné nároky na **RAM / VRAM / CPU**, parametry režimů myšlení (**`Low` / `Medium` / `High`**), životní cyklus dat v paměti (**Zero-Retention RAM Policy**) a výsledky **bezpečnostního auditu (ochrana proti napadnutelnosti systému)**.

---

## 1. Jak aplikace běží (Architektura a Běhový cyklus)

AI Lens běží jako plně lokální desktopová aplikace rozdělená do dvou oddělených vrstev, které spolu komunikují výhradně přes lokální loopback rozhraní (`127.0.0.1`):

1. **Klientská GUI & Capture vrstva (Python + PyQt6 + Win32 API):**
   - Po spuštění (`ai-lens cs High` nebo `.\ai-lens.bat`) běží v lehkém pohotovostním režimu (**Standby Daemon**).
   - **Neotevírá žádný naslouchající TCP/UDP port** – komunikace mezi CLI příkazy (`trigger`, `status`, `stop`) a běžícím procesem probíhá přes nativní Windows zprávu `PostThreadMessageW` (`WM_HOTKEY`).
   - Detekce zkratky (`Alt+F8` / `F8` / `Ctrl+Alt+Shift+G`) využívá trojitý engine: dedikované Win32 `GetMessageW` vlákno (`RegisterHotKey`), 15ms hardwarový poller `GetAsyncKeyState` a nízkourovňový hook `pynput`.
2. **Lokální VLM Inference vrstva (Ollama Server na `127.0.0.1:11434`):**
   - Při zakroužkování oblasti myší se z originálního snímku v RAM vyřízne pouze ohraničený obdélník (**Bounding Box** s adaptivním paddingem).
   - Výřez se přímo v paměti RAM převede na optimalizovaný JPEG base64 řetězec a odešle se asynchronním vláknem (`VisionInferenceWorker` / `QThread`) do lokální Ollamy.
   - Tokeny odpovědi se streamují v reálném čase přímo do plovoucího okna (`PopoverCard`).

---

## 2. Specifikace AI modelů (VLM)

Aplikace ve výchozím stavu využívá multimodální model **`gemma4:latest`**, ale v [`config.json`](config.json) (nebo příkazem `ai-lens config --model <název>`) lze přepnout na libovolný lokální VLM model v Ollamě:

| Model v Ollamě | Role / Určení | Velikost na disku | Spotřeba RAM / VRAM (Model) | Minimální RAM PC |
|---|---|---|---|---|
| **`gemma4:latest`** *(Výchozí)* | Univerzální vizuální model s podporou interního přemýšlení (`<thought>`), vhodný na popis obrazu, čtení textu, otázky, logické úlohy i kód | ~5.0 – 5.5 GB | **~5.2 – 6.2 GB** | 8 GB RAM (ideálně 16 GB) |
| **`qwen2.5vl:3b`** | Ultralehký model pro starší / slabší notebooky a integrované grafiky | ~2.5 GB | **~2.8 – 3.4 GB** | 8 GB RAM |
| **`minicpm-v:latest`** | Alternativní model zaměřený na husté OCR a dokumenty | ~5.5 GB | **~5.5 – 6.4 GB** | 8 – 16 GB RAM |

---

## 3. Spotřeba RAM, VRAM a CPU

Spotřeba systémových prostředků se dělí na samotnou aplikaci **AI Lens (Python/PyQt6)** a na běh **lokálního AI modelu (Ollama)**:

### A. Samotná aplikace AI Lens (`python` proces)

| Stav aplikace | Spotřeba RAM (AI Lens) | Využití CPU (AI Lens) | Poznámka |
|---|---|---|---|
| **Pohotovostní režim (Standby / Mini-Dock)** | **~45 – 65 MB RAM** | **0.0 % – 0.2 % CPU** | V RAM je pouze prázdné Qt okno a plovoucí tlačítko; žádný snímek obrazovky není v paměti. |
| **Aktivní zamrznutí obrazovky (Overlay + Laso)** | **~85 – 140 MB RAM** *(1080p–4K)* | **1 % – 4 % CPU** *(vykreslování lasa 60 FPS)* | V RAM drží 1 nekomprimovaný snímek obrazovky (`QPixmap`) po dobu výběru. |
| **Streamování odpovědi v Popover okně** | **~90 – 150 MB RAM** | **1 % – 3 % CPU** | Asynchronní čtení JSON streamu a vykreslování HTML v `QTextBrowser`. |
| **Po uzavření chatu (`Esc` / `✕` / Pravý klik)** | **Zpět na ~45 – 65 MB RAM** | **0.0 % – 0.2 % CPU** | Okamžité vymazání výřezu, historie i obrazovky z RAM + `gc.collect()`. |

### B. Lokální AI Engine (`ollama` proces během dotazu)

* **Pokud má PC dedikovanou GPU (NVIDIA / AMD / Apple Silicon):** Váhy modelu i KV-cache běží ve **VRAM grafické karty**, vytížení systémového CPU během generování je pouze **3 % – 10 %**.
* **Pokud PC běží čistě na CPU / integrované GPU (slabší PC):** Model běží v systémové **RAM** a během samotného generování odpovědi využívá **40 % – 85 % CPU** po dobu několika sekund (mimo generování **0 % CPU**).

---

## 4. Specifikace úrovní myšlení, přesnosti odpovědí a šíře kontextu: `Low` vs. `Medium` vs. `High`

Pojem **„kontext“** v režimech **`Low`**, **`Medium`** a **`High`** zahrnuje dvě věci:
1. **Přesnost odpovědi a bohatost faktických informací o zakroužkovaném objektu/textu** (např. když zakroužkuješ zvíře, rostlinu, předmět, budovu nebo odborný pojem, kolik souvisejících informací a jak hluboký popis o něm dostaneš).
2. **Technickou kapacitu modelu** (velikost kontextového okna `num_ctx`, maximální počet generovaných tokenů `num_predict`, rozlišení výřezu a hloubku interního ověřování).

Všechny tři úrovně jsou navrženy tak, aby **běžely lokálně i na slabších počítačích**:

| Parametr | `Low` (Rychlý režim) | `Medium` (Vyvážený – Výchozí) | `High` (Hluboké myšlení & Encyklopedický kontext) |
|---|---|---|---|
| **Spuštění z terminálu** | `ai-lens cs Low` | `ai-lens cs Medium` *(nebo `ai-lens cs`)* | `ai-lens cs High` |
| **Přesnost odpovědí** | **Základní / Rychlá** (okamžitá identifikace hlavního objektu či textu) | **Vysoká** (pečlivé ověření vizuálních znaků, textu i otázek krok za krokem) | **Maximální** (hloubková kontrola detailů, rozlišení podobných druhů/pojmů, nulová tolerance k drobným chybám) |
| **Faktický kontext (např. když zakroužkuješ zvíře / rostlinu / věc)** | **Stručný kontext (2–4 věty):** přesně určí, o jaké zvíře/věc jde, a přidá 1–2 nejdůležitější fakta. | **Vyvážený, bohatý kontext (1–2 odstavce):** určí druh/kategorii, popíše vzhled na snímku a doplní výskyt (kde žije), potravu/funkci a zajímavost. | **Hluboký encyklopedický kontext (kompletní profil):** přesné druhové zařazení, rozlišení od podobných druhů, anatomické znaky, prostředí, potrava, chování/fungování, historie a zajímavé souvislosti. |
| **Faktický kontext u textu, kódu a otázek** | Rychlé shrnutí významu nebo přímá odpověď se stručným důvodem. | Jasné vysvětlení významu, kontextu věty/kódu a srozumitelné zdůvodnění správné odpovědi. | Kompletní rozbor významu, kontrola kontextu před i za vynechaným místem (`_`), odhalení chytáků a podrobný postup krok za krokem. |
| **Interní přemýšlení (`think`)** | `False` (vypnuto – přímá odpověď) | `True` (zapnuto – krok za krokem) | `True` (hluboká víceúrovňová verifikace) |
| **Velikost kontextu (`num_ctx`)** | **2 048 tokenů** | **4 096 tokenů** | **8 192 tokenů** |
| **Max. počet tokenů (`num_predict`)** | **1 024 tokenů** | **2 560 tokenů** | **4 096 tokenů** |
| **Max. rozlišení výřezu (`max_side`)** | **768 px** | **1 024 px** | **1 344 px** *(vysoká ostrost detailů a diakritiky)* |
| **Teplota (`temperature`)** | `0.20` | `0.15` | `0.10` *(maximální přesnost bez tipování)* |
| **Top-P / Repeat Penalty** | `0.90` / `1.05` | `0.90` / `1.07` | `0.85` / `1.10` |
| **Extra spotřeba RAM (KV-cache)** | **+ ~150 – 250 MB RAM** | **+ ~350 – 500 MB RAM** | **+ ~650 – 950 MB RAM** |
| **Typická doba generování** | **~1 – 4 s** | **~5 – 12 s** | **~10 – 25 s** *(dle výkonu CPU/GPU)* |

---

## 5. Okamžité mazání dat po uzavření chatu (Zero-Retention RAM Policy)

Aplikace uplatňuje přísnou politiku **nulového uchovávání dat (Zero-Retention)**:

1. **Nulový zápis na disk (Zero Disk Persistence):**
   - Snímky obrazovky (`capture_screen`), zakroužkované výřezy (`crop_from_capture`) ani texty konverzací se **nikdy neukládají na pevný disk** (ani do dočasných složek `%TEMP%`).
   - Při startu aplikace funkce `_purge_legacy_disk_traces()` automaticky vyčistí případné staré testovací soubory z dřívějších verzí.
   - Diagnostické výpisy v `daemon.py` se vypisují pouze do živé konzole (`stdout`), nikoli do souboru na disku.
2. **Okamžité vymazání z RAM při zavření chatu / výběru:**
   - Jakmile uživatel zavře chat křížkem `✕`, stiskne `Esc`, klikne pravým tlačítkem myši nebo začne kreslit nové laso:
     - **Ve vlákně `VisionInferenceWorker` (`vision_engine.py`):** V bloku `finally:` (i při okamžitém zrušení přes `clear_memory()`) se uzavře kopie obrázku (`self.image.close()`, `self.image = None`), vymaže se base64 řetězec `b64_img = ""`, vyprázdní se pole `messages.clear()` a `self.history.clear()`.
     - **V okně `PopoverCard` (`popover.py`):** Metoda `clear_sensitive_data()` okamžitě vymaže Markdown buffer (`self._raw_markdown = ""`), vyčistí HTML dokument (`self.response_browser.clear()`, `setHtml("")`) i vstupní pole (`self.prompt_input.clear()`).
     - **V okně `OverlayWindow` (`overlay.py`):** Metody `reset_selection()` a `dismiss_overlay()` uzavřou `self._last_cropped_image.close()`, vymažou všechny slovníky v `self._chat_history`, zruší referenci na celoobrazovkový snímek `self.capture_result = None` a okamžitě zavolají **`gc.collect()`**, čímž Python uvolní paměťové stránky v RAM.

---

## 6. Bezpečnostní diagnostika a ochrana proti napadnutelnosti systému

V rámci bezpečnostního auditu zdrojového kódu byly prověřeny všechny potenciální vektory útoku a implementovány vícevrstvé pojistky:

| Oblast / Hrozba | Stav | Implementovaná ochrana v kódu |
|---|---|---|
| **1. Odeslání snímku mimo PC (SSRF / Exfiltrace dat přes `config.json`)** | **CHRÁNĚNO** | Funkce `validate_local_ollama_host()` v [`ai_lens/vision_engine.py`](ai_lens/vision_engine.py) parsuje URL a **povoluje výhradně lokální loopback** (`127.0.0.1`, `localhost`, `::1`). Pokud by útočník nebo škodlivý skript změnil `ollama_host` v `config.json` na externí IP/doménu, aplikace ji zablokuje a vynutí `http://127.0.0.1:11434`. |
| **2. Odposlech přes systémovou Proxy (`HTTP_PROXY` / MitM)** | **CHRÁNĚNO** | Všechna spojení `httpx.Client` mají pevně nastaveno `trust_env=False`. Aplikace kompletně ignoruje podvržené systémové proměnné `HTTP_PROXY` / `HTTPS_PROXY`. |
| **3. Otevřené síťové porty (Remote Exploit / Firewall)** | **CHRÁNĚNO** | AI Lens **neotevírá žádný naslouchající TCP ani UDP socket**. Proces tedy nelze kontaktovat ani napadnout po lokální síti (LAN/Wi-Fi). |
| **4. HTML / XSS / Link Injection v okně odpovědi (`QTextBrowser`)** | **CHRÁNĚNO** | Všechen text z modelu prochází přes `html.escape()` v [`ai_lens/popover.py`](ai_lens/popover.py), takže žádné HTML značky (`<script>`, `<img>`, `<iframe>`) ze snímku obrazovky se nemohou vykonat. Navíc má `QTextBrowser` nastaveno `setOpenExternalLinks(False)` i `setOpenLinks(False)`. |
| **5. Visual Prompt Injection (škodlivé instrukce v textu na obrazovce)** | **CHRÁNĚNO** | Systémový prompt obsahuje explicitní `SECURITY & PROMPT-INJECTION GUARD` (veškerý text na snímku je brán jako nedůvěryhodná data, nikoli příkazy). Navíc model **nemá přístup k žádným systémovým nástrojům, souborům ani příkazové řádce** – generuje pouze čistý text. |
| **6. Spouštění podprocesů (Command Injection / Binary Hijacking)** | **CHRÁNĚNO** | Funkce `_try_start_ollama_service()` nepoužívá shell (`shell=False`), ověřuje binárku přes `shutil.which("ollama")` a předává pevné pole argumentů `[ollama_bin, "serve"]` s odpojeným `stdin`/`stdout`/`stderr`. |
| **7. Podvržení hodnot v `config.json` (Buffer / UI DoS)** | **CHRÁNĚNO** | Funkce `load_config()` v [`ai_lens/overlay.py`](ai_lens/overlay.py) omezuje (clampuje) všechny číselné hodnoty do bezpečných mezí (`padding` 0–200 px, `border_width` 1–20 px, `temperature` 0.0–2.0). |

---

## 7. Živá diagnostika přímo v příkazové řádce (CLI)

Veškeré specifikace, aktuální vytížení systémové RAM/CPU, přehled přesnosti a kontextu (`Low` / `Medium` / `High`), kontrolu nulového zápisu na disk i 7-bodový bezpečnostní audit si můžeš kdykoliv vypsat přímo do terminálu příkazem:

```powershell
# Spuštění kompletní živé diagnostiky v příkazové řádce (fungují i aliasy diagnostika, security, specs)
ai-lens diag
ai-lens diagnostika

# Nebo přes přiložený spouštěč bez nutnosti aktivovat venv:
.\ai-lens.bat diag
.\ai-lens.bat diagnostika

# Výpis samotných úrovní myšlení, přesnosti odpovědí a šíře kontextu:
ai-lens levels
.\ai-lens.bat levels
```

