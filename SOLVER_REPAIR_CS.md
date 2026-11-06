# AI Lens: oprava postupného vkládání, High zachováno

Oprava je připravena proti commitu `644d49cb3bda673bce9f26144049cc7d92045d1a`.
Změny byly připraveny v pracovní kopii a otestovány lokálně. Tento návod popisuje
rozsah opravy; aktuální stav začlenění určuje historie Git. Odeslání změn na
GitHub samo neaktualizuje aplikaci ve vašem počítači.

## Co je opraveno

- **BST:** samostatná implementace postupného vkládání do prázdného nevyvažovaného
  stromu; vstup se netřídí. Hodnoty `[1,2,3]`, `[3,2,1]`, `[2,1,3]` mají kořeny
  `1`, `3`, `2`. Implementace vrací vazby uzlů, tři průchody, výšku v hranách a
  záznam operací. Prázdný strom má výšku `-1`.
- **B-strom:** oddělená simulace postupného vkládání s bottom-up dělením po
  přetečení. Vyžaduje explicitní `max_keys` a `split_median`; vrací skutečné
  úrovně stromu, ne seřazené statické stránky. Neimplementuje všechny varianty
  B-stromů ani top-down dělení před sestupem.
- **Dispatcher:** neznámý název vrací `unsupported`, nikoli třídění. Obecné
  `BTREE`, `IMPLICIT_BTREE`, `BINARY_TREE` se odmítnou jako nejednoznačné.
  Přesnou novou operací je `BTREE_INSERT`; `BST` je kompatibilní alias pro
  `BST_INSERT`.
- **Parser:** parametry `@ALGO[...]` se čtou jako JSON hodnoty v párech
  `key=value`. Desetinné číslo už není rozděleno na celočíselné fragmenty;
  celočíselné operace jej explicitně odmítnou. Vnořené intervaly se zachovají.
- **Intervaly:** `R=[[1,3]]` nad `[1,2,3,4]` se skutečně předá řešiči a vrací
  součet `9`. Konvence je 0-based inclusive; neplatné intervaly se neomezují
  potichu na jiný rozsah.
- **Heuristika čísel:** automatické hádání algoritmu z libovolné číselné řady
  bylo odstraněno. Zpracovávají se jen explicitní požadavky.
- **High:** stávající konfigurace generování nebyla snížena. U Gemini 3,
  kde se nastavuje `thinkingLevel="high"`, zůstává High i při fast fallbacku.
  Kompatibilní opakování po HTTP 400 už nesmí tento výslovný parametr odstranit.
  Záložní endpoint, jehož konfigurace nenabízí výslovné High, se u takového
  požadavku přeskočí; při nedostupnosti High může aplikace raději oznámit chybu.
  Nastavení modelů používajících původní `thinkingBudget` zůstává beze změny.
- **Nedokončený výstup:** neúplný solverový požadavek se neprovede. Pomocné
  myšlenky se už nevytahují jako náhradní finální odpověď. Přerušený běžný text
  dostane upozornění, že není dokončený.

## Jak se solver skutečně dostane do odpovědi

Nový soubor `ai_lens/solver_engine.py` obsahuje stromové algoritmy, validaci,
renderer a `TreeOutputGate`. Integrace přidá systémovou instrukci, aby model
u podporované úlohy vrátil jediný strojový požadavek:

```text
@TREE_SOLVER{"algorithm":"BST_INSERT","params":{"values":[8,3,10,1,6],"duplicate_policy":"reject"}}
```

Výstupní brána zachytí takto označený požadavek i po jednotlivých tokenech.
Spustí jej až po řádném dokončení odpovědi a zobrazí výsledek vytvořený Pythonem.
Model tedy nezobrazuje vlastní odhad výsledku za tímto požadavkem.

Tohle je vlastní textový protokol aplikace, nikoli nativní Gemini function
calling. Nevyžaduje změnu API ani druhé modelové volání. Je připojen ke
streamovanému Gemini, streamované Ollamě i ne-streamovanému Gemini fallbacku.
Běžné odpovědi, které tímto markerem nezačínají, procházejí jako text.

Model musí nové instrukci skutečně vyhovět. Pokud ji ignoruje a odpoví běžným
textem, tato odpověď není ověřena novým solverem. To je zásadní důvod, proč je
před nasazením potřeba živý test na vašich výřezech.

## Konvence a ochranné limity

- Nejvýše 128 celočíselných klíčů; nejvýše 512 bitů na klíč.
- Nejvýše 32 768 znaků strojového požadavku; vstup se nikdy tiše nezkracuje.
- BST duplicity: `reject`, `ignore`, `left`, `right`.
- B-strom duplicity: `reject`, `ignore`.
- B-strom `max_keys`: 2 až 64; `split_median`: `lower` nebo `upper`.
- Pro BST s různými hodnotami umí kompatibilní dispatcher doplnit `reject`;
  při opakovaných hodnotách musí být politika explicitní.
