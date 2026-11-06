# Složitější výpočty v Gemini a limit 60 sekund

AI Lens má nově kromě deterministického stromového solveru i obecnější cestu:
model může použít spravované Code Execution v Gemini. Vygenerovaný Python se
nespouští v počítači uživatele; běží u poskytovatele API v rámci stejného
modelového požadavku ([dokumentace nástrojů Gemini](https://ai.google.dev/gemini-api/docs/tools?hl=en)).

## Rozdělení práce

- **Podporované postupné stromové operace:** přednost má existující
  `@TREE_SOLVER` a otestované funkce v `solver_engine.py`.
- **Složitější výpočty:** Gemini může vytvořit a spustit Python přes svůj
  vestavěný nástroj. Instrukce uvádí rovnice, matice, kombinatoriku, grafy,
  dynamické programování, numerické úlohy a algoritmické simulace.
- **Běžné otázky a popisy:** zůstává přímá textová odpověď bez povinného
  výpočetního volání.
- **Ollama:** nedostává nástroj Google Code Execution. Lokální generovaný kód
  se neprovádí a nová cloudová cesta není dostupná v čistě lokálním režimu.

Vybrání metody provádí model, nejde o záruku, že vždy použije nejvhodnější
algoritmus nebo správně přečte obrázek. Tato funkce také automaticky
nezpřístupňuje všechny staré Pythonové metody jako nativní funkční nástroje.

## Co uživatel uvidí

Worker zpracovává skutečné události `executableCode` a `codeExecutionResult`,
nikoli textové tvrzení modelu, že něco počítá. Při prvním kódu zobrazí:

> Spouštím výpočet v Pythonu (Gemini) · limit 60 s

Při úspěšném výsledku nástroje zobrazí:

> Výpočet dokončen, připravuji odpověď

Při chybě nástroje informuje o selhání. Model může v rámci stejného požadavku
opravit program. Po úspěšném výsledku nástroje a spárování volání se text
zobrazuje průběžně, nikoli až po dokončení celého generování. Do řádného
ukončení odpovědi jde o průběžný výstup: pokud model spustí další výpočet nebo
generování selže, dosavadní průběžná odpověď se stáhne z UI. Stavy i stažení
fungují v běžném popoveru a v SecretTopBar.

Úspěšné spuštění programu není matematický důkaz správnosti. Výstup proto
obsahuje upozornění, že výsledek z Pythonu není nezávisle ověřený. Instrukce
modelu požaduje zachování pořadí, podmínek, jednotek a kontrolu výsledku,
ale správnost těchto modelových kontrol není zaručená.

## Časový limit

- Běžný požadavek má dosavadní limit 40 sekund.
- Po přijetí skutečné události Code Execution se limit změní na **celkem
  60 sekund od začátku dotazu**.
- Pokud se nástroj ohlásí po 30 sekundách, zbývá nejvýše 30 sekund.
- Opakované spuštění nástroje ani modelový fallback čas neobnovuje.
- Událost přijatá až po vypršení původního limitu dotaz neoživí.
- UI watchdog i worker sledují tentýž zbývající čas; worker se pokouší zavřít
  aktivní HTTP odpověď i při zablokovaném čtení.
- Po expiraci UI dotaz ukončí a ignoruje pozdní stavové události starého
  workeru. Neúplná odpověď není označena jako hotová.

Jde o klientský rozpočet aplikace, nikoli příkaz k vypnutí serverového modelu
nebo záruku zastavení účtování na straně poskytovatele. Plánování OS, síť a
uzavírání transportu mohou přidat režii. Ne-streamovaný fallback nemůže
zobrazit nástroj předtím, než server vrátí jeho události; pokud je do té doby
neoznámí, platí běžný limit.

Vlastní omezení nástroje Gemini, včetně dokumentovaného maximálního času běhu
kódu 30 sekund, tím neměníme. Dokumentace uvádí mimo jiné dostupnost NumPy,
SymPy a SciPy a možnost oprav kódu modelem; podpora nástroje závisí na
konkrétním modelu a API ([Code Execution](https://ai.google.dev/gemini-api/docs/generate-content/code-execution)).

## Bezpečnost a správnost

Nový `ai_lens/code_execution.py` pouze čte protokol API, páruje události,
omezuje nahromaděný text a rozhoduje, zda lze zobrazit navazující odpověď.
Neobsahuje `eval`, spuštění subprocessu ani lokální interpretaci modelového
Pythonu. Syrový program a stdout nástroje automaticky nezobrazuje uživateli
ani je neukládá do souborů. Tato integrace vrací textové výsledky; generované
soubory a obrázky z nástroje nevykresluje.

Výsledky po `OUTCOME_FAILED`, `OUTCOME_DEADLINE_EXCEEDED`, chybějícím výsledku,
nespárovaném ID, přerušení generování či překročení lokálního limitu nejsou
přijaty jako úspěšná výpočetní odpověď. Běžná textová preambule před použitím
nástroje již může být viditelná; při chybě následuje chybový stav, ne falešné
potvrzení správnosti.

Instrukce pro screenshot zůstává oddělená od systémových pravidel. Tato
integrace neslibuje ochranu před každým typem prompt injection ani správnou
interpretaci všech matematických zadání.

## High a dostupnost

Konfigurace High se nesnižuje. HTTP 400 nevede k odstranění výslovného
`thinkingLevel="high"` a fallback bez výslovného High se u takového požadavku
přeskočí. Nový nástroj je přidán jako `tools: [{"codeExecution": {}}]` do
Gemini požadavků. Pokud API výslovně odmítne Code Execution jako nepodporované,
aplikace to oznámí a zkusí požadavek bez nástroje, ale se stejným High.
Běžné odpovědi a lokální stromový solver tak mohou dál fungovat; model dostane
výslovnou instrukci netvrdit, že Python spustil. Pro obecné vykonávání kódu je
potřeba podporovaný endpoint, nikoli vypnutí High.

High reasoning a dostupnost spouštění kódu jsou dvě samostatné vlastnosti API.
Při použití jiných modelových rodin, které používají původní thinking budget,
zůstává jejich stávající konfigurace zachována.

## Ověření

Při zavedení Code Execution prošlo 150 testovacích metod. Navazující opravu
streamování a jednoznačných DP tabulek popisuje [DP a rychlost](DP_STREAMING_CS.md).
Testy
používají simulované HTTP streamy, skutečné metody workeru a headless Qt
widgety. Kontrolují úspěch, neúspěch, opravu programu, neúplné odpovědi, ID
volání, High, stavové zprávy, obnovení UI, ignorování starých workerů a společný
deadline. Samostatný test ověřuje přerušení mlčícího HTTP streamu watchdogem.

Živý Gemini účet, skutečné screenshoty, produkční síť a Windows/macOS nebyly
v této etapě ověřeny. Nejde o měření 98% správnosti ani rychlosti celého produktu.

```bash
QT_QPA_PLATFORM=offscreen python -m unittest discover -s tests -v
```

V běžném vývojovém prostředí lze testy spustit bez offscreen proměnné.
Pro Linux bez desktopu může PyQt6 vyžadovat systémové grafické knihovny.

## První provozní kontrola

1. Aktualizovat repozitář a restartovat aplikaci.
2. Použít Gemini endpoint podporující Code Execution, ponechat High.
3. Zkusit běžnou otázku: neměla by povinně spouštět Python.
4. Zkusit postupné vložení do BST: měla by zůstat deterministická větev.
5. Zkusit složitější numerickou nebo algoritmickou úlohu; pokud model zvolí
   Code Execution, objeví se nový stav.
6. Zkontrolovat nejen číslo, ale i přepis zadání, pořadí operací, předpoklady
   a to, zda jde o přesný nebo přibližný výsledek.

Všechny druhy algoritmů a příkladů nelze garantovat jednou integrací. Další
ověřené specializované řešiče je vhodné přidávat podle chyb ze skutečných
testovacích zadání, zatímco spravované spouštění kódu pokrývá širší, méně
předvídatelnou skupinu úloh.
