# Technické specifikace, spotřeba zdrojů a bezpečnostní diagnostika (AI Lens)

Tento dokument obsahuje kompletní technickou specifikaci aplikace **AI Lens**, přehled podporovaných lokálních modelů, přesné nároky na **RAM / VRAM / CPU**, parametry režimů myšlení (**`Low` / `Medium` / `High`**), životní cyklus dat v paměti (**Zero-Retention RAM Policy**) a výsledky **bezpečnostního auditu (ochrana proti napadnutelnosti systému)**.

---

## 1. Jak aplikace běží (Architektura a Běhový cyklus)

AI Lens běží jako plně lokální desktopová aplikace rozdělená do dvou oddělených vrstev, které spolu komunikují výhradně přes lokální loopback rozhraní (`127.0.0.1`):

1. **Klientská GUI & Capture vrstva (Python + PyQt6 + Win32 API):**
   - Po spuštění (`.\ai-lens.bat en High`, `.\ai-lens.bat cs High` nebo `.\ai-lens.bat start with Gemini`) běží v lehkém pohotovostním režimu (**Standby Daemon**).
   - **Ultra-mini zelená tečka v pravém rohu:** V pravém horním rohu obrazovky je zobrazeno ultra-mini zelené kolečko (7×7 px, `#22C55E`). Přejetím myši zčervená (`#EF4444`) a kliknutím na něj se AI Lens okamžitě a bezpečně kompletně vypne.
   - **Neotevírá žádný naslouchající TCP/UDP port** – komunikace mezi CLI příkazy (`trigger`, `secret`, `status`, `stop`) a běžícím procesem probíhá přes nativní Windows zprávu `PostThreadMessageW` (`WM_HOTKEY`).
   - Detekce zkratek využívá trojitý engine (Win32 `RegisterHotKey`, 15ms hardwarový poller `GetAsyncKeyState` a fallback `pynput`):
     - **Standardní režim lasa:** `Alt + F8`, `F8`, `Ctrl + Alt + Shift + G`.
     - **Secret Quick-Answer Mode:** `Ctrl + Alt + Shift + Q` (nebo `Ctrl + Shift + Alt + Q`).
   - **Těsný Bounding Box (4px padding):** Z kódu bylo odstraněno dřívější 12% nafukování okrajů; rámeček výběru nyní těsně kopíruje nakreslené laso s přesným 4px odsazením.
   - **Inteligentní odkliknutí (Click-Away Dismissal):** Pokud je zobrazen výsledek (karta `PopoverCard` nebo horní lišta `SecretTopBar`), kliknutí kamkoliv mimo tuto kartu overlay ihned bezpečně zavře a vyčistí RAM, čímž se zamezí nechtěnému spuštění nového výběru.
   - **Secret Mode (`Ctrl+Alt+Shift+Q`):**
     - Funguje jako čisté označení textu tažením myší (poloprůhledné zvýraznění jako při kopírování textu bez vytváření ohraničujícího rámečku/pole) a vezme přesně to, co je v něm.
     - **Okamžité zmizení zvýraznění po puštění myši:** Jakmile uživatel pustí levé tlačítko myši, modré zvýraznění textu okamžitě zmizí a obrazovka zůstává 100% čistá, přirozená a neoznačená během inference i čtení.
     - **Vysoce čitelná horní lišta (`SecretTopBar`):** Zobrazuje odpověď přímo v horní liště zarovnané k hornímu okraji obrazovky v poloprůhledném glassmorphic stylu (`rgba(12, 20, 36, 135)` s jemným stínovým efektem a 15px tučným písmem). Text je skvěle viditelný i na světlém podkladu webu či dokumentu a dynamicky se přizpůsobuje počtu řádků textu. Obsahuje čisté tlačítko kopírování a zavření (`✕`), zcela bez emotikonů.
     - **Inteligentní vyhodnocení jazyka (Smart Language Evaluation):**
       - Pokud je označen cizojazyčný test nebo cvičení (např. doplňování chybějícího slova do anglické věty, gramatický tvar, spojování anglických definic nebo výběr možností), model **odpověď nepřekládá do češtiny**, ale doplní přímo správné anglické slovo (např. `"went"`, nikoliv `"šla"`).
       - Pokud zadání výslovně žádá překlad (*"Přeložte:"*, *"Translate into..."*), poskytne přeložený výraz v cílovém jazyce.
       - Pokud jde o běžnou faktickou či popisnou otázku (např. *"What is the capital of France?"*), odpovídá přirozeně ve zvoleném jazyce aplikace (např. česky *"Paříž."*).
     - Striktní systémové omezení na **maximálně 25 slov** přímé odpovědi bez úvodních frází a vysvětlování — maximalizuje rychlost a šetří tokeny i čas.
     - **Anglický formát pohotovostního banneru a hlášení:** Úvodní informační tabulka v konzoli, veškeré notifikace o zmrazení obrazovky, čištění RAM i výmazu API klíče se vypisují do konzole anglicky; při přetížení kvóty (HTTP 429) probíhá automatický fallback na `gemini-3.5-flash-lite` se správným kódem chyby.
