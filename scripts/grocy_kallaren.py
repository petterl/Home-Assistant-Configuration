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