- Stromy jsou na začátku prázdné. Existující strom, mazání, AVL a red-black
  operace nejsou novým solverem podporované.
- `invariants_checked` znamená kontrolu vlastností stromu a zachování vstupu,
  nikoli nezávislé potvrzení přepisu screenshotu nebo důkaz správnosti všech
  možných zadání.

Nový modul používá pouze standardní knihovnu Pythonu. Nezapisuje zadání na disk,
nespouští `eval`, nevykonává kód vygenerovaný modelem a neposílá další API dotaz.
Výpočet běží v existujícím pracovním vlákně, nikoli v novém izolovaném procesu;
jde o pevně omezenou stromovou úlohu, nikoli obecné bezpečné prostředí pro
libovolný Python. Nejhorší doba výstavby nevyvažovaného BST je kvadratická,
nikoli O(log n); zachování předepsaného tvaru má přednost před vyvažováním.

## Testy

Na Linuxu, Pythonu 3.14.8, prošlo **122 testovacích metod**, bez přeskočení.
Nová sada má 43 metod; další jsou existující grafové, procesové a integrační
testy. Ve dvou existujících testech byla opravena chybná cesta mocku
`isolated_solver.client.solve` na `ai_lens.isolated_solver.client.solve`;
jejich kontrolované požadavky nebyly oslabeny.

Nové kontroly zahrnují:

- 5 914 permutací BST, tedy všechny permutace velikostí 0 až 7, s porovnáním
  všech tří průchodů proti samostatné referenční implementaci.
- 300 deterministických případů s duplicitami proti referenční implementaci.
- 480 deterministických B-stromů s kontrolou kapacity a zachování hodnot;
  tyto případy nejsou nezávislým referenčním důkazem celého algoritmu.
- Ručně určené příklady pořadí a volby mediánu B-stromu.
- Rozdělení JSON požadavku na každé možné hranici streamu, token po tokenu,
  neúplný výstup, zrušení, neplatné vstupy a překročení limitu.
- Simulovaný Gemini a Ollama stream přes skutečné metody workeru až k Qt
  výstupnímu signálu.
- Simulovaný HTTP 400 a ne-streamovaný fallback s kontrolou zachování High.

Testy nepoužívají živý API klíč a neodesílají testovací screenshoty do cloudu.
Živé OCR/modelové rozpoznání, celé zobrazené GUI, Windows a macOS nebyly ověřeny.
Čas testovací sady není benchmark aplikace; dosažení 10–20 sekund ani 98 %
správnosti celé pipeline nebylo změřeno.

## Převzetí opravy

Balíček obsahuje patch, změněné zdrojové soubory, testy a skutečný testovací
protokol. Preferujte aplikaci patche do nové větve před ručním přepisováním
souborů. Pokud máte jiné místní změny, nejdřív je uložte nebo zálohujte.

V adresáři svého repozitáře spusťte:

```bash
git status --short
git switch -c fix/sequential-tree-solver
git apply --check /cesta/k/ai-lens-sequential-solver.patch
git apply /cesta/k/ai-lens-sequential-solver.patch
python -m unittest discover -s tests -v
```

Pokud `git apply --check` selže, nepoužívejte násilné přepsání souborů. Patch byl
připraven proti výše uvedenému commitu; je třeba jej sloučit s aktuální verzí.
Závislosti jsou běžné závislosti projektu, včetně NumPy, PyQt6, httpx a Pillow.
V sandboxu byly chybějící závislosti doplněny jen pro testování, nikoli na vašem PC.

## Co ověřit na skutečných výřezech

Pro první kontrolu použijte obrázky těchto tří zadání:

1. Do prázdného BST postupně vlož 1, 2, 3. Urči kořen a preorder.
2. Do prázdného BST postupně vlož 3, 2, 1. Urči kořen a preorder.
3. Do prázdného BST postupně vlož 2, 1, 3. Urči kořen a preorder.

Očekávané dvojice jsou `(1, [1,2,3])`, `(3, [3,2,1])`, `(2, [2,1,3])`.
Renderer navíc ukáže přečtené pořadí, takže lze rozlišit chybu přepisu od chyby
výpočtu. Následně vyzkoušejte duplicity, nečitelnou hodnotu a B-strom s
explicitně zadanou kapacitou a konvencí dělení.

Původní starý akcelerátor není celý přepsaný. Tato oprava řeší konkrétní
zaměňování postupných stromových operací a jejich skutečné propojení s
odpovědí; neznamená kompletní audit všech zbývajících numerických metod.