2. **Inference vrstva: Duální podpora (Lokální VLM vs. Google Gemini API):**
   - **Lokální režim (Výchozí):** Ollama na `127.0.0.1:11434` (akcelerace GPU nebo CPU přes `@\`). 100% offline.
   - **Režim Google Gemini API (`start with Gemini`):**
     - Umožňuje spuštění přes Google Gemini API s výběrem modelů rozdělených podle předplatného Google:
       - **Placené předplatné (Paid / Billing enabled):** `gemini-2.5-flash`, `gemini-3.1-pro`, `gemini-3.5-flash`, `gemini-3.8-flash`, `gemini-3.5-flash-lite` (+ vlastní model).
       - **Bezplatná kvóta (Free tier):** `gemini-2.5-flash`, `gemini-3.5-flash-lite` (+ vlastní model).
     - **Striktní zrychlení 3.8 Flash (Low Thinking Lock):** Gemini 3.8 Flash je záměrně uzamčen na `thinkingLevel: "low"`, což eliminuje nekonečné smyčky interního uvažování a garantuje bleskové doručení odpovědi do ~1.5–2.5 s (stejně rychle jako 2.5 Flash).
     - **Ochrana API klíče v RAM:** Klíč se zadává v příkazové řádce při startu, je uložen **výhradně v krátkodobé paměti (RAM)** a **nikdy se nezapisuje na disk** do `config.json` ani logů.
     - **Automatický výmaz:** Při jakémkoliv zavření programu ([Esc], pravé tlačítko myši, klik na zelenou tečku, Ctrl+C nebo stop) je API klíč z RAM okamžitě smazán a paměť uvolněna.
   - Při označení oblasti myší se z originálního snímku v RAM vyřízne pouze ohraničený obdélník (**Bounding Box** s těsným 4px paddingem).
   - Výřez se přímo v paměti RAM převede na optimalizovaný JPEG base64 řetězec a streamuje se token po tokenu do plovoucího okna (`PopoverCard` nebo `SecretTopBar`).

---

## 2. Specifikace AI modelů (VLM)

Aplikace ve výchozím stavu využívá multimodální model **`gemma4:latest`**, ale v [`config.json`](config.json) (nebo příkazem `.\ai-lens.bat config --model <název>`) lze přepnout na libovolný lokální VLM model v Ollamě:

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

* **Výchozí běh na GPU (GPU by default):** Aplikace ve výchozím stavu odesílá do Ollamy `num_gpu: -1`, což přesouvá všechny vrstvy modelu i KV-cache přímo do **VRAM grafické karty (NVIDIA / AMD / Apple Silicon)**. Generování je bleskové díky masivní propustnosti VRAM paměti (300–1000 GB/s) a tisícům maticových jader (CUDA / Tensor Cores). Vytížení procesoru je minimální (**3 % – 10 % CPU**).
* **Přepnutí na čisté CPU (`CPU` nebo `@\`):** Pokud uživatel při spuštění zadá `CPU` nebo `@\` (např. `.\ai-lens.bat cs High CPU` nebo `.\ai-lens.bat cs Low CPU`), AI Lens nastaví `num_gpu: 0`. Model běží kompletně v systémové **RAM** a počítá se na procesoru.
  - **Proč je CPU pomalejší (Hardware Bottleneck):** Autoregresivní generování tokenů vyžaduje načtení celé váhové matice modelu (~3.5–5.5 GB) pro **každý jeden vygenerovaný token**. Běžná operační paměť PC (DDR4 / DDR5) má propustnost pouhých **25–60 GB/s** (cca 10× až 20× pomalejší než VRAM grafické karty). Procesor navíc disponuje pouze 8–16 jádry. Rychlost generování na CPU je proto přirozeně omezena na ~**4–8 tokenů/s** (oproti 40–80 tokenů/s na GPU).
  - **Řešení v AI Lens (Odlehčený CPU profil):** Aby uživatel na CPU nečekal minuty, AI Lens při detekci CPU automaticky aktivuje **odlehčený profil** (384–1280 tokenů, vypnuté interní myšlení u `Low`, optimalizovaný výřez a stručné přímé odpovědi). Díky tomu generování na CPU proběhne za **1.5 až 15 sekund**.

---

## 4. Specifikace úrovní myšlení, přesnosti odpovědí a šíře kontextu (Duální GPU / CPU architektura)

Pojem **„kontext“** v režimech **`Low`**, **`Medium`** a **`High`** zahrnuje dvě věci:
1. **Přesnost odpovědi a bohatost faktických informací o zakroužkovaném objektu/textu** (např. když zakroužkuješ zvíře, rostlinu, předmět, budovu nebo odborný pojem, kolik souvisejících informací a jak hluboký popis o něm dostaneš).
2. **Technickou kapacitu modelu** (velikost kontextového okna `num_ctx`, maximální počet generovaných tokenů `num_predict`, rozlišení výřezu a hloubku interního ověřování).

---

#### 4.A GPU Profil (Výchozí akcelerace — plný encyklopedický výkon)

| Parametr | `Low` (Bleskový vyvážený režim) | `Medium` (Zvýšeno nad dřívější High) | `High` (Maximálně posílená encyklopedická hloubka) |
|---|---|---|---|
| **Spuštění z terminálu (Windows)** | `.\ai-lens.bat en Low`<br>`.\ai-lens.bat cs Low` | `.\ai-lens.bat en Medium`<br>`.\ai-lens.bat cs Medium` | `.\ai-lens.bat en High`<br>`.\ai-lens.bat cs High` |
| **Přesnost odpovědí** | **Vysoká & Blesková** (přímá odpověď a ověření znaků bez čekání na `<thought>`) | **Velmi vysoká** (hloubkové rozlišení podobných variant a jemných detailů) | **Maximální** (kompletní verifikace, nulová tolerance chyb, hluboký rozbor) |
| **Faktický kontext (např. zvíře / rostlina / věc)** | **Bohatý vyvážený kontext (1–2 odstavce):** přesně určí druh/kategorii, popíše znaky na snímku, výskyt, potravu/funkci a klíčovou zajímavost. | **Velmi hluboký kontext (2–3 odstavce):** detailní taxonomie, původ/biotop, anatomické znaky, potrava, chování, rozlišení od příbuzných. | **Kompletní encyklopedický profil:** vyčerpávající biologický profil (taxonomie, poddruhy, srovnání záměn, anatomické detaily, biotop, etologie, historie). |
| **Faktický kontext u textu, kódu a otázek** | Jasné vysvětlení významu, kontextu a zdůvodnění odpovědi. | Detailní rozbor významu, kontrola souvislostí a postupné řešení. | Kompletní rozbor včetně kontroly textu před i za prázdným místem (`_`), odhalení chytáků a exaktní důkaz. |
| **Interní přemýšlení (`think`)** | **`False`** *(bleskový start streamu za 1–2 s)* | **`True`** *(zapnuto, důkladné ověření)* | **`True`** *(hluboká víceúrovňová verifikace)* |
| **Velikost kontextu (`num_ctx`)** | **4 096 tokenů** | **8 192 tokenů** | **10 240 tokenů** |
| **Max. počet tokenů (`num_predict`)** | **2 560 tokenů** | **4 096 tokenů** | **5 120 tokenů** |
| **Max. rozlišení výřezu (`max_side`)** | **1 024 px** | **1 280 px** | **1 280 px** *(ostrost detailů bez zahlcení paměti)* |
| **Teplota (`temperature`)** | `0.15` | `0.12` | `0.08` *(maximální determinismus a přesnost)* |
| **Top-P / Repeat Penalty** | `0.90` / `1.07` | `0.88` / `1.09` | `0.85` / `1.10` |
| **Extra spotřeba RAM / VRAM (KV-cache)** | **+ ~350 – 500 MB** | **+ ~600 – 800 MB** | **+ ~800 – 1 100 MB** *(bezpečný strop)* |
| **Typická doba generování (GPU)** | **~1.5 – 3 s** | **~4 – 8 s** | **~6 – 14 s** *(dle GPU)* |

---

### 4.B CPU Profil (Odlehčený režim — snížené tokeny a rychlá odezva bez zasekávání)

| Parametr | `Low` (Bleskový režim) | `Medium` (Vyvážený režim) | `High` (Hloubkový režim pro CPU) |
|---|---|---|---|
| **Spuštění z terminálu (Windows)** | `.\ai-lens.bat cs Low CPU`<br>`.\ai-lens.bat en Low CPU` | `.\ai-lens.bat cs Medium CPU`<br>`.\ai-lens.bat en Medium CPU` | `.\ai-lens.bat cs High CPU`<br>`.\ai-lens.bat en High CPU` |
| **Přesnost odpovědí** | **Základní rychlá:** okamžité řešení bez zdlouhavého přemýšlení | **Dobrá vyvážená:** rychlé ověření znaků, textu i doplňovaček | **Vysoká přesnost:** důkladná verifikace s optimalizovanou délkou textu |
| **Faktický kontext (zvíře / předmět / text)** | **Stručný přímý kontext (1–2 věty):** okamžité určení druhu/řešení a nejdůležitější fakt | **Vyvážený stručný kontext (1 odstavec):** druh/předmět, popis znaků a klíčová vlastnost | **Informativní hloubkový kontext (1–2 odstavce):** přesný druh, znaky, výskyt/funkce a zdůvodnění |
| **Interní přemýšlení (`think`)** | **`False`** *(okamžitá generace bez overheadu)* | **`True`** *(rychlé interní ověření)* | **`True`** *(pečlivá verifikace)* |
| **Velikost kontextu (`num_ctx`)** | **1 536 tokenů** | **2 560 tokenů** | **4 096 tokenů** |
| **Max. počet tokenů (`num_predict`)** | **384 tokenů** | **768 tokenů** | **1 280 tokenů** |
| **Max. rozlišení výřezu (`max_side`)** | **640 px** | **768 px** | **896 px** |
| **Teplota (`temperature`)** | `0.20` | `0.15` | `0.10` |
| **Top-P / Repeat Penalty** | `0.90` / `1.05` | `0.88` / `1.07` | `0.85` / `1.10` |
| **Extra spotřeba RAM (KV-cache)** | **+ ~150 – 250 MB** | **+ ~250 – 400 MB** | **+ ~400 – 600 MB** |
| **Typická doba generování (CPU)** | **~1.5 – 3 s** *(blesková odezva)* | **~4 – 8 s** | **~8 – 15 s** |

### 4.1 Kalibrované rozpoznávání druhů zvířat, plemen a realistická skepse u pravděpodobnosti (`XX %`)

Model byl instrukcemi striktně kalibrován tak, aby **nepřestřeloval jistotu u zvířat a obtížně rozlišitelných plemen**:
- **Přísná skepse u koček, psů a divoké zvěře:**
  - Domácí plemena koček (např. *Britská krátkosrstá*, *Evropská krátkosrstá*, *Ruská modrá*) nebo kříženci mají často velmi podobné zbarvení. Pokud není vidět rodokmen či naprosto specifický tělesný znak, model **záměrně snižuje pravděpodobnost do realistického rozmezí 38–65 %** (nebo **25–45 %**, pokud je zvíře z dálky, rozmazané či částečně zakryté).
  - Hadi a plazi bez křišťálově ostrého detailu šupin na hlavě a zorniček rovněž dostávají sníženou jistotu s výčtem možných záměn.
  - **Vysoká jistota 85–95 %** (nikdy slepých 99 %) je vyhrazena **výhradně nezaměnitelným exemplářům bez jakýchkoliv dvojníků** (např. dospělý lev s hřívou, zebra, žirafa, slon).
- **Povinné zdůvodnění (Rationale):**
  - Za každým procentem následuje **1 věta vysvětlující**, jaké znaky byly potvrzeny a které alternativní druhy či křížence nelze ze snímku stoprocentně vyloučit.
- **Zobrazení v UI:**
  - Hodnota je dynamicky extrahována a v hlavičce `PopoverCard` vykreslena jako čistý barevný odznak bez emotikonů:
    - 🟢 **≥ 85 %:** Zelený odznak (např. `92 %`) – učebnicový, nezaměnitelný druh.
    - 🔵 **70 – 84 %:** Modrý odznak (např. `78 %`) – dobrá shoda hlavních znaků.
    - 🟡 **< 70 %:** Žlutý odznak (např. `54 %` nebo `42 %`) – realistická skepse u kříženců, plemen či chybějících mikro-detailů.

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
| **8. Ochrana Gemini API klíče (Únik citlivých dat na disk)** | **CHRÁNĚNO** | **100% RAM-only storage.** Funkce `load_config()` i ukládací funkce explicitně zakazují zápis `gemini_api_key` do `config.json`. Klíč žije pouze v proměnné `_VOLATILE_GEMINI_API_KEY` a je automaticky vymazán z RAM přes `clear_volatile_gemini_api_key()` a `atexit` při každém zavření aplikace. |

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

# Spuštění v režimu Google Gemini API (výběr modelu z tabulky + zadání RAM klíče):
.\ai-lens.bat start with Gemini

# Spuštění lokálního modelu s GPU (výchozí) vs. s vynuceným CPU:
.\ai-lens.bat cs High            # GPU
.\ai-lens.bat cs High @\         # CPU (nebo v PowerShellu ".\ai-lens.bat cs High `"@\`"")

# Secret Mode (zkratka Ctrl+Alt+Shift+Q, přímá odpověď max 25 slov na horní liště):
.\ai-lens.bat secret
.\ai-lens.bat trigger --secret
```

