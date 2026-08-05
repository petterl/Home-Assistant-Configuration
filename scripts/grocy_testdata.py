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
