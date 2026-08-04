# "Lägg till dryck" — app för Grocy-inmatning med Systembolaget-berikning

**Datum:** 2026-07-20
**Status:** Godkänd design, under implementation

## Mål

En liten mobilvänlig webbapp för att snabbt lägga in **öl & vin** (och andra
Systembolaget-drycker) i Grocy med **rik data automatiskt**. Löser att `EAN→namn`
inte går pålitligt (gratis-API:er saknar vinerna) genom att i stället söka på
**namn → Systembolaget** (bevisat: live-API ger namn, producent, land, årgång,
druvor, kategori, pris, bild).

## Bakgrund / bevisat

- `EAN→namn` via OpenFoodFacts/UPCitemdb: **fallerar** på riktiga vinflaskor.
- Systembolagets interna API funkar (2026-07): `GET
  https://api-systembolaget.azure-api.net/sb-api-ecommerce/v1/productsearch/search?textQuery=<q>`
  med header `Ocp-Apim-Subscription-Key` → rik data. Inofficiell nyckel (risk för
  rotation → fallback: lokal community-dataset).
- Grocys eget formulär saknar extern typeahead → egen frontend behövs. Browser kan
  ej anropa Systembolaget direkt (CORS + nyckeln får ej ligga i klient) → backend-proxy.

## Arkitektur

Ny container `dryck` på docker-hosten (`.66`), bakom nginx-proxy som
`https://dryck.sandholdt.se:8443` (samma SNI-mönster som grocy).

```
Mobil (PWA) → https://dryck.sandholdt.se:8443
  → nginx .70 (TLS, SNI) → dryck-container .66:<port>
     ├─ GET /api/search?q=  → proxar Systembolaget (nyckel server-side) → topp ~10
     └─ POST /api/add       → skapar Grocy-produkt via Grocy-API (nyckel server-side)
```

Backend: enfils-Python (**stdlib `http.server`**, inga beroenden) i `python:3.12-slim`.

## Flöde (frontend)

1. Öppna appen → (valfritt) **ZXing-scanner** fångar EAN, kopplas till drycken.
2. Skriv namn → **debouncad typeahead** mot `/api/search` → topp ~10 kort
   (minibild, namn, typ, årgång, pris). Smalnar av efterhand.
3. Välj → `POST /api/add` skapar färdig Grocy-produkt:
   - produktgrupp = Systembolagets `categoryLevel2` (Rött vin / Ljus lager / IPA …),
     find-or-create.
   - userfields: `land_region`=country, `druva`=grapes, `argang`=vintage (tomt för öl).
   - pris = Systembolaget-pris (Grocys inbyggda), bild = Systembolagets etikett
     (laddas ner → laddas upp till Grocy → `picture_file_name`), streckkod kopplas,
     +N i lager (location Källare).

## Komponenter att bygga

1. `/opt/dryck/server.py` — stdlib-server: static + `/api/search` + `/api/add`.
2. `/opt/dryck/static/index.html` — sök/typeahead + ZXing-scanner + antal + lägg-till.
3. `/opt/dryck/static/zxing.js` — lokal ZXing-UMD (self-contained, ingen CDN).
4. `/opt/dryck/Dockerfile` + `docker-compose.yml` (publicera intern port).
5. Grocy-mappning: kategori→grupp (auto-create), country/grapes/vintage→userfields,
   pris, bild-upload, barcode, add-stock.
6. nginx-site `dryck` på `.70` (SNI 8443) + certbot-cert + DNS (one.com A→WAN,
   UniFi Local DNS → .70) — kräver användarsteg (som grocy).

## Öppna beroenden / användarsteg
- DNS: `dryck.sandholdt.se` A→`98.128.137.175` (one.com) + UniFi Local DNS →`.70`.
- Systembolaget-nyckelns hållbarhet → fallback lokal dataset vid behov.
- QU: öl är ofta burk/flaska — default `Flaska`, kan behöva `Burk` (TBD vid test).

## Beslut
- Extern åtkomst via HTTPS (egen subdomän), ZXing-scanner med.
- Backend stdlib (noll beroenden). Nycklar server-side.
- Bygg kärnan (sök+add) och testa internt på `.66:<port>` först, sen scanner + proxy/cert/DNS.
