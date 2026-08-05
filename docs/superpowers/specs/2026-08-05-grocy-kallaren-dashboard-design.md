# Källaren — Grocy-dashboard i Home Assistant

**Datum:** 2026-08-05
**Status:** Design godkänd, implementation ej påbörjad

---

## 1. Problemet vi löser

Dryckesbeståndet i källaren ligger i Grocy (`grocy.sandholdt.se:8443`, container på
docker-hosten `.66:9283`) och matas in med den egna dryck-appen
(`dryck.sandholdt.se:8443`). Men i Home Assistant syns ingenting av det: för att se
vad som finns i vinhyllan måste man öppna Grocy-webben.

Målet: en HA-dashboard som visar beståndet med den rika datan (årgång, druva, land,
betyg) och som klarar de två vanliga handgreppen — **dricka upp en flaska** och
**betygsätta den man just drack** — utan att lämna HA.

## 2. Utgångsläge (verifierat 2026-08-05)

| Fråga | Resultat |
|-------|----------|
| Grocy-innehåll | **1 produkt** ("Test Wine bottle") — dashboarden byggs mot tom källare |
| Locations | Endast `Källare` (id 3, "Vinhylla i källaren") |
| Produktgrupper | `Rött vin`, `Vitt vin`, `Rosévin`, `Mousserande vin`, `Öl` |
| Enheter | `Flaska` (id 4), `Burk` (id 5) |
| Userfields på produkter | `vintage`, `grape_or_style`, `region`, `country`, `abv`, `rating`, `tasting_notes`, `deposit`, `source_url` |
| Grocy-integrationen i HA | Installerad, men **alla lager-sensorer avstängda** (`disabled_by: integration`) |
| Ger integrationen userfields? | ❌ **Nej** |
| Ger `/api/objects/products` userfields? | ✅ **Ja** — nyckeln `userfields` finns i svaret |
| Grocy + dryck-appen uppe? | ✅ `.66:9283` → 302, `.66:8000` → 200 |
| Installerade kort (HACS) | mushroom, apexcharts, auto-entities, card-mod, layout-card, decluttering, power-flow-card-plus |

**Konsekvens:** Grocy-schemat ägs av dryck-appens bootstrap (se
`project_grocy_scanner_app`). Dashboarden får därför **läsa** schemat, aldrig ändra
det — inga nya userfields, grupper eller enheter skapas härifrån.

## 3. Vald lösning — datalager via command_line-sensor

Tre alternativ övervägdes:

| Alt | Upplägg | Utfall |
|-----|---------|--------|
| **A** | `command_line`-sensor + Python-skript som joinar `/api/stock` och `/api/objects/products` | ✅ **Valt** |
| B | Rena `rest:`-sensorer, join i Jinja i varje kort | ❌ Sköra, svårlästa joins; 255-teckenfällor i mellansteg |
| C | Slå på Grocy-integrationens avstängda sensorer | ❌ Inga userfields → ingen årgång/druva/land/betyg, ingen gruppfördelning |

A valdes eftersom joinlogiken då bor på **ett** ställe, kan köras och testas från
terminalen, och levererar datan i exakt den form korten behöver. Priset är en
~60-radersfil att underhålla — litet jämfört med att felsöka samma join i sex kort.

### Komponenter

| Fil / entitet | Syfte |
|---------------|-------|
| `scripts/grocy_kallaren.py` | Läser `grocy_api_key` ur `secrets.yaml`, hämtar `/api/stock` + `/api/objects/products`, joinar, skriver JSON till stdout |
| `sensor.kallaren_grocy` | `command_line`, `scan_interval: 300`. State = antal flaskor, attribut = allt övrigt |
| `sensor.kallaren_flaskor` | Template-sensor på statet, **inkluderad** i recorder → ger trendgraf |
| `rest_command.grocy_consume` | `POST /api/stock/products/{id}/consume` |
| `rest_command.grocy_set_userfields` | `PUT /api/userfields/products/{id}` — betyg + smaknotering |
| `dashboards/kallaren.yaml` | Dashboarden, registreras som `lovelace-kallaren` |

### Skriptets utdata

```json
{
  "bottles": 12, "kinds": 7, "value": 1480.0, "avg_rating": 3.8,
  "n_rott_vin": 6, "n_vitt_vin": 3, "n_rosevin": 0,
  "n_mousserande_vin": 1, "n_ol": 2,
  "by_country": {"Frankrike": 5, "Italien": 4},
  "by_vintage": {"2019": 3, "2020": 5},
  "items": [
    {"id": 7, "name": "...", "group": "Rött vin", "vintage": 2019,
     "grape": "Syrah", "country": "Frankrike", "region": "Rhône",
     "amount": 2, "rating": 4.0, "abv": 13.5, "value": 298.0}
  ]
}
```

`value` per rad tas från `/api/stock`-radens `value` (Grocy räknar redan ut den);
`value` på toppnivå är summan av raderna. Ingen egen pris×antal-multiplikation.

De platta `n_*`-fälten finns **utöver** grupperingen för att apexcharts-korten ska
kunna peka rakt på ett attribut i stället för att gå via `data_generator`.

### Felhantering

Skriptet får aldrig krascha ut i HA. Vid nätverksfel, HTTP-fel eller trasig JSON
skriver det `{"bottles": 0, "kinds": 0, ..., "items": [], "error": "<orsak>"}`.
Korten visar då "Grocy nås inte" och nyckeltalen 0, i stället för `unavailable`.
Tomt bestånd (inga rader, inget fel) ger "Källaren är tom" i stället för en trasig
tabell.

### Databas

