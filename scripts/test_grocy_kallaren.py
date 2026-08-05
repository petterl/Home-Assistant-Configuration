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
