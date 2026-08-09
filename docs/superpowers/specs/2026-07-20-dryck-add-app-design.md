# "Lägg till dryck" — app för Grocy-inmatning med Systembolaget-berikning

**Datum:** 2026-07-20
**Status:** Design + plan (bygget pausat på användarens begäran — kod utkastad, ej deployad)

---

## 1. Problemet vi löser

Grocy-vinkällaren fungerar, men att lägga in en ny dryck kräver att man manuellt
skriver namn, typ, land, druva, årgång och pris. Målet: **scanna/skriv → få rik
data automatiskt**, för både **öl och vin**, med en **väljare** som visar ~10
kandidater medan man skriver (så man slipper felmatchning).

## 2. Vad utredningen visade (viktiga fynd)

| Fråga | Resultat |
|-------|----------|
| `EAN → namn` via gratis-API (OpenFoodFacts, UPCitemdb) | ❌ **Fallerar** på riktiga vinflaskor (testat på 2 av dina) |
| Websökning på EAN | ❌ Ger inget användbart |
| Systembolaget: har EAN i datan? | ❌ **Nej** — nycklat på artikelnummer, inte flaskans EAN |
| `namn → Systembolaget` (internt API) | ✅ **Fungerar utmärkt** — namn, producent, land, årgång, druvor, kategori, pris, bild |

**Slutsats:** vägen via streckkod är en återvändsgränd. Vägen via **namn →
Systembolaget** ger all rik data. Alltså bygger vi kring namn-sökning, inte EAN.
Streckkoden har ändå värde: den kopplas till drycken så att **consume/påfyllning**
av kända flaskor kan ske genom att scanna i Grocy-appen sen.

## 3. Vald lösning — en liten egen webbapp

Grocys eget formulär har ingen extern typeahead, och en webbläsare kan inte anropa
Systembolaget direkt (CORS + nyckeln får inte ligga i klienten). Därför: en liten
mobilvänlig **"Lägg till dryck"-app** med en backend som proxar Systembolaget och
skapar Grocy-produkter server-side.

### Användarflöde
1. Öppna appen på mobilen → (valfritt) **ZXing-scanner** fångar EAN och kopplar den.
2. Skriv namnet → **debouncad typeahead** mot Systembolaget → topp ~10 kort
   (minibild, namn, typ, årgång, pris). Fler bokstäver → färre, bättre träffar.
3. Tryck på rätt dryck → appen skapar en **färdig, berikad Grocy-produkt** + lägger
   +N i lager.

### Vad som fylls i automatiskt vid "välj"
| Grocy | Från Systembolaget |
|-------|--------------------|
| Namn | `productNameBold` + `productNameThin` |
| Produktgrupp | `categoryLevel2` (Rött vin / Ljus lager / IPA …) — **find-or-create** |
| Userfield `land_region` | `country` |
| Userfield `druva` | `grapes` (tomt för öl) |
| Userfield `argang` | `vintage` (tomt för öl) |
| Pris (inbyggt) | `price` |
| Produktbild | Etiketten laddas ner → laddas upp till Grocy |
| Streckkod | Den scannade EAN:en (om någon) |
| Lager | +N st i location **Källare** |

Känd streckkod som scannas → appen **fyller bara på lagret** på befintlig produkt
(ingen dubblett).

## 4. Arkitektur

```
Mobil (PWA)  ──►  https://dryck.sandholdt.se:8443
                    │  nginx .70 (TLS, SNI — samma mönster som grocy)
                    ▼
              dryck-container på docker-hosten (.66)
                    ├─ GET  /api/search?q=  → proxar Systembolaget (nyckel server-side) → topp ~10
                    └─ POST /api/add        → skapar Grocy-produkt via Grocy-API (nyckel server-side)
                                               → Grocy-container .66:9283
```

- **Backend:** enfils-Python med **stdlib `http.server`** (noll beroenden) i
  `python:3.12-slim`. Nycklar (Systembolaget + Grocy) ligger server-side i
  compose-env, aldrig i klienten.
- **Frontend:** en statisk `index.html` (inbyggd CSS/JS) + lokal `zxing.js`
  (self-contained, ingen CDN i drift).
- **Reverse proxy:** ny nginx-site `dryck.sandholdt.se` på `.70:8443` (SNI, delar
  maffia/grocy-lyssnaren), eget certbot-cert.

## 5. Komponenter / filer

| Fil (på docker-hosten `/opt/dryck/`) | Syfte | Status |
|--------------------------------------|-------|--------|
| `server.py` | stdlib-server: static + `/api/search` + `/api/add` + Grocy-mappning | ✅ utkastad |
| `static/index.html` | sök/typeahead + ZXing-scanner + antal + lägg-till | ✅ utkastad |
| `static/zxing.js` | lokal ZXing-UMD (0.19.1) | ⏳ hämtas vid deploy |
| `Dockerfile` | `python:3.12-slim`, kör `server.py` | ✅ utkastad |
| `docker-compose.yml` | container `dryck`, host-port 8098→8099, env-nycklar | ✅ utkastad |

## 6. Byggplan (faser)

1. **Kärna internt** — deploya containern på `.66`, testa `/api/search` live +
   `/api/add` mot Grocy (skapa → verifiera berikning → radera testprodukt). Nås på
   `http://192.168.1.66:8098` internt.
2. **Scanner** — verifiera ZXing-flödet på mobil (bakkamera, som i Grocy-fixen).
3. **Externalisering** — nginx-site + certbot-cert på `.70`, DNS.
4. **Puts** — öl-specifika detaljer (enhet burk/flaska), felhantering, ev. filter
   på dryckeskategorier.

## 7. Öppna beroenden / användarsteg

- **DNS (one.com):** A-post `dryck.sandholdt.se` → `98.128.137.175`.
- **UniFi Local DNS:** `dryck.sandholdt.se` → `192.168.1.70` (som grocy).
- **Enhet för öl:** öl är ofta burk — default `Flaska`, ev. lägga till `Burk` (avgörs vid test).

## 8. Risker & fallback

- **Systembolaget-nyckeln är inofficiell** (från publik gist) → kan rotera/sluta
  gälla. Fallback: lokal community-dataset (AlexGustafsson/C4illin), daglig refresh,
  namn-matchas lokalt. Byggs vid behov.
- **Namn-matchning** kan ge fel dryck → därför **väljaren** (användaren bekräftar),
  inte auto-topp-träff.
- **Nycklar i klartext** i compose-env på hosten (homelab-acceptabelt, PBS-backat).

## 9. Framtida tillägg (ej nu)

- Betalt streckkods-API (EAN-Search/barcodelookup) för att slippa skriva namnet.
- HA-kort som visar beståndet (via redan installerade Grocy-integrationen).
- "Ratea"-genväg i appen (sätta `betyg` + `smaknoteringar`).

## 10. Beslut (bekräftade med användaren)

- Öl **och** vin (och andra Systembolaget-drycker).
- Interaktiv **väljare** med ~10 kandidater + typeahead.
- **Extern** åtkomst via HTTPS (egen subdomän).
- **ZXing-scanner** med i appen.
- Backend stdlib, nycklar server-side. Bygg kärnan internt först, sen proxy/cert/DNS.
