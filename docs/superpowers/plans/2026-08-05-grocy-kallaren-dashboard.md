# Källaren — Grocy-dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** En HA-dashboard "Källaren" med fyra vyer som visar dryckesbeståndet i Grocy med årgång/druva/land/betyg, och som klarar att dricka upp och betygsätta en flaska utan att lämna HA.

**Architecture:** Ett Python-skript (`scripts/grocy_kallaren.py`) joinar Grocys `/api/stock`, `/api/objects/products` (som bär `userfields`), `/api/objects/product_groups` och `/api/objects/locations` till en kompakt JSON som en `command_line`-sensor exponerar — state = antal flaskor, allt övrigt som attribut. Dashboarden läser bara den sensorn. Skrivning tillbaka till Grocy går via två `rest_command` som anropas av två skript i `scripts.yaml`.

**Tech Stack:** Python 3.14 (endast stdlib — `urllib`, `json`, `re`, `unittest`), Home Assistant 2026.7.4 YAML (`command_line`, `template`, `rest_command`, `input_*`, `script`, `automation`), Lovelace YAML-dashboard med mushroom, apexcharts-card och markdown-kort.

## Global Constraints

- **Grocy-schemat får aldrig ändras härifrån.** Produktgrupper, userfields, enheter och locations ägs av dryck-appens bootstrap (`/opt/grocy-scanner`). Denna implementation är read-only mot schemat; den skriver bara `rating`/`tasting_notes` på befintliga produkter och konsumerar lager.
- **Grocy-API:** bas `http://192.168.1.66:9283/api`, header `GROCY-API-KEY`. Nyckeln finns som `grocy_api_key` i `/config/secrets.yaml`. Verifierat: `PUT /api/userfields/products/{id}` **merge:ar** (partiella uppdateringar nollar inte andra fält), och `rating`/`vintage` returneras som **strängar** — måste typomvandlas.
- **Location:** `Källare` har id `3` i dagens Grocy, men id:t får **aldrig hårdkodas i Python** — det slås upp på namnet `Källare`. (I `rest_command.grocy_consume` är `location_id: 3` däremot hårdkodat; se Task 4, steg 1.)
- **`!secret` får aldrig användas i `automations.yaml`** (blockerar UI-editering). I `configuration.yaml` är det obligatoriskt för API-nyckeln.
- **Svenska genomgående** i entitetsnamn, alias, notiser och kort. Entity-ID:n är snake_case med `kallaren_`-prefix.
- **Validering efter varje YAML-ändring:** `/config/scripts/ha core check`.
- **Aldrig `ha core stop`** — Claude kör i ett HA-addon.
- **Ingen `Co-Authored-By: Claude`-trailer** i commit-meddelanden.
- **HTTPS-URL:er i dashboarden** (`https://grocy.sandholdt.se:8443`, `https://dryck.sandholdt.se:8443`) — `http://192.168.1.66:*` blockeras som mixed content när HA nås över HTTPS.

## Avvikelse från specen (medveten förbättring)

Specen lägger dubbletthanteringen (` #<id>` när två flaskor får samma label) i
automationen som fyller väljaren. Planen flyttar den till Python-skriptet, som
skriver ett färdigt `label`-fält på varje item. Skäl: labeln blir då **en** sanning
som både automationen och konsumtionsskriptet läser, i stället för två Jinja-uttryck
som måste hållas identiska. Den blir dessutom enhetstestbar. Automationen blir en
ren `map(attribute='label')`.

## Filstruktur

| Fil | Ansvar | Task |
|-----|--------|------|
| `scripts/grocy_kallaren.py` | Hämtar + joinar Grocy-data → JSON på stdout. Enda stället med joinlogik. | 1 |
| `scripts/test_grocy_kallaren.py` | Enhetstester för joinlogiken (stdlib `unittest`, ingen nätverkstrafik) | 1 |
| `scripts/grocy_testdata.py` | Utvecklarverktyg: `--add`/`--remove` av testflaskor med prefix `ZZ Test ` | 2 |
| `configuration.yaml` | `command_line`-sensor, `rest_command`, `input_select`/`input_number`/`input_text`, recorder-/InfluxDB-excludes, dashboard-registrering | 3, 4, 5 |
| `template_sensors.yaml` | `sensor.kallaren_flaskor` (trendbar kopia av antalet) | 3 |
| `scripts.yaml` | `kallaren_drick_upp`, `kallaren_satt_betyg` | 4 |
| `automations.yaml` | `kallaren_fyll_flaskvaljare` | 4 |
| `dashboards/kallaren.yaml` | De fyra vyerna | 5, 6, 7 |
| `CLAUDE.md` | Dokumentation av dashboard + entiteter | 8 |

---

### Task 1: Joinlogiken — `scripts/grocy_kallaren.py`

**Files:**
- Create: `scripts/grocy_kallaren.py`
- Test: `scripts/test_grocy_kallaren.py`

**Interfaces:**
- Consumes: inget (första tasken)
- Produces:
  - `GROUP_ATTRS: dict[str, str]` — grupp­namn → attributnamn, t.ex. `{"Rött vin": "n_rott_vin", ...}`
  - `build_payload(stock: list[dict], products: list[dict], groups: list[dict], locations: list[dict]) -> dict`
  - `error_payload(reason: str) -> dict`
  - `read_api_key(path: str = SECRETS) -> str`
  - `api_get(path: str, key: str) -> list`
  - `main() -> int`
  - Varje item i `payload["items"]` har nycklarna: `id, name, label, group, vintage, grape, country, region, amount, rating, abv, value`. Task 4–7 läser dessa namn; ändra dem inte utan att uppdatera dashboarden.

- [ ] **Step 1: Skriv de misslyckande testerna**

Create `scripts/test_grocy_kallaren.py`:

```python
#!/usr/bin/env python3
"""Enhetstester för grocy_kallaren.build_payload.

Ingen nätverkstrafik: testerna matar in samma JSON-strukturer som Grocy-API:t
returnerar (verifierade mot http://192.168.1.66:9283 2026-08-05).

Kör: python3 -m unittest discover -s /config/scripts -p "test_grocy_*.py" -v
"""
import unittest

from grocy_kallaren import GROUP_ATTRS, build_payload, error_payload

LOCATIONS = [{"id": 3, "name": "Källare"}]
GROUPS = [
    {"id": 1, "name": "Rött vin"},
    {"id": 2, "name": "Vitt vin"},
    {"id": 7, "name": "Öl"},
]


def stock_row(product_id, amount, value, group_id=1, location_id=3, name="Flaska"):
    """Härmar en rad ur GET /api/stock (produkten ligger nästlad, utan userfields)."""
    return {
        "amount": amount,
        "value": value,
        "product_id": product_id,
        "product": {
            "id": product_id,
            "name": name,
            "location_id": location_id,
            "product_group_id": group_id,
        },
    }


def product(product_id, **userfields):
    """Härmar en rad ur GET /api/objects/products. Grocy ger userfields som strängar."""
    fields = {
        "abv": None, "country": None, "deposit": None, "grape_or_style": None,
        "rating": None, "region": None, "source_url": None,
        "tasting_notes": None, "vintage": None,
    }
    fields.update(userfields)
    return {"id": product_id, "name": f"produkt-{product_id}", "userfields": fields}


class TestBuildPayload(unittest.TestCase):
    def test_tom_kallare_ger_nollor_och_inget_fel(self):
        p = build_payload([], [], GROUPS, LOCATIONS)
        self.assertEqual(p["bottles"], 0)
        self.assertEqual(p["kinds"], 0)
        self.assertEqual(p["items"], [])
        self.assertIsNone(p["error"])
        for attr in GROUP_ATTRS.values():
            self.assertEqual(p[attr], 0, f"{attr} ska vara 0 i tom källare")

    def test_flaska_blir_item_med_typomvandlade_userfields(self):
        p = build_payload(
            [stock_row(5, 2, 298.0, name="Château Test")],
            [product(5, vintage="2019", grape_or_style="Syrah",
                     country="Frankrike", region="Rhône", rating="4", abv="13.5")],
            GROUPS, LOCATIONS,
        )
        item = p["items"][0]
        self.assertEqual(item["id"], 5)
        self.assertEqual(item["name"], "Château Test")
        self.assertEqual(item["group"], "Rött vin")
        self.assertEqual(item["vintage"], 2019)      # sträng "2019" → int
        self.assertEqual(item["rating"], 4.0)        # sträng "4" → float
        self.assertEqual(item["abv"], 13.5)
        self.assertEqual(item["grape"], "Syrah")
        self.assertEqual(item["country"], "Frankrike")
        self.assertEqual(item["amount"], 2)
        self.assertEqual(item["value"], 298.0)
        self.assertEqual(p["bottles"], 2)
        self.assertEqual(p["kinds"], 1)
        self.assertEqual(p["value"], 298.0)

    def test_label_far_arganghang_och_id_vid_dubblett(self):
        p = build_payload(
            [stock_row(1, 1, 100.0, name="Barolo"),
             stock_row(2, 1, 100.0, name="Barolo"),
             stock_row(3, 1, 100.0, name="Rioja")],
            [product(1, vintage="2018"), product(2, vintage="2018"),
             product(3, vintage="2020")],
            GROUPS, LOCATIONS,
        )
        labels = sorted(i["label"] for i in p["items"])
        self.assertEqual(labels, ["Barolo (2018) #1", "Barolo (2018) #2", "Rioja (2020)"])

    def test_label_utan_argang_ar_bara_namnet(self):
        p = build_payload([stock_row(9, 1, 30.0, group_id=7, name="Test IPA")],
                          [product(9)], GROUPS, LOCATIONS)
        self.assertEqual(p["items"][0]["label"], "Test IPA")

    def test_stock_i_annan_location_filtreras_bort(self):
        p = build_payload(
            [stock_row(1, 1, 100.0), stock_row(2, 5, 500.0, location_id=99)],
            [product(1), product(2)], GROUPS, LOCATIONS,
        )
        self.assertEqual(p["bottles"], 1)
        self.assertEqual([i["id"] for i in p["items"]], [1])

    def test_gruppfordelning_hamnar_i_platta_attribut(self):
        p = build_payload(
            [stock_row(1, 3, 300.0, group_id=1), stock_row(2, 2, 200.0, group_id=2),
             stock_row(3, 6, 180.0, group_id=7)],
            [product(1), product(2), product(3)], GROUPS, LOCATIONS,
        )
        self.assertEqual(p["n_rott_vin"], 3)
        self.assertEqual(p["n_vitt_vin"], 2)
        self.assertEqual(p["n_ol"], 6)
        self.assertEqual(p["n_rosevin"], 0)

    def test_okand_grupp_hamnar_i_ovrigt_och_i_groups(self):
        p = build_payload([stock_row(1, 1, 100.0, group_id=None)],
                          [product(1)], GROUPS, LOCATIONS)
        self.assertEqual(p["items"][0]["group"], "Övrigt")
        self.assertIn("Övrigt", p["groups"])

    def test_by_country_och_by_vintage_summerar_antal_fallande(self):
        p = build_payload(
            [stock_row(1, 2, 200.0), stock_row(2, 5, 500.0), stock_row(3, 1, 100.0)],
            [product(1, country="Italien", vintage="2019"),
             product(2, country="Frankrike", vintage="2019"),
             product(3, country="Italien", vintage="2021")],
            GROUPS, LOCATIONS,
        )
        self.assertEqual(p["by_country"], {"Frankrike": 5, "Italien": 3})
        self.assertEqual(list(p["by_country"])[0], "Frankrike")  # sorterad fallande
        self.assertEqual(p["by_vintage"], {"2019": 7, "2021": 1})

    def test_avg_rating_ignorerar_flaskor_utan_betyg(self):
        p = build_payload(
            [stock_row(1, 1, 100.0), stock_row(2, 1, 100.0), stock_row(3, 1, 100.0)],
            [product(1, rating="4"), product(2, rating="3"), product(3)],
            GROUPS, LOCATIONS,
        )
        self.assertEqual(p["avg_rating"], 3.5)

    def test_saknad_kallarlocation_ger_felpayload(self):
        p = build_payload([], [], GROUPS, [{"id": 1, "name": "Kylen"}])
        self.assertIn("Källare", p["error"])
        self.assertEqual(p["bottles"], 0)


class TestErrorPayload(unittest.TestCase):
    def test_felpayload_har_alla_nycklar_som_korten_laser(self):
        p = error_payload("URLError: timeout")
        for key in ("bottles", "kinds", "value", "avg_rating", "groups",
                    "by_country", "by_vintage", "items", "error",
                    *GROUP_ATTRS.values()):
            self.assertIn(key, p, f"kortet läser {key} — måste finnas även vid fel")
        self.assertEqual(p["error"], "URLError: timeout")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Kör testerna och verifiera att de misslyckas**

```bash
cd /config/scripts && python3 -m unittest discover -s . -p "test_grocy_*.py" -v
```

Expected: `ModuleNotFoundError: No module named 'grocy_kallaren'`

- [ ] **Step 3: Skriv implementationen**

Create `scripts/grocy_kallaren.py`:

```python
#!/usr/bin/env python3
"""Läser dryckesbeståndet i Grocy-källaren och skriver kompakt JSON till stdout.

Anropas var 5:e minut av command_line-sensorn sensor.kallaren_grocy
(configuration.yaml). Felsök genom att köra den för hand:

    python3 /config/scripts/grocy_kallaren.py | python3 -m json.tool

Varför skriptet finns: Grocy-integrationen i HA exponerar INTE produkternas
userfields (årgång, druva, land, betyg), och de fälten är hela poängen med
dashboarden. /api/objects/products bär dem, så vi joinar själva.

Skriptet skriver ALDRIG till Grocy och ändrar aldrig schemat.
"""
from __future__ import annotations

import json
import re
import sys
import urllib.request

BASE_URL = "http://192.168.1.66:9283/api"
SECRETS = "/config/secrets.yaml"
LOCATION_NAME = "Källare"
TIMEOUT = 10

# Grupperna ägs av dryck-appens bootstrap. Attributnamnen till höger är exakt
# vad apexcharts-serierna i dashboards/kallaren.yaml pekar på — byt inte namn
# på ena sidan utan den andra.
GROUP_ATTRS = {
    "Rött vin": "n_rott_vin",
    "Vitt vin": "n_vitt_vin",
    "Rosévin": "n_rosevin",
    "Mousserande vin": "n_mousserande_vin",
    "Öl": "n_ol",
}
UNKNOWN_GROUP = "Övrigt"


def read_api_key(path: str = SECRETS) -> str:
    """Plockar grocy_api_key ur secrets.yaml utan att dra in pyyaml."""
    with open(path, encoding="utf-8") as handle:
        match = re.search(r'^grocy_api_key:\s*"?([^"\s]+)"?', handle.read(), re.M)
    if not match:
        raise RuntimeError("grocy_api_key saknas i secrets.yaml")
    return match.group(1)


def api_get(path: str, key: str) -> list:
    request = urllib.request.Request(
        f"{BASE_URL}{path}", headers={"GROCY-API-KEY": key, "Accept": "application/json"}
    )
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        return json.load(response)


def to_float(value) -> float | None:
    """Grocy ger userfields som strängar ("4", "13.5") och tomt som None/""."""
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def to_int(value) -> int | None:
    number = to_float(value)
    return None if number is None else int(number)


def _apply_labels(items: list[dict]) -> None:
    """Sätter ett unikt label per item: "Namn (årgång)", med " #id" vid dubblett.

    Labeln är den enda kopplingen mellan input_select.kallaren_flaska och
    produkt-id:t, så den måste vara entydig.
    """
    buckets: dict[str, list[dict]] = {}
    for item in items:
        base = f"{item['name']} ({item['vintage']})" if item["vintage"] else item["name"]
        buckets.setdefault(base, []).append(item)
    for base, bucket in buckets.items():
        for item in bucket:
            item["label"] = base if len(bucket) == 1 else f"{base} #{item['id']}"


def _count_by(items: list[dict], field: str) -> dict[str, int]:
    """Summerar antal per värde av ett fält, sorterat fallande. Tomma hoppas över."""
    totals: dict[str, int] = {}
    for item in items:
        value = item.get(field)
        if value in (None, ""):
            continue
        totals[str(value)] = totals.get(str(value), 0) + int(item["amount"])
    return dict(sorted(totals.items(), key=lambda pair: (-pair[1], pair[0])))


def error_payload(reason: str) -> dict:
    """Samma nycklar som en lyckad körning, så inget kort går sönder vid fel."""
    payload = {
        "bottles": 0,
        "kinds": 0,
        "value": 0.0,
        "avg_rating": None,
        "groups": list(GROUP_ATTRS),
        "by_country": {},
        "by_vintage": {},
        "items": [],
        "error": reason,
    }
    payload.update({attr: 0 for attr in GROUP_ATTRS.values()})
    return payload


def build_payload(stock: list, products: list, groups: list, locations: list) -> dict:
    location_id = next(
        (to_int(loc.get("id")) for loc in locations if loc.get("name") == LOCATION_NAME),
        None,
    )
    if location_id is None:
        return error_payload(f'location "{LOCATION_NAME}" finns inte i Grocy')

    group_names = {to_int(g.get("id")): g.get("name") for g in groups}
    userfields = {to_int(p.get("id")): (p.get("userfields") or {}) for p in products}

    items: list[dict] = []
    for row in stock:
        product = row.get("product") or {}
        if to_int(product.get("location_id")) != location_id:
            continue
        product_id = to_int(product.get("id"))
        fields = userfields.get(product_id, {})
        items.append({
            "id": product_id,
            "name": product.get("name") or "(namnlös)",
            "group": group_names.get(to_int(product.get("product_group_id"))) or UNKNOWN_GROUP,
            "vintage": to_int(fields.get("vintage")),
            "grape": fields.get("grape_or_style") or "",
            "country": fields.get("country") or "",
            "region": fields.get("region") or "",
            "amount": int(to_float(row.get("amount")) or 0),
            "rating": to_float(fields.get("rating")),
            "abv": to_float(fields.get("abv")),
            "value": round(to_float(row.get("value")) or 0.0, 2),
        })

    _apply_labels(items)
    items.sort(key=lambda item: (item["group"], item["name"]))

    ratings = [item["rating"] for item in items if item["rating"] is not None]
    # Grupperna i GROUP_ATTRS visas alltid (även tomma, så donuten är stabil);
    # oväntade grupper läggs sist så inget bestånd blir osynligt i vy 1.
    extra = [item["group"] for item in items if item["group"] not in GROUP_ATTRS]

    payload = {
        "bottles": sum(item["amount"] for item in items),
        "kinds": len(items),
        "value": round(sum(item["value"] for item in items), 2),
        "avg_rating": round(sum(ratings) / len(ratings), 1) if ratings else None,
        "groups": list(GROUP_ATTRS) + sorted(set(extra)),
        "by_country": _count_by(items, "country"),
        "by_vintage": _count_by(items, "vintage"),
        "items": items,
        "error": None,
    }
    for name, attr in GROUP_ATTRS.items():
        payload[attr] = sum(i["amount"] for i in items if i["group"] == name)
    return payload


