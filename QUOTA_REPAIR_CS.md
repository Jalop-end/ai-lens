# AI Lens: oprava kvóty a dokončování odpovědi

Lokální stabilizační oprava navazuje na commit `102d3f9`. Řeší reprodukované
chyby řízení požadavků; bez konkrétní provozní chybové hlášky a živého testu
netvrdíme, že byly vysvětleny všechny uživatelem hlášené pomalé či nedokončené odpovědi.

## Změněné chování

- **Výchozí cesta:** jeden streamovaný Gemini požadavek, zachované High a
  lokální stromový/DP solver. Obecný Python se již nenabízí každému dotazu.
- **Volitelný Python:** `enable_code_execution` je ve výchozím stavu `false`.
  JSON boolean `true` jej zapne v běžném i tajném režimu. U podporovaných
  lokálních algoritmů není k výpočtu potřeba; jiné výpočty bez něj řeší
  samotný model a nemá se tvrdit, že byly provedeny Pythonem.
- **Počet pokusů:** po 429, chybě oprávnění, chybě sítě nebo prázdné odpovědi
  se automaticky nezkouší další model ani ne-streamované generování.
  Jediná výjimka je výslovně zapnutý Python, který endpoint odmítne jako
  nepodporovaný pomocí HTTP 400: nejvýše jeden další pokus bez nástroje
  na stejném endpointu, se stejným High a původním časovým rozpočtem.
- **Kvóta:** uchovávají se strukturované detaily chyby a `Retry-After`.
  Doporučená prodleva se již nezkracuje na 35 s. Po 429 lokální ochranná pauza
  blokuje další požadavek na stejný model; bez doporučení API je tato
  lokální pauza 14 s, nikoli tvrzení o obnovení kvóty za 14 s.
- **Chybové zprávy:** 403/404 se již nevydává za vyčerpanou kvótu všech
  modelů, nevkládá se smyšlené `[limit: 0]`, dočasná 429 u Pro modelu
  není trvalý zákaz. Text uvádí model, stav a zprávu API; klíč se rediguje
  ještě před zkrácením textu chyby.
- **Dokončení:** po terminální události streamu se nečeká na EOF.
  Chybějící `STOP`, `MAX_TOKENS` a přerušení spojení nejsou úspěšné dokončení.
  Vnitřní nedokončené přemýšlení se nezachraňuje jako finální odpověď.
- **Čas:** High už není restartováno kvůli krátké mezeře 8,8 s.
  Zůstává celkový limit 40 s, při skutečném použití Code Execution
  maximálně 60 s od původního začátku. Nejde o příslib odpovědi do 10–20 s.

Rate limits Gemini platí pro projekt, nikoli jednotlivý API klíč; nový klíč
ve stejném projektu tedy limity neobnoví ([dokumentace Gemini](https://ai.google.dev/gemini-api/docs/rate-limits)).
Odstraněna je proto rada řešit vyčerpanou kvótu vytvořením nového klíče.

## Reprodukce a kontrola

Soubor `tests/test_gemini_request_regressions.py` lze spustit i proti
nezměněné verzi `102d3f9`. Na této verzi selžou všechny čtyři kontroly:
zákaz opakování po 429, nepřítomnost nástroje ve výchozím požadavku,
odmítnutí úspěchu po přerušení a konec čtení při `STOP`.
Na opravené verzi všechny čtyři projdou.

Další testy v `tests/test_gemini_stability.py` kontrolují skutečný worker
s `httpx.MockTransport`, High, chybové kódy, zachování detailů,
lokální pauzu, nejvýše dva kompatibilitní pokusy, zrušení a deadline.
Síť je simulovaná: nejde o test živé kvóty, latence API, čtení screenshotů,
Windows/macOS ani 98% správnosti.

```bash
QT_QPA_PLATFORM=offscreen python -m unittest discover -s tests -v
```

## Nasazení a provozní ověření

Po schváleném nasazení aktualizovat repozitář a aplikaci restartovat.
Pokud v `config.json` nastavení není, Python zůstane vypnutý; není třeba
měnit High. Pro základní kontrolu nejprve ponechat výchozí stav.

- **Běžný výřez:** zkusit původní rychlou textovou otázku a popis scény.
- **Algoritmus:** zopakovat postupné vkládání do stromu a batoh s uvedeným
  významem buněk; potvrdit zachované pořadí a lokální solver.
- **Chyba:** pokud nastane, zaznamenat její přesný text, model a čas.
  Screenshot před sdílením zbavit klíče, osobních údajů a citlivého obsahu.
- **Volitelný Python:** až po kontrole základní cesty lze přidat boolean
  `"enable_code_execution": true` do kořenového `config.json`, restartovat
  a samostatně otestovat obecný výpočet. Nejde o automatické zapnutí jen
  pro složité příklady; při této volbě má nástroj opět k dispozici model.

Opakovaný test s reálným účtem je nutný před tvrzením, že byly odstraněny
všechny provozní potíže nebo dosažena požadovaná rychlost.