`sensor.kallaren_grocy` bär hela `items`-listan som attribut och **exkluderas från
både recorder och InfluxDB** — annars skrivs listan om var 5:e minut och sväller
databasen. Trenden tas i stället från `sensor.kallaren_flaskor`, som bara är ett
tal. Trendhistoriken börjar den dag sensorn skapas; ingen data bakåt finns.

## 4. Dashboarden

Registreras i `configuration.yaml` under `lovelace.dashboards`:
`lovelace-kallaren`, titel "Källaren", ikon `mdi:bottle-wine`,
`filename: dashboards/kallaren.yaml`.

### Vy 1 · Bestånd (standardvy)

- Nyckeltalsrad: antal flaskor, antal sorter, lagervärde.
- Chips-rad från `input_select.kallaren_filter` med valen
  `Allt / Rött vin / Vitt vin / Rosévin / Mousserande vin / Öl`. Aktivt val
  markeras.
- Markdown-kort som itererar `items`, grupperar per typ och renderar
  `Namn | Årgång | Druva | Land | Antal | Betyg` (betyg som ★). Grupper som inte
  matchar filtret hoppas över; `Allt` visar alla.
- Två knappar längst ner: "Lägg till dryck" → `https://dryck.sandholdt.se:8443`,
  "Öppna Grocy" → `https://grocy.sandholdt.se:8443`.

### Vy 2 · Hantera

Två steg som medvetet är separerade:

**Drick upp.** `input_select.kallaren_flaska` fylls av en automation från
beståndet (label `Namn (årgång)`; placeholder `— källaren är tom —` när
beståndet är tomt, och skriptet vägrar köra på placeholdern). Om två rader ger
samma label lägger automationen till ` #<id>` på båda, så uppslaget alltid är
entydigt.
`input_number.kallaren_antal` (1–12, default 1). Knappen kör
`script.kallaren_drick_upp`, som slår upp `product_id` ur `items` via labeln och
anropar `rest_command.grocy_consume`.

**Betygsätt.** Efter konsumtion sparar skriptet flaskan i
`input_text.kallaren_senast_druckit` på formatet `<id>|<namn>` — id:t först så
betygsskriptet kan plocka det utan att gissa, namnet efter så kortet kan visa det.
Betygsblocket rubriceras "Betygsätt: *namn*"
och skriver `input_number.kallaren_betyg` (1–5, steg 0.5) och
`input_text.kallaren_smaknotering` till Grocy via
`rest_command.grocy_set_userfields`.

Stegen är separerade just för att flaskan man vill betygsätta ofta har lämnat
lagret — den finns inte längre i väljaren, men id:t finns kvar i
`input_text.kallaren_senast_druckit`.

### Vy 3 · Statistik

- Donut över fördelning per dryckestyp (apexcharts, en serie per `n_*`-attribut).
- Staplar för flaskor per land och per årgång, renderade i markdown med
  blocktecken. Dessa dimensioner är dynamiska och blir sköra som fasta
  apexcharts-serier.
- Trendgraf på `sensor.kallaren_flaskor`, 30 dagar.
- Snittbetyg och lagervärde som nyckeltal.

### Vy 4 · Grocy

`iframe`-kort mot `https://grocy.sandholdt.se:8443` i full höjd, plus knapp till
dryck-appen. **Reservation:** Grocy svarade inte på HEAD, så `X-Frame-Options` är
overifierat. Om Grocy blockerar inbäddning blir vyn stora länkkort i stället —
det avgörs vid implementationen, inte här.

HTTPS-URL:erna används genomgående; `http://192.168.1.66:9283` skulle blockeras
som mixed content när HA nås över HTTPS.

## 5. Verifiering

1. Kör `scripts/grocy_kallaren.py` från terminalen mot tom källare → giltig JSON.
2. Lägg in tillfälliga testflaskor via API:t (rött, vitt, öl — med årgång, druva,
   land, pris) så alla vyer får data att rendera.
3. `python3 -c "import yaml; yaml.safe_load(...)"` på dashboard-filen.
4. `/config/scripts/ha core check`.
5. Entitetskontroll: alla refererade entiteter finns och har giltigt state
   (skriptet i CLAUDE.md).
6. Skärmdump av alla fyra vyer med `scripts/ha_screenshot.py`.
7. Testa `drick upp` → verifiera att lagret minskade i Grocy; testa betygsättning
   → verifiera att `rating`/`tasting_notes` satts via
   `GET /api/userfields/products/{id}`.
8. Kontrollera att `PUT /api/userfields` inte nollar övriga userfields.
9. **Radera testflaskorna** — bara den befintliga `Test Wine bottle` ska stå kvar.
10. `ha core logs` — inga nya fel.

## 6. Avgränsningar

- Dashboarden **läser** Grocy-schemat; den skapar aldrig grupper, userfields eller
  enheter (dryck-appens bootstrap äger dem).
- Ingen inmatning av nya drycker här — det gör dryck-appen.
- Inget stöd för flera locations; källaren är enda platsen.
- Ingen `hide_on_stock_overview`-hantering, ingen recept-/inköpslistedel.
- Ingen historik över konsumtion utöver "senast druckit".

## 7. Beslut bekräftade med användaren

| Fråga | Beslut |
|-------|--------|
| Dashboardens syfte | Alla fyra delarna — bestånd, hantering, statistik, Grocy-inbäddning — som **separata vyer** |
| Beståndsvyns layout | **Grupperad per dryckestyp + filterknappar** |
| Konsumtionsflöde | **Väljare + knapp + betygsättning** |
| Datalager | **Alternativ A** — command_line-sensor med Python-skript |