def main() -> int:
    try:
        key = read_api_key()
        payload = build_payload(
            api_get("/stock", key),
            api_get("/objects/products", key),
            api_get("/objects/product_groups", key),
            api_get("/objects/locations", key),
        )
    except Exception as err:  # nätverk, HTTP, trasig JSON, saknad nyckel
        payload = error_payload(f"{type(err).__name__}: {err}")
    json.dump(payload, sys.stdout, ensure_ascii=False, separators=(",", ":"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Kör testerna och verifiera att de passerar**

```bash
cd /config/scripts && python3 -m unittest discover -s . -p "test_grocy_*.py" -v
```

Expected: `OK` — 11 tester.

- [ ] **Step 5: Kör mot riktiga Grocy och verifiera giltig JSON**

```bash
python3 /config/scripts/grocy_kallaren.py | python3 -m json.tool
```

Expected: `"error": null`, `"bottles": 1`, `"kinds": 1` och ett item `Test Wine bottle` i gruppen `Övrigt` (produkten saknar `product_group_id`).

- [ ] **Step 6: Verifiera felhanteringen**

```bash
python3 -c "
import grocy_kallaren as g
g.BASE_URL = 'http://192.168.1.66:9999/api'   # ingen lyssnar här
print(g.main())
" 2>&1 | tail -2
```
Kör från `/config/scripts`. Expected: giltig JSON med `"bottles":0` och ett `"error"` som börjar med `URLError`. Ingen traceback, exit 0.

- [ ] **Step 7: Commit**

```bash
cd /config
git add scripts/grocy_kallaren.py scripts/test_grocy_kallaren.py
git commit -m "feat: skript som läser Grocy-källarens bestånd till JSON"
```

---

### Task 2: Testdata-verktyg — `scripts/grocy_testdata.py`

Källaren innehåller bara en namnlös testflaska, så vy 1–3 skulle rendera tomma.
Detta verktyg lägger in fyra realistiska flaskor så varje vy kan verifieras, och
tar bort dem igen med ett kommando. Prefixet `ZZ Test ` gör städningen entydig och
kan aldrig råka träffa en riktig flaska.

**Files:**
- Create: `scripts/grocy_testdata.py`

**Interfaces:**
- Consumes: `read_api_key`, `BASE_URL`, `TIMEOUT` från `grocy_kallaren`
- Produces: CLI `python3 scripts/grocy_testdata.py --add|--remove|--list`. `NAME_PREFIX = "ZZ Test "`.

- [ ] **Step 1: Skriv verktyget**

Create `scripts/grocy_testdata.py`:

```python
#!/usr/bin/env python3
"""Lägger in / tar bort testflaskor i Grocy-källaren.

Endast ett utvecklingsverktyg — används för att verifiera dashboardens vyer och
körs aldrig av HA. Alla produkter får prefixet "ZZ Test " så att --remove aldrig
kan träffa en riktig flaska.

    python3 /config/scripts/grocy_testdata.py --add
    python3 /config/scripts/grocy_testdata.py --list
    python3 /config/scripts/grocy_testdata.py --remove
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.request

from grocy_kallaren import BASE_URL, TIMEOUT, api_get, read_api_key, to_float, to_int

NAME_PREFIX = "ZZ Test "

# (namn, grupp, enhet, antal, pris, userfields)
FIXTURES = [
    ("Barolo Riserva", "Rött vin", "Flaska", 3, 249.0,
     {"vintage": 2018, "grape_or_style": "Nebbiolo", "country": "Italien",
      "region": "Piemonte", "abv": 14.0, "rating": 4.5}),
    ("Chablis Premier Cru", "Vitt vin", "Flaska", 2, 189.0,
     {"vintage": 2021, "grape_or_style": "Chardonnay", "country": "Frankrike",
      "region": "Bourgogne", "abv": 12.5, "rating": 4.0}),
    ("Rhône Rosé", "Rosévin", "Flaska", 1, 129.0,
     {"vintage": 2022, "grape_or_style": "Grenache", "country": "Frankrike",
      "region": "Rhône", "abv": 12.0}),
    ("Hazy IPA", "Öl", "Burk", 6, 32.0,
     {"grape_or_style": "New England IPA", "country": "Sverige",
      "abv": 6.2, "rating": 3.5}),
]


def api(method: str, path: str, key: str, body: dict | None = None):
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(
        f"{BASE_URL}{path}", data=data, method=method,
        headers={"GROCY-API-KEY": key, "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        raw = response.read()
    return json.loads(raw) if raw else None


def lookup(key: str) -> tuple[dict, dict, dict]:
    """Namn → id för locations, produktgrupper och enheter."""
    return (
        {loc["name"]: to_int(loc["id"]) for loc in api_get("/objects/locations", key)},
        {grp["name"]: to_int(grp["id"]) for grp in api_get("/objects/product_groups", key)},
        {qu["name"]: to_int(qu["id"]) for qu in api_get("/objects/quantity_units", key)},
    )


def test_products(key: str) -> list[dict]:
    return [p for p in api_get("/objects/products", key)
            if (p.get("name") or "").startswith(NAME_PREFIX)]


def add(key: str) -> None:
    locations, groups, units = lookup(key)
    if "Källare" not in locations:
        sys.exit('FEL: location "Källare" finns inte i Grocy')
    for name, group, unit, amount, price, fields in FIXTURES:
        if group not in groups:
            sys.exit(f'FEL: produktgruppen "{group}" finns inte — skapa den i dryck-appen, inte här')
        if unit not in units:
            sys.exit(f'FEL: enheten "{unit}" finns inte i Grocy')
        created = api("POST", "/objects/products", key, {
            "name": f"{NAME_PREFIX}{name}",
            "location_id": locations["Källare"],
            "product_group_id": groups[group],
            "qu_id_stock": units[unit],
            "qu_id_purchase": units[unit],
            "qu_id_consume": units[unit],
            "qu_id_price": units[unit],
        })
        product_id = to_int(created["created_object_id"])
        api("PUT", f"/userfields/products/{product_id}", key, fields)
        api("POST", f"/stock/products/{product_id}/add", key, {
            "amount": amount, "price": price, "best_before_date": "2999-12-31",
            "location_id": locations["Källare"],
        })
        print(f"+ {NAME_PREFIX}{name} (id {product_id}, {amount} {unit.lower()})")


def remove(key: str) -> None:
    """Konsumerar bort lagret först — Grocy vägrar radera produkter med lager."""
    found = test_products(key)
    if not found:
        print("Inga testprodukter att ta bort.")
        return
    in_stock = {to_int(row["product_id"]): to_float(row["amount"]) or 0
                for row in api_get("/stock", key)}
    for product in found:
        product_id = to_int(product["id"])
        amount = in_stock.get(product_id, 0)
        if amount:
            api("POST", f"/stock/products/{product_id}/consume", key,
                {"amount": amount, "transaction_type": "consume"})
        api("DELETE", f"/objects/products/{product_id}", key)
        print(f"- {product['name']} (id {product_id})")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--add", action="store_true", help="lägg in testflaskorna")
    group.add_argument("--remove", action="store_true", help="ta bort alla ZZ Test-produkter")
    group.add_argument("--list", action="store_true", help="visa vilka som finns")
    args = parser.parse_args()

    key = read_api_key()
    if args.add:
        add(key)
    elif args.remove:
        remove(key)
    else:
        for product in test_products(key):
            print(f"{product['id']}\t{product['name']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Lägg in testdatan och verifiera**

```bash
cd /config/scripts && python3 grocy_testdata.py --add && python3 grocy_testdata.py --list
```

Expected: fyra `+`-rader, sedan fyra id/namn-rader.

- [ ] **Step 3: Verifiera att joinen ser datan**

```bash
python3 /config/scripts/grocy_kallaren.py | python3 -m json.tool | head -30
```

Expected: `"bottles": 13` (3+2+1+6, plus 1 för `Test Wine bottle` = 13), `"kinds": 5`,
`"n_rott_vin": 3`, `"n_ol": 6`, och `by_country` med Frankrike högst.

- [ ] **Step 4: Verifiera att borttagningen är fullständig, och lägg tillbaka**

```bash
cd /config/scripts && python3 grocy_testdata.py --remove && python3 grocy_testdata.py --list && python3 grocy_testdata.py --add
```

Expected: fyra `-`-rader, sedan **ingen** utskrift från `--list`, sedan fyra `+`-rader.
Om `--remove` ger HTTP 400 på DELETE: lagret konsumerades inte bort — felsök
`consume`-anropet innan du går vidare, annars går inte städningen i Task 8.

- [ ] **Step 5: Commit**

```bash
cd /config
git add scripts/grocy_testdata.py
git commit -m "feat: verktyg för test-testflaskor i Grocy-källaren"
```

---

### Task 3: HA-sensorerna

**Files:**
- Modify: `configuration.yaml` — `command_line:`-listan (efter `Git Status`, rad ~323), recorder `exclude.entities` (~rad 461), InfluxDB `exclude.entities` (~rad 515)
- Modify: `template_sensors.yaml` — nytt `- sensor:`-block sist i filen

**Interfaces:**
- Consumes: `scripts/grocy_kallaren.py` från Task 1
- Produces: `sensor.kallaren_grocy` (state = antal flaskor; attribut `kinds, value, avg_rating, groups, by_country, by_vintage, items, error, n_rott_vin, n_vitt_vin, n_rosevin, n_mousserande_vin, n_ol`) och `sensor.kallaren_flaskor` (bara talet, med `state_class: measurement`). Task 4–7 läser dessa.

- [ ] **Step 1: Lägg till command_line-sensorn**

I `configuration.yaml`, direkt efter `Git Status`-sensorns `scan_interval: 300` och före den tomma raden som följs av `rest_command:`:

```yaml
  # Källaren: dryckesbeståndet i Grocy. Skriptet joinar stock + produkter (som
  # bär userfields) + grupper + locations — Grocy-integrationen exponerar inte
  # userfields, så årgång/druva/land/betyg finns inte att få den vägen.
  # State = antal flaskor, allt övrigt i attributen. Sensorn är exkluderad från
  # recorder och InfluxDB längre ner: items-listan skrivs om var 5:e minut och
  # skulle svälla databasen. Trend tas från sensor.kallaren_flaskor i stället.
  - sensor:
      name: "Källaren Grocy"
      unique_id: kallaren_grocy
      command: "python3 /config/scripts/grocy_kallaren.py"
      value_template: "{{ value_json.bottles }}"
      unit_of_measurement: "flaskor"
      json_attributes:
        - kinds
        - value
        - avg_rating
        - groups
        - by_country
        - by_vintage
        - items
        - error
        - n_rott_vin
        - n_vitt_vin
        - n_rosevin
        - n_mousserande_vin
        - n_ol
      scan_interval: 300
      command_timeout: 60
```

- [ ] **Step 2: Lägg till trendsensorn**

Sist i `template_sensors.yaml`:

```yaml
# =============================================================================
# KÄLLAREN - trendbar kopia av flaskantalet
# =============================================================================
# sensor.kallaren_grocy är exkluderad från recorder (stor items-lista i
# attributen). Den här sensorn är bara talet, så den kan sparas och ge
# statistics-graph i dashboardens statistikvy. Historiken börjar den dag
# sensorn skapas — ingen data bakåt finns.
- sensor:
    - name: "Källaren flaskor"
      unique_id: kallaren_flaskor
      unit_of_measurement: "flaskor"
      state_class: measurement
      icon: mdi:bottle-wine
      state: "{{ states('sensor.kallaren_grocy') | int(0) }}"
      availability: "{{ states('sensor.kallaren_grocy') not in ['unknown', 'unavailable'] }}"
```

- [ ] **Step 3: Exkludera attributsensorn från recorder och InfluxDB**

I `configuration.yaml`, i recorder-blockets `exclude.entities`-lista, efter `- sensor.time_utc`:

```yaml
      # Källaren: bär hela items-listan som attribut, skrivs om var 5:e min.
      # Trend finns i sensor.kallaren_flaskor i stället.
      - sensor.kallaren_grocy
```

Och i InfluxDB-blockets `exclude.entities`-lista, efter `- sensor.date_time_iso`:

```yaml
      - sensor.kallaren_grocy   # stor attributlista, se recorder-excluden
```

- [ ] **Step 4: Validera konfigurationen**

```bash
/config/scripts/ha core check
```

Expected: `Configuration testing... valid` (eller motsvarande OK-utskrift). Vid fel — rätta YAML-indenteringen innan du går vidare.

- [ ] **Step 5: Starta om HA och verifiera sensorerna**

```bash
/config/scripts/ha core restart
```

Vänta tills HA svarar igen, sedan:

```bash
/config/scripts/ha state sensor.kallaren_grocy
/config/scripts/ha state sensor.kallaren_flaskor
```

Expected: `sensor.kallaren_grocy` = `13` med attributen ifyllda (`items` med 5 poster,
`error: None`); `sensor.kallaren_flaskor` = `13`.

- [ ] **Step 6: Verifiera att inga fel loggas**

```bash
/config/scripts/ha core logs 300 | grep -i "kallaren\|command_line" | head
```

Expected: ingen träff på `Error`/`Timeout`. En `command_line`-varning om att kommandot
tog lång tid är godtagbar; ett fel är inte det.

- [ ] **Step 7: Commit**

```bash
cd /config
git add configuration.yaml template_sensors.yaml
git commit -m "feat: sensorer för Grocy-källarens bestånd"
```

---

### Task 4: Skrivvägen — konsumera och betygsätta

**Files:**
- Modify: `configuration.yaml` — `rest_command:`-blocket (~rad 325), nytt `input_select:`-block, `input_number:`-blocket (~rad 149), nytt `input_text:`-block
- Modify: `scripts.yaml`
- Modify: `automations.yaml`

**Interfaces:**
- Consumes: `sensor.kallaren_grocy` med `items[].label` och `items[].id` från Task 1 och 3
- Produces:
  - `rest_command.grocy_consume(product_id, amount)`
  - `rest_command.grocy_set_userfields(product_id, rating, notes)`
  - `input_select.kallaren_filter` (`Allt`/gruppnamnen), `input_select.kallaren_flaska`
  - `input_number.kallaren_antal` (1–12), `input_number.kallaren_betyg` (1–5, steg 0.5)
  - `input_text.kallaren_smaknotering`, `input_text.kallaren_senast_druckit` (format `<id>|<namn>`)
  - `script.kallaren_drick_upp`, `script.kallaren_satt_betyg`
  - `automation` med id `kallaren_fyll_flaskvaljare`
  - Task 5–7 refererar alla dessa entity-id:n.

- [ ] **Step 1: Lägg till rest_commands**

I `configuration.yaml`, i `rest_command:`-blocket efter `birdhouse_clip_end`:

```yaml
  # Källaren: dricka upp en flaska. location_id 3 = Källare. Id:t är hårdkodat
  # här (rest_command kan inte slå upp något) — om locationen någon gång får ett
  # nytt id syns det som att konsumtionen inte gör något, och skriptet
  # grocy_kallaren.py börjar samtidigt returnera ett tydligt fel.
  grocy_consume:
    url: "http://192.168.1.66:9283/api/stock/products/{{ product_id }}/consume"
    method: POST
    content_type: "application/json"
    headers:
      GROCY-API-KEY: !secret grocy_api_key
    payload: '{"amount": {{ amount | int(1) }}, "transaction_type": "consume", "location_id": 3}'
  # Källaren: sätta betyg + smaknotering. PUT på userfields MERGE:ar i Grocy
  # (verifierat 2026-08-05) — övriga fält som årgång och druva rörs inte.
  grocy_set_userfields:
    url: "http://192.168.1.66:9283/api/userfields/products/{{ product_id }}"
    method: PUT
    content_type: "application/json"
    headers:
      GROCY-API-KEY: !secret grocy_api_key
    payload: '{"rating": {{ rating | float(3) }}, "tasting_notes": {{ notes | to_json }}}'
```

- [ ] **Step 2: Lägg till helpers**

I `configuration.yaml`, direkt efter `input_boolean:`-blocket (före `utility_meter:`):

```yaml
# =============================================================================
# INPUT SELECT
# =============================================================================
input_select:
  # Filtret i källardashboardens beståndsvy. Alternativen måste matcha
  # produktgruppernas namn i Grocy exakt (de ägs av dryck-appens bootstrap).
  kallaren_filter:
    name: "Källaren filter"
    icon: mdi:filter-variant
    options:
      - "Allt"
      - "Rött vin"
      - "Vitt vin"
      - "Rosévin"
      - "Mousserande vin"
      - "Öl"
    initial: "Allt"
  # Fylls automatiskt av automationen kallaren_fyll_flaskvaljare från
  # sensor.kallaren_grocy. Placeholdern nedan är startvärdet innan sensorn
  # hunnit läsa (input_select kräver minst ett alternativ).
  kallaren_flaska:
    name: "Källaren flaska"
    icon: mdi:bottle-wine-outline
    options:
      - "— källaren är tom —"

# =============================================================================
# INPUT TEXT
# =============================================================================
input_text:
  kallaren_smaknotering:
    name: "Källaren smaknotering"
    icon: mdi:note-text-outline
    min: 0
    max: 255
  # Format: "<produkt-id>|<namn>". Sätts av script.kallaren_drick_upp så att
  # betygsättningen fungerar även när flaskan lämnat lagret och därmed
  # försvunnit ur väljaren.
  kallaren_senast_druckit:
    name: "Källaren senast druckit"
    icon: mdi:history
    min: 0
    max: 255
```

Och i det befintliga `input_number:`-blocket, efter `igrill_maltemperatur`:

```yaml
  kallaren_antal:
    name: "Källaren antal att dricka upp"
    icon: mdi:numeric
    min: 1
    max: 12
    step: 1
    initial: 1

  kallaren_betyg:
    name: "Källaren betyg"
    icon: mdi:star
    min: 1
    max: 5
    step: 0.5
    initial: 3
```

- [ ] **Step 3: Lägg till skripten**

Sist i `scripts.yaml`:

```yaml
# =============================================================================
# KÄLLAREN
# =============================================================================
kallaren_drick_upp:
  alias: "Källaren - Drick upp flaska"
  description: "Konsumerar valda flaskan i Grocy och kommer ihåg den för betygsättning"
  icon: mdi:glass-wine
  mode: single
  sequence:
    - variables:
        # Labeln i väljaren byggs av grocy_kallaren.py och är unik per produkt.
        flaska: >
          {{ (state_attr('sensor.kallaren_grocy', 'items') or [])
             | selectattr('label', 'eq', states('input_select.kallaren_flaska'))
             | list | first | default(none, true) }}
    # Stoppar tyst på placeholdern "— källaren är tom —" och om beståndet
    # ändrats sedan väljaren fylldes.
    - condition: template
      value_template: "{{ flaska is mapping }}"
    - action: rest_command.grocy_consume
      data:
        product_id: "{{ flaska.id }}"
        amount: "{{ states('input_number.kallaren_antal') | int(1) }}"
    - action: input_text.set_value
      target:
        entity_id: input_text.kallaren_senast_druckit
      data:
        value: "{{ flaska.id }}|{{ flaska.name }}"
    # Hämta beståndet direkt i stället för att vänta på nästa 5-minutersavläsning.
    - action: homeassistant.update_entity
      target:
        entity_id: sensor.kallaren_grocy

kallaren_satt_betyg:
  alias: "Källaren - Sätt betyg på senast druckna"
  description: "Skriver betyg och smaknotering till Grocys userfields"
  icon: mdi:star-outline
  mode: single
  sequence:
    - variables:
        product_id: "{{ states('input_text.kallaren_senast_druckit').split('|')[0] | int(0) }}"
    - condition: template
      value_template: "{{ product_id > 0 }}"
    - action: rest_command.grocy_set_userfields
      data:
        product_id: "{{ product_id }}"
        rating: "{{ states('input_number.kallaren_betyg') | float(3) }}"
        notes: "{{ states('input_text.kallaren_smaknotering') }}"
    - action: input_text.set_value
      target:
        entity_id: input_text.kallaren_smaknotering
      data:
        value: ""
    - action: homeassistant.update_entity
      target:
        entity_id: sensor.kallaren_grocy
```

- [ ] **Step 4: Lägg till automationen som fyller väljaren**

Sist i `automations.yaml` (inget `!secret` här — det blockerar UI-editering):

```yaml
- id: kallaren_fyll_flaskvaljare
  alias: Källaren - Fyll flaskväljaren
  description: Håller input_select.kallaren_flaska i synk med beståndet i Grocy
  triggers:
    - trigger: state
      entity_id: sensor.kallaren_grocy
    - trigger: homeassistant
      event: start
  conditions: []
  actions:
    - variables:
        labels: >
          {{ (state_attr('sensor.kallaren_grocy', 'items') or [])
             | map(attribute='label') | list }}
    - action: input_select.set_options
      target:
        entity_id: input_select.kallaren_flaska
      data:
        # input_select kräver minst ett alternativ, därav placeholdern.
        options: "{{ labels if labels | count > 0 else ['— källaren är tom —'] }}"
  mode: single
```

- [ ] **Step 5: Validera och starta om**

```bash
/config/scripts/ha core check && /config/scripts/ha core restart
```

Expected: konfigurationen giltig, HA startar.

- [ ] **Step 6: Verifiera att väljaren fylldes**

```bash
/config/scripts/ha state input_select.kallaren_flaska
```

Expected: attributet `options` innehåller fem labels, t.ex. `ZZ Test Barolo Riserva (2018)`
och `ZZ Test Hazy IPA`. Om den bara har placeholdern: trigga automationen manuellt med
`/config/scripts/ha call automation.trigger '{"entity_id":"automation.kallaren_fyll_flaskvaljare"}'`
och läs `ha core logs` efter template-fel.

- [ ] **Step 7: Verifiera konsumtionen mot Grocy**

```bash
/config/scripts/ha call input_select.select_option '{"entity_id":"input_select.kallaren_flaska","option":"ZZ Test Hazy IPA"}'
/config/scripts/ha call input_number.set_value '{"entity_id":"input_number.kallaren_antal","value":2}'
/config/scripts/ha call script.kallaren_drick_upp '{}'
sleep 5 && /config/scripts/ha state sensor.kallaren_grocy | head -5
```

Expected: `n_ol` gick från 6 till 4 och `bottles` minskade med 2. Kontrollera även att
`input_text.kallaren_senast_druckit` nu är `<id>|ZZ Test Hazy IPA`:

```bash
/config/scripts/ha state input_text.kallaren_senast_druckit
```

- [ ] **Step 8: Verifiera betygsättningen mot Grocy**

```bash
/config/scripts/ha call input_number.set_value '{"entity_id":"input_number.kallaren_betyg","value":4.5}'
/config/scripts/ha call input_text.set_value '{"entity_id":"input_text.kallaren_smaknotering","value":"Grumlig, citrus, testnotering"}'
/config/scripts/ha call script.kallaren_satt_betyg '{}'
sleep 3
ID=$(/config/scripts/ha state input_text.kallaren_senast_druckit | grep -o '"state": "[0-9]*' | grep -o '[0-9]*')
curl -s -H "GROCY-API-KEY: $(grep -oP '^grocy_api_key:\s*"?\K[^"]+' /config/secrets.yaml)" \
  "http://192.168.1.66:9283/api/userfields/products/$ID"
```

Expected: `"rating":"4.5"`, `"tasting_notes":"Grumlig, citrus, testnotering"` — **och**
`"grape_or_style":"New England IPA"`, `"country":"Sverige"`, `"abv":"6.2"` kvar orörda.
Det sista är hela poängen: PUT ska merge:a, inte ersätta. Om de nollades — sluta här
och gör om `grocy_set_userfields` så den läser befintliga fält först och skickar allt.

- [ ] **Step 9: Commit**

```bash
cd /config
git add configuration.yaml scripts.yaml automations.yaml
git commit -m "feat: konsumera och betygsätta källarflaskor från HA"
```

---

### Task 5: Dashboard vy 1 — Bestånd

**Files:**
- Create: `dashboards/kallaren.yaml`
- Modify: `configuration.yaml` — `lovelace.dashboards` (~rad 60, efter `lovelace-holk`)

**Interfaces:**
- Consumes: `sensor.kallaren_grocy` (attribut `items`, `groups`, `kinds`, `value`, `error`), `input_select.kallaren_filter`
- Produces: dashboarden `lovelace-kallaren` med vy `path: bestand`. Task 6 och 7 lägger till fler vyer i samma fil.

- [ ] **Step 1: Skapa dashboardfilen med beståndsvyn**

Create `dashboards/kallaren.yaml`:

```yaml
# =============================================================================
# KÄLLAREN - dryckesbestånd ur Grocy
# =============================================================================
# All data kommer från sensor.kallaren_grocy (command_line-sensor som kör
# scripts/grocy_kallaren.py). Attributnamnen nedan är definierade i det
# skriptet — ändra aldrig på ena stället utan det andra.
# Inmatning av nya drycker sker i dryck-appen, inte här.
# =============================================================================
title: Källaren
views:
  - title: Bestånd
    path: bestand
    icon: mdi:bottle-wine
    cards:
      - type: horizontal-stack
        cards:
          - type: custom:mushroom-template-card
            primary: "{{ states('sensor.kallaren_grocy') }}"
            secondary: Flaskor
            icon: mdi:bottle-wine
            icon_color: purple
            tap_action:
              action: none
          - type: custom:mushroom-template-card
            primary: "{{ state_attr('sensor.kallaren_grocy', 'kinds') or 0 }}"
            secondary: Sorter
            icon: mdi:format-list-bulleted
            icon_color: blue
            tap_action:
              action: none
          - type: custom:mushroom-template-card
            primary: "{{ (state_attr('sensor.kallaren_grocy', 'value') or 0) | round(0) }} kr"
            secondary: Lagervärde
            icon: mdi:cash
            icon_color: green
            tap_action:
              action: none

      # Filterchips. En chip per alternativ i input_select.kallaren_filter;
      # aktivt val lyser, övriga är grå.
      - type: custom:mushroom-chips-card
        alignment: center
        chips:
          - type: template
            icon: mdi:select-all
            content: Allt
            icon_color: "{{ 'purple' if is_state('input_select.kallaren_filter', 'Allt') else 'disabled' }}"
            tap_action:
              action: perform-action
              perform_action: input_select.select_option
              target:
                entity_id: input_select.kallaren_filter
              data:
                option: Allt
          - type: template
            icon: mdi:glass-wine
            content: Rött
            icon_color: "{{ 'red' if is_state('input_select.kallaren_filter', 'Rött vin') else 'disabled' }}"
            tap_action:
              action: perform-action
              perform_action: input_select.select_option
              target:
                entity_id: input_select.kallaren_filter
              data:
                option: Rött vin
          - type: template
            icon: mdi:glass-wine
            content: Vitt
            icon_color: "{{ 'amber' if is_state('input_select.kallaren_filter', 'Vitt vin') else 'disabled' }}"
            tap_action:
              action: perform-action
              perform_action: input_select.select_option
              target:
                entity_id: input_select.kallaren_filter
              data:
                option: Vitt vin
          - type: template
            icon: mdi:glass-cocktail
            content: Rosé
            icon_color: "{{ 'pink' if is_state('input_select.kallaren_filter', 'Rosévin') else 'disabled' }}"
            tap_action:
              action: perform-action
              perform_action: input_select.select_option
              target:
                entity_id: input_select.kallaren_filter
              data:
                option: Rosévin
          - type: template
            icon: mdi:glass-flute
            content: Mousserande
            icon_color: "{{ 'yellow' if is_state('input_select.kallaren_filter', 'Mousserande vin') else 'disabled' }}"
            tap_action:
              action: perform-action
              perform_action: input_select.select_option
              target:
                entity_id: input_select.kallaren_filter
              data:
                option: Mousserande vin
          - type: template
            icon: mdi:beer
            content: Öl
            icon_color: "{{ 'orange' if is_state('input_select.kallaren_filter', 'Öl') else 'disabled' }}"
            tap_action:
              action: perform-action
              perform_action: input_select.select_option
              target:
                entity_id: input_select.kallaren_filter
              data:
                option: Öl

      # Flasklistan, grupperad per dryckestyp. Grupper utan flaskor visas inte,
      # och filtret döljer de som inte matchar.
      - type: markdown
        content: >-
          {% set s = 'sensor.kallaren_grocy' %} {% set items = state_attr(s,
          'items') or [] %} {% set filt = states('input_select.kallaren_filter')
          %} {% if state_attr(s, 'error') %}

          ### ⚠️ Grocy nås inte

          `{{ state_attr(s, 'error') }}`

          {% elif items | count == 0 %}

          ### Källaren är tom

          Lägg in flaskor med [dryck-appen](https://dryck.sandholdt.se:8443).

          {% else %} {% for grupp in state_attr(s, 'groups') or [] %} {% set
          rader = items | selectattr('group', 'eq', grupp) | list %} {% if rader
          and filt in ['Allt', grupp] %}

          #### {{ grupp }} — {{ rader | sum(attribute='amount') }} st

          | Namn | Årgång | Druva | Land | Antal | Betyg |
          |---|---:|---|---|---:|---|
          {% for r in rader %}| {{ r.name }} | {{ r.vintage or '–' }} | {{ r.grape or '–' }} | {{ r.country or '–' }} | {{ r.amount }} | {{ '★' * (r.rating | round(0) | int) if r.rating else '–' }} |
          {% endfor %}
          {% endif %} {% endfor %} {% if filt != 'Allt' and (items |
          selectattr('group', 'eq', filt) | list | count) == 0 %}

          *Inget i lager under "{{ filt }}".*

          {% endif %} {% endif %}

      - type: horizontal-stack
        cards:
          - type: custom:mushroom-template-card
            primary: Lägg till dryck
            secondary: Scanna eller sök
            icon: mdi:barcode-scan
            icon_color: teal
            tap_action:
              action: url
              url_path: https://dryck.sandholdt.se:8443
          - type: custom:mushroom-template-card
            primary: Öppna Grocy
            secondary: Full lagerhantering
            icon: mdi:fridge-outline
            icon_color: blue
            tap_action:
              action: url
              url_path: https://grocy.sandholdt.se:8443
```

- [ ] **Step 2: Registrera dashboarden**

I `configuration.yaml`, i `lovelace.dashboards`, efter `lovelace-holk`-blocket:

```yaml
    lovelace-kallaren:
      mode: yaml
      title: Källaren
      icon: mdi:bottle-wine
      show_in_sidebar: true
      filename: dashboards/kallaren.yaml
```

- [ ] **Step 3: Validera YAML och konfiguration**

```bash
python3 -c "import yaml; yaml.safe_load(open('/config/dashboards/kallaren.yaml')); print('Valid')"
/config/scripts/ha core check
```

Expected: `Valid` och giltig konfiguration.

- [ ] **Step 4: Starta om och verifiera entiteterna**

```bash
/config/scripts/ha core restart
```

Vänta, sedan kontrollera att varje refererad entitet finns och har state:

```bash
for e in sensor.kallaren_grocy input_select.kallaren_filter; do
  /config/scripts/ha state $e | head -3
done
```

Expected: båda har riktiga states, ingen `unavailable`.

- [ ] **Step 5: Skärmdumpa vyn och läs bilden**

```bash
python3 /config/scripts/ha_screenshot.py "/lovelace-kallaren/bestand" "/config/www/screenshots/kallaren-bestand.png" 15
```

Läs `/config/www/screenshots/kallaren-bestand.png` och kontrollera: nyckeltalen visar
11 flaskor / 5 sorter / ett lagervärde, chipsraden syns med `Allt` markerat, och
tabellerna listar `ZZ Test`-flaskorna under Rött vin, Vitt vin, Rosévin, Öl och Övrigt.
Testa också filtret:

```bash
/config/scripts/ha call input_select.select_option '{"entity_id":"input_select.kallaren_filter","option":"Öl"}'
python3 /config/scripts/ha_screenshot.py "/lovelace-kallaren/bestand" "/config/www/screenshots/kallaren-filter-ol.png" 15
/config/scripts/ha call input_select.select_option '{"entity_id":"input_select.kallaren_filter","option":"Allt"}'
```

Expected i den andra bilden: bara Öl-sektionen syns, Öl-chipen är orange.

- [ ] **Step 6: Commit**

```bash
cd /config
git add dashboards/kallaren.yaml configuration.yaml
git commit -m "feat: källardashboard med beståndsvy"
```

---

### Task 6: Dashboard vy 2 — Hantera

**Files:**
- Modify: `dashboards/kallaren.yaml` — ny vy efter `Bestånd`

**Interfaces:**
- Consumes: `input_select.kallaren_flaska`, `input_number.kallaren_antal`, `input_number.kallaren_betyg`, `input_text.kallaren_smaknotering`, `input_text.kallaren_senast_druckit`, `script.kallaren_drick_upp`, `script.kallaren_satt_betyg` (alla från Task 4)
- Produces: vy `path: hantera`

- [ ] **Step 1: Lägg till vyn**

I `dashboards/kallaren.yaml`, efter beståndsvyns sista kort (på samma indenteringsnivå som `- title: Bestånd`):

```yaml
  - title: Hantera
    path: hantera
    icon: mdi:glass-wine
    cards:
      # Steg 1: dricka upp. Väljaren fylls av automationen
      # kallaren_fyll_flaskvaljare från beståndet.
      - type: entities
        title: Drick upp en flaska
        show_header_toggle: false
        entities:
          - entity: input_select.kallaren_flaska
            name: Flaska
          - entity: input_number.kallaren_antal
            name: Antal
      - type: custom:mushroom-template-card
        primary: Drick upp
        secondary: >-
          {{ states('input_select.kallaren_flaska') }} ×{{
          states('input_number.kallaren_antal') | int(1) }}
        icon: mdi:glass-wine
        # Mushroom har ingen disabled-option. Skyddet mot tom källare ligger i
        # script.kallaren_drick_upp (condition på att labeln matchar en flaska) —
        # här signalerar färgen bara att knappen är meningslös just nu.
        icon_color: >-
          {{ 'disabled' if is_state('input_select.kallaren_flaska', '— källaren är tom —')
             else 'purple' }}
        tap_action:
          action: perform-action
          perform_action: script.kallaren_drick_upp

      # Steg 2: betygsätta. Medvetet skilt från steg 1 — flaskan man vill
      # betygsätta har ofta lämnat lagret och finns inte längre i väljaren.
      # Produkt-id:t ligger kvar i input_text.kallaren_senast_druckit ("id|namn").
      - type: markdown
        content: >-
          {% set senast = states('input_text.kallaren_senast_druckit') %} {% if
          '|' in senast %}

          ### Betygsätt: {{ senast.split('|')[1] }}

          {% else %}

          ### Betygsätt

          *Drick upp en flaska först — då hamnar den här.*

          {% endif %}
      - type: entities
        show_header_toggle: false
        entities:
          - entity: input_number.kallaren_betyg
            name: Betyg
          - entity: input_text.kallaren_smaknotering
            name: Smaknotering
      - type: custom:mushroom-template-card
        primary: Spara betyg
        secondary: Skrivs till Grocy
        icon: mdi:star
        # Som ovan: skyddet ligger i script.kallaren_satt_betyg (condition på att
        # ett produkt-id finns i input_text.kallaren_senast_druckit).
        icon_color: >-
          {{ 'amber' if '|' in states('input_text.kallaren_senast_druckit') else 'disabled' }}
        tap_action:
          action: perform-action
          perform_action: script.kallaren_satt_betyg
```

- [ ] **Step 2: Validera**

```bash
python3 -c "import yaml; yaml.safe_load(open('/config/dashboards/kallaren.yaml')); print('Valid')"
/config/scripts/ha core check
```

Expected: `Valid` + giltig konfiguration.

- [ ] **Step 3: Skärmdumpa och verifiera**

```bash
python3 /config/scripts/ha_screenshot.py "/lovelace-kallaren/hantera" "/config/www/screenshots/kallaren-hantera.png" 15
```

Läs bilden. Expected: flaskväljaren listar `ZZ Test`-flaskorna, antalsreglaget syns,
"Drick upp"-kortet visar valt namn i undertexten, och betygsrubriken visar namnet på
flaskan som konsumerades i Task 4 steg 7 (`ZZ Test Hazy IPA`).

- [ ] **Step 4: Klicktesta hela flödet via services**

```bash
/config/scripts/ha call input_select.select_option '{"entity_id":"input_select.kallaren_flaska","option":"ZZ Test Chablis Premier Cru (2021)"}'
/config/scripts/ha call input_number.set_value '{"entity_id":"input_number.kallaren_antal","value":1}'
/config/scripts/ha call script.kallaren_drick_upp '{}'
sleep 5
/config/scripts/ha state sensor.kallaren_grocy | head -3
/config/scripts/ha state input_text.kallaren_senast_druckit
```

Expected: `n_vitt_vin` gick från 2 till 1, och `senast_druckit` pekar nu på Chablis-flaskan.

- [ ] **Step 5: Commit**

```bash
cd /config
git add dashboards/kallaren.yaml
git commit -m "feat: hanteringsvy för att dricka upp och betygsätta"
```

---

### Task 7: Dashboard vy 3 och 4 — Statistik och Grocy

**Files:**
- Modify: `dashboards/kallaren.yaml` — två nya vyer efter `Hantera`

**Interfaces:**
- Consumes: `sensor.kallaren_grocy` (`n_*`, `by_country`, `by_vintage`, `avg_rating`, `value`), `sensor.kallaren_flaskor`
- Produces: vyerna `path: statistik` och `path: grocy`

- [ ] **Step 1: Kontrollera om Grocy kan bäddas in**

`iframe`-kortet fungerar bara om Grocy inte skickar en blockerande
`X-Frame-Options`/`frame-ancestors`. Grocy svarar inte på HEAD, så använd GET:

```bash
curl -s -D - -o /dev/null --max-time 8 -H "Accept: text/html" \
  http://192.168.1.66:9283/ | grep -i "x-frame-options\|content-security-policy\|HTTP/"
```

- Ingen träff på `x-frame-options` eller `frame-ancestors` → använd `iframe`-kortet i steg 3.
- `DENY`/`SAMEORIGIN`/`frame-ancestors` → hoppa över `iframe`-kortet och använd
  reservvarianten i steg 4 i stället. Anteckna vilket som gällde i commit-meddelandet.

- [ ] **Step 2: Lägg till statistikvyn**

I `dashboards/kallaren.yaml`, efter Hantera-vyn:

```yaml
  - title: Statistik
    path: statistik
    icon: mdi:chart-donut
    cards:
      - type: horizontal-stack
        cards:
          - type: custom:mushroom-template-card
            primary: >-
              {{ state_attr('sensor.kallaren_grocy', 'avg_rating') or '–' }}
            secondary: Snittbetyg
            icon: mdi:star
            icon_color: amber
            tap_action:
              action: none
          - type: custom:mushroom-template-card
            primary: "{{ (state_attr('sensor.kallaren_grocy', 'value') or 0) | round(0) }} kr"
            secondary: Lagervärde
            icon: mdi:cash
            icon_color: green
            tap_action:
              action: none

      # Donuten läser de platta n_*-attributen (satta av grocy_kallaren.py)
      # i stället för att gå via data_generator — en serie per dryckestyp.
      - type: custom:apexcharts-card
        chart_type: donut
        header:
          show: true
          title: Fördelning per typ
        series:
          - entity: sensor.kallaren_grocy
            attribute: n_rott_vin
            name: Rött vin
          - entity: sensor.kallaren_grocy
            attribute: n_vitt_vin
            name: Vitt vin
          - entity: sensor.kallaren_grocy
            attribute: n_rosevin
            name: Rosévin
          - entity: sensor.kallaren_grocy
            attribute: n_mousserande_vin
            name: Mousserande
          - entity: sensor.kallaren_grocy
            attribute: n_ol
            name: Öl

      # Land och årgång är dynamiska dimensioner — de renderas som staplar i
      # markdown i stället för fasta apexcharts-serier, som hade behövt en
      # serie per värde och gått sönder så fort en ny flaska dök upp.
      - type: markdown
        content: >-
          {% set by = state_attr('sensor.kallaren_grocy', 'by_country') or {} %}

          #### Flaskor per land

          {% if by %}{% set hogsta = by.values() | list | max %}{% for land, n in
          by.items() %}

          `{{ '█' * ([1, (n / hogsta * 14) | round(0) | int] | max) }}` {{ land }} ({{ n }})

          {% endfor %}{% else %}*Ingen landsdata än.*{% endif %}
      - type: markdown
        content: >-
          {% set by = state_attr('sensor.kallaren_grocy', 'by_vintage') or {} %}

          #### Flaskor per årgång

          {% if by %}{% set hogsta = by.values() | list | max %}{% for argang, n
          in by.items() %}

          `{{ '█' * ([1, (n / hogsta * 14) | round(0) | int] | max) }}` {{ argang }} ({{ n }})

          {% endfor %}{% else %}*Ingen årgångsdata än.*{% endif %}

      # Trenden börjar den dag sensor.kallaren_flaskor skapades — ingen
      # historik bakåt finns.
      - type: statistics-graph
        title: Antal flaskor över tid
        entities:
          - sensor.kallaren_flaskor
        days_to_show: 30
        stat_types:
          - mean
```

- [ ] **Step 3: Lägg till Grocy-vyn (om steg 1 gav klartecken)**

```yaml
  - title: Grocy
    path: grocy
    icon: mdi:fridge-outline
    cards:
      - type: horizontal-stack
        cards:
          - type: custom:mushroom-template-card
            primary: Lägg till dryck
            secondary: Scanna eller sök
            icon: mdi:barcode-scan
            icon_color: teal
            tap_action:
              action: url
              url_path: https://dryck.sandholdt.se:8443
          - type: custom:mushroom-template-card
            primary: Öppna i egen flik
            secondary: Om inbäddningen krånglar
            icon: mdi:open-in-new
            icon_color: blue
            tap_action:
              action: url
              url_path: https://grocy.sandholdt.se:8443
      # HTTPS-URL krävs: http://192.168.1.66:9283 blockeras som mixed content
      # när HA nås över HTTPS.
      - type: iframe
        url: https://grocy.sandholdt.se:8443
        aspect_ratio: 150%
```

- [ ] **Step 4: Reservvariant — bara om steg 1 visade att inbäddning blockeras**

Ersätt `iframe`-kortet ovan med:

```yaml
      # Grocy skickar X-Frame-Options och kan inte bäddas in — länkkort i stället.
      - type: markdown
        content: >-
          ### Grocy

          Grocy tillåter inte inbäddning i HA (`X-Frame-Options`). Använd
          knapparna ovan för att öppna
          [Grocy](https://grocy.sandholdt.se:8443) eller
          [dryck-appen](https://dryck.sandholdt.se:8443) i en egen flik.
```

- [ ] **Step 5: Validera**

```bash
python3 -c "import yaml; yaml.safe_load(open('/config/dashboards/kallaren.yaml')); print('Valid')"
python3 /config/scripts/validate_apexcharts.py /config/dashboards/kallaren.yaml
/config/scripts/ha core check
```

Expected: `Valid`, inga apexcharts-anmärkningar, giltig konfiguration.

- [ ] **Step 6: Skärmdumpa båda vyerna**

```bash
python3 /config/scripts/ha_screenshot.py "/lovelace-kallaren/statistik" "/config/www/screenshots/kallaren-statistik.png" 20
python3 /config/scripts/ha_screenshot.py "/lovelace-kallaren/grocy" "/config/www/screenshots/kallaren-grocy.png" 20
```

Läs båda bilderna. Expected i statistikvyn: donuten visar segment för Rött/Vitt/Rosé/Öl,
landstaplarna listar Italien/Frankrike/Sverige, årgångsstaplarna 2018/2021/2022.
Expected i Grocy-vyn: Grocys inloggning eller lagervy syns i iframen (eller länkkorten,
om reservvarianten användes). En tom vit iframe betyder att inbäddningen blockeras —
byt då till reservvarianten.

- [ ] **Step 7: Commit**

```bash
cd /config
git add dashboards/kallaren.yaml
git commit -m "feat: statistik- och Grocy-vy i källardashboarden"
```

---

### Task 8: Slutverifiering, städning och dokumentation

**Files:**
- Modify: `CLAUDE.md` — tabellen "Lovelace Dashboards" och ett nytt Källaren-avsnitt

**Interfaces:**
- Consumes: allt från Task 1–7
- Produces: städad Grocy (inga `ZZ Test`-produkter), uppdaterad dokumentation

- [ ] **Step 1: Verifiera hela entitetskedjan**

```bash
for e in sensor.kallaren_grocy sensor.kallaren_flaskor input_select.kallaren_filter \
         input_select.kallaren_flaska input_number.kallaren_antal input_number.kallaren_betyg \
         input_text.kallaren_smaknotering input_text.kallaren_senast_druckit \
         script.kallaren_drick_upp script.kallaren_satt_betyg \
         automation.kallaren_fyll_flaskvaljare; do
  printf '%-45s ' "$e"; /config/scripts/ha state $e | grep -m1 '"state"'
done
```

Expected: alla elva har ett state, inget `unavailable`/`unknown`, automationen är `on`.

- [ ] **Step 2: Kontrollera loggarna**

```bash
/config/scripts/ha core logs 500 | grep -iE "kallaren|grocy|command_line|template" | grep -iE "error|warning|exception" | head -20
```

Expected: inga träffar relaterade till källaren. Befintliga varningar från andra
integrationer är inte i scope.

- [ ] **Step 3: Ta bort testdatan**

```bash
cd /config/scripts && python3 grocy_testdata.py --remove && python3 grocy_testdata.py --list
```

Expected: `-`-rader för alla kvarvarande `ZZ Test`-produkter, sedan tom utskrift.

- [ ] **Step 4: Verifiera att Grocy är tillbaka i ursprungsläget**

```bash
K=$(grep -oP '^grocy_api_key:\s*"?\K[^"]+' /config/secrets.yaml)
curl -s -H "GROCY-API-KEY: $K" http://192.168.1.66:9283/api/objects/products \
  | python3 -c "import sys,json; print([p['name'] for p in json.load(sys.stdin)])"
curl -s -H "GROCY-API-KEY: $K" http://192.168.1.66:9283/api/objects/product_groups \
  | python3 -c "import sys,json; print([g['name'] for g in json.load(sys.stdin)])"
```

Expected: **exakt** `['Test Wine bottle']` och
`['Rött vin', 'Vitt vin', 'Rosévin', 'Mousserande vin', 'Öl']` — inga rester, och
grupperna orörda (schemat ägs av dryck-appen).

- [ ] **Step 5: Verifiera tomt läge i dashboarden**

```bash
/config/scripts/ha call homeassistant.update_entity '{"entity_id":"sensor.kallaren_grocy"}'
sleep 5
python3 /config/scripts/ha_screenshot.py "/lovelace-kallaren/bestand" "/config/www/screenshots/kallaren-tomt.png" 15
/config/scripts/ha state input_select.kallaren_flaska | head -5
```

Läs bilden. Expected: `Test Wine bottle` under "Övrigt", inga `ZZ Test`-rader, inga
tomma tabeller eller Jinja-fel. Väljaren innehåller nu bara `Test Wine bottle`.

- [ ] **Step 6: Verifiera felläget end-to-end**

Byt tillfälligt porten i skriptet så Grocy inte kan nås, och se att dashboarden
visar "Grocy nås inte" i stället för `unavailable`:

```bash
sed -i 's#:9283/api#:9999/api#' /config/scripts/grocy_kallaren.py
/config/scripts/ha call homeassistant.update_entity '{"entity_id":"sensor.kallaren_grocy"}'
sleep 5 && /config/scripts/ha state sensor.kallaren_grocy | head -4
python3 /config/scripts/ha_screenshot.py "/lovelace-kallaren/bestand" "/config/www/screenshots/kallaren-fel.png" 15
sed -i 's#:9999/api#:9283/api#' /config/scripts/grocy_kallaren.py
git -C /config diff --exit-code scripts/grocy_kallaren.py && echo "ÅTERSTÄLLD OK"
```

Expected: state blir `0`, bilden visar rubriken "⚠️ Grocy nås inte", och sista raden
skriver `ÅTERSTÄLLD OK` — porten måste vara tillbaka på 9283.

- [ ] **Step 7: Uppdatera dokumentationen**

I `CLAUDE.md`, lägg en rad i tabellen "Lovelace Dashboards" efter `System`:

```markdown
| Källaren | `/lovelace-kallaren` | Grocy drinks inventory (4 views: Bestånd, Hantera, Statistik, Grocy) |
```

Och ett nytt avsnitt efter "Grocy"-raden i infrastrukturtabellens avsnitt (före `## Custom Components`):

```markdown
## Källaren (Grocy-bestånd)
Dryckesbeståndet i källarens vinhylla, läst ur Grocy. Inmatning sker i dryck-appen
(`dryck.sandholdt.se:8443`), inte i HA.

| Entitet | Syfte |
|---------|-------|
| `sensor.kallaren_grocy` | Hela beståndet. State = antal flaskor, attribut `items`/`groups`/`by_country`/`by_vintage`/`n_*`/`error`. Exkluderad från recorder & InfluxDB |
| `sensor.kallaren_flaskor` | Bara antalet, recordat → trendgraf |
| `script.kallaren_drick_upp` | Konsumerar valda flaskan i Grocy |
| `script.kallaren_satt_betyg` | Skriver `rating`/`tasting_notes` på senast druckna |
| `automation.kallaren_fyll_flaskvaljare` | Håller `input_select.kallaren_flaska` i synk |

- Data hämtas av `scripts/grocy_kallaren.py` (joinar `/api/stock`, `/api/objects/products`,
  `/api/objects/product_groups`, `/api/objects/locations`) var 5:e minut. Grocy-integrationen
  används **inte** för lagret — den exponerar inte userfields (årgång, druva, land, betyg).
- Enhetstester: `cd /config/scripts && python3 -m unittest discover -s . -p "test_grocy_*.py"`
- Testdata för att verifiera vyerna: `python3 scripts/grocy_testdata.py --add|--list|--remove`
  (produkter med prefix `ZZ Test `). **Kör alltid `--remove` efteråt.**
- Grocy-schemat (grupper, userfields, enheter, locations) ägs av dryck-appens bootstrap —
  ändra det aldrig härifrån.
- `PUT /api/userfields/products/{id}` merge:ar; `rating`/`vintage` returneras som strängar.
```

- [ ] **Step 8: Slutlig validering**

```bash
/config/scripts/ha core check
cd /config/scripts && python3 -m unittest discover -s . -p "test_grocy_*.py"
cd /config && git status --short
```

Expected: giltig konfiguration, alla tester `OK`, och `git status` visar bara
`CLAUDE.md` som ändrad (skärmdumparna i `www/screenshots/` ska vara gitignorerade —
kontrollera med `git check-ignore -v www/screenshots/kallaren-bestand.png`; om de
inte är ignorerade, lägg till dem i `.gitignore` i stället för att committa dem).

- [ ] **Step 9: Commit**

```bash
cd /config
git add CLAUDE.md
git commit -m "docs: dokumentera Källaren-dashboarden"
```

- [ ] **Step 10: Fråga användaren om push**

Pusha **aldrig** utan uttryckligt godkännande. Redovisa vad som byggts, visa
skärmdumparna, och fråga om det ska pushas till GitHub.

---

## Self-Review

**Spec coverage:**

| Spec-avsnitt | Task |
|--------------|------|
| §3 Alternativ A, `grocy_kallaren.py` | 1 |
| §3 `sensor.kallaren_grocy` (command_line, 300 s) | 3 steg 1 |
| §3 `sensor.kallaren_flaskor` (template, recordad) | 3 steg 2 |
| §3 `rest_command.grocy_consume` / `grocy_set_userfields` | 4 steg 1 |
| §3 Skriptets utdata (alla fält inkl. `value` från stock-raden) | 1 steg 3 |
| §3 Felhantering (`error_payload`, aldrig `unavailable`) | 1 steg 3+6, 8 steg 6 |
| §3 Databas (recorder- & InfluxDB-exclude) | 3 steg 3 |
| §4 Registrering `lovelace-kallaren` | 5 steg 2 |
| §4 Vy 1 Bestånd (nyckeltal, chips, grupperad tabell, knappar) | 5 |
| §4 Vy 2 Hantera (väljare, antal, drick upp, betygsätt) | 6 |
| §4 Vy 3 Statistik (donut, land, årgång, trend, nyckeltal) | 7 steg 2 |
| §4 Vy 4 Grocy (iframe + reservvariant) | 7 steg 1, 3, 4 |
| §4 Dubbletthantering av label | 1 steg 3 (`_apply_labels`) — flyttad från automationen, se avvikelsen ovan |
| §5 Verifiering steg 1–10 | 1 steg 5, 2, 3 steg 5, 5–7 skärmdumpar, 8 steg 1–6 |
| §5 punkt 8 (PUT nollar inte övriga userfields) | 4 steg 8 |
| §5 punkt 9 (radera testflaskorna) | 8 steg 3–4 |
| §6 Läser bara schemat | Global Constraints + 2 steg 1 (avbryter om grupp saknas) + 8 steg 4 |

Ingen spec-punkt utan task.

**Placeholder scan:** Inga TBD/TODO. Varje kodsteg har fullständig kod; varje
verifieringssteg har ett körbart kommando och ett förväntat utfall. Task 7 steg 1
är en förgrening med två färdigskrivna utfall, inte en oskriven lucka.

**Type consistency:** `build_payload(stock, products, groups, locations)` har samma
signatur i testerna (Task 1 steg 1) och implementationen (steg 3). Item-nycklarna
`id/name/label/group/vintage/grape/country/region/amount/rating/abv/value` används
identiskt i skriptet, i `scripts.yaml` (`flaska.id`, `flaska.name`, `label`), i
automationen (`map(attribute='label')`) och i dashboardens markdown-kort
(`r.name`, `r.vintage`, `r.grape`, `r.country`, `r.amount`, `r.rating`).
`GROUP_ATTRS`-värdena `n_rott_vin/n_vitt_vin/n_rosevin/n_mousserande_vin/n_ol`
matchar `json_attributes` i Task 3 och apexcharts-serierna i Task 7.
`input_text.kallaren_senast_druckit`-formatet `<id>|<namn>` skrivs i Task 4 steg 3
och läses med `split('|')[0]` i samma fil och `split('|')[1]` i Task 6.
