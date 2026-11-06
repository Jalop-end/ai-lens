# DP tabulka batohu a rychlejší zobrazování výsledku

Tato oprava navazuje na Code Execution. Zachovává High i dosavadní časové
rozpočty; řeší dvě odlišné věci: význam buněk pomocného pole a zbytečné čekání
na celý text po úspěšném výpočtu.

## Konkrétní příklad

Vstup: předměty o hmotnostech `[7, 4, 5, 9, 2]`, kapacita `17`, každý
předmět nejvýše jednou, požadováno posledních pět buněk pole `0..17`.

Samotný název „problém batohu“ neurčuje, co se v pomocném poli ukládá.
Přesná odpověď závisí na pseudokódu nebo konvenci kurzu:

| Význam buňky a pravidlo zápisu | Buňky 13 až 17 |
|---|---|
| Největší dosažitelná hmotnost nepřevyšující index | `[13, 14, 15, 16, 16]` |
| Boolean dosažitelnost přesné hmotnosti | `[true, true, true, true, false]` |
| Hmotnost předmětu při prvním dosažení; nepřepisovat | `[9, 9, 2, 5, 0]` |
| Hmotnost předmětu; každý nový platný přechod přepisuje | `[2, 2, 2, 2, 0]` |
| Číslo předmětu od 1 při prvním dosažení; nepřepisovat | `[4, 4, 5, 3, 0]` |

V původní funkci `table_state_transition_1d` znamená výchozí varianta
`preserve_first=True` třetí řádek této tabulky. Proto je pro tuto konvenci
odpovědí `[9, 9, 2, 5, 0]`, nikoli optimalizační hodnoty.

Například 13 poprvé vznikne jako `4+9`, 14 jako `5+9`, 15 až s přidaným
předmětem 2 a 16 už při vložení předmětu 5 jako `7+4+5`. Přesná hmotnost 17
dosažitelná není; nula zde znamená nedosažitelnost.

Modelová odpověď s celým řádkem
`[0,0,2,2,4,5,6,7,7,9,9,11,12,13,14,15,16,16]`
je aritmeticky správná pro jinou reprezentaci: maximalizaci hmotnosti do
kapacity. Chybou je její neodůvodněný výběr pro simulaci jiné pomocné tabulky
a také ignorování požadavku vrátit jen posledních pět buněk.

## Přímá výpočetní cesta

Nový modul `ai_lens/dp_solver.py` obsahuje `KNAPSACK_01_TABLE`.
Model musí výslovně určit význam buněk a případné pravidlo zápisu:

```text
@SOLVER_REQUEST{"algorithm":"KNAPSACK_01_TABLE","params":{"weights":[7,4,5,9,2],"capacity":17,"cell_meaning":"last_weight","update_policy":"first","tail_count":5}}
```

Výstup se vytvoří lokálně:

```text
Poslední políčka (13–17): [9, 9, 2, 5, 0]
hmotnost vloženého předmětu; 0 = nedosažitelné.
Pravidlo zápisu: first.
```

Není potřeba generovat celou tabulku ani druhé modelové vysvětlení.
Pokud konvence z obrázku či kontextu není určitelná, instrukce vyžaduje
upřesnění, nikoli tichý předpoklad `max_weight`. Žádná instrukce nezaručuje,
že model význam zadání vždy správně rozpozná.

Podporované varianty jsou 0/1, kladné celočíselné hmotnosti, bez samostatných
zisků/hodnot. Nulové nebo záporné hmotnosti, neomezený batoh a jiné profity se
nesmějí vydávat za tuto variantu.

Limity: 256 předmětů, kapacita 10 000 a nejvýše 1 000 000 kombinací
počet_předmětů × délka_pole. Při překročení se nic nekrátí. Výpočet používá
DP v čase úměrném počtu předmětů a kapacitě, nikoli univerzální O(log n).
Dosažitelnost se nezávisle porovnává s přesnou bitsetovou rekurencí.

Původní veřejná metoda `table_state_transition_1d` nyní používá tuto přesnou
implementaci. Zachovává význam předchůdcové hmotnosti a parametr
`preserve_first`; nepoužívá namátkové opravy buněk ani tiché omezení kapacity.
Neplatné nebo příliš velké požadavky vyvolají chybu místo jiného výpočtu.

## Odstraněné čekání po Code Execution

Předchozí integrace zadržovala všechny textové části po spuštění Pythonu až
do finálního `STOP`. To zhoršovalo vnímanou odezvu, i když model už text
průběžně odesílal.

Nyní se po `OUTCOME_OK` a spárování volání zobrazují příchozí textové části
ihned. Při novém běhu kódu, přerušení nebo chybě se průběžný text stáhne
signálem `answerReset`; konečný text se neopakuje. To nezrychluje samotné
generování modelu a neodstraňuje případné další uvažování po výsledku nástroje.
Ne-streamovaný API fallback nadále čeká na celou HTTP odpověď.

High, lokální stromové výpočty, běžné nealgoritmické odpovědi a společný
60sekundový limit při Code Execution zůstávají zachovány.

## Ověření a omezení

Nové testy obsahují konkrétní zadaný příklad, všechny uvedené interpretace,
duplicitní předměty, zachování pořadí, zákaz opakovaného použití jednoho
předmětu a vstupní limity.

Jedna testovací metoda provádí 26 598 porovnání s vyčerpávajícím výčtem
podmnožin nebo samostatnou dvourozměrnou referencí pro malé vstupy.
Další testy ověřují rozdělení strojového požadavku po hranicích streamu,
průchod přes skutečný worker s jediným simulovaným modelovým požadavkem
a stažení neúplné odpovědi z UI.

V této etapě prošlo všech 171 testovacích metod. Nejde o procento správnosti
živých odpovědí ani benchmark rychlosti modelu. Živé screenshoty a API zde
nebyly testovány.

```bash
python -m unittest discover -s tests -v
```
