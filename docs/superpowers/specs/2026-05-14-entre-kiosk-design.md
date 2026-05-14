# Entré Kiosk Dashboard — Design

**Date:** 2026-05-14
**Status:** Draft (pending review)
**Target device:** Wall-mounted landscape tablet in entré

## Goal

Add a new Lovelace dashboard intended for kiosk-mode display on a landscape
tablet mounted in the entré. The dashboard surfaces:

- Live camera feeds for the three outdoor cameras (ringklocka, uppfart, garage)
- Easy house-wide light control via per-room group toggles
- Current weather
- Next bus departures from Fornvägen towards Resecentrum
- Door status and lock control for the two doors at the kiosk's location

## Non-goals

- No new automations
- No changes to existing dashboards
- No granular per-light control on the kiosk (the existing `/lovelace-hem`
  dashboard handles that; long-press on a room tile navigates there)
- No new template sensors, statistics sensors, or SQL sensors
- No kiosk-mode addon configuration (HA's URL kiosk handling is out of scope —
  this design covers only the dashboard YAML)

## Architecture

A new YAML Lovelace dashboard registered at `/lovelace-entre`, structured as
three tabs (HA's native view navigation, no custom tab-bar card):

1. **Hem** — default view: cameras, weather, doors/locks, bus departures
2. **Ljus** — per-room light group toggles
3. **Mer** — vacuum, scenes, birdcage camera

Layout uses `custom:grid-layout` (the same `layout-card` pattern already in use
across the other dashboards).

### New dependencies

| Dependency | Source | Purpose |
|------------|--------|---------|
| `MrSjodin/HomeAssistant_Trafiklab_Integration` | HACS | Trafiklab Realtime API — bus departures |
| Trafiklab Realtime API key | trafiklab.se (free) | Authenticate the integration |

The integration is configured via the HA UI (config flow). One departure
sensor is created: Fornvägen stop, direction filtered to Resecentrum.

### Files touched

| File | Change |
|------|--------|
| `dashboards/entre.yaml` | **New** — the dashboard |
| `configuration.yaml` | Register the new dashboard under `lovelace.dashboards` |
| `secrets.yaml` | Add `trafiklab_api_key` |

No changes to `automations.yaml`, `template_sensors.yaml`, `sql_sensors.yaml`,
`statistics_sensors.yaml`, `scenes.yaml`, or existing dashboards.

## Views

### View 1 — Hem (default, landscape)

3-column grid:

```
┌─────────────────────────────────────────────────────────────────────┐
│  Klocka + datum + väder (full width header)                         │
├──────────────────────┬──────────────────────┬───────────────────────┤
│  Ringklocka          │  Uppfart             │  Garage               │
│  (live stream)       │  (live stream)       │  (live stream)        │
├──────────────────────┴──────────────────────┼───────────────────────┤
│  Dörrar & lås                               │  Nästa bussar         │
│  • Entré:    [olåst] [lås]  status: stängd  │  Fornvägen →          │
│  • Groventré:[olåst] [lås]  status: stängd  │  Resecentrum          │
│  • Garage:                  status: stängd  │  • 17:42  linje 3     │
│                                             │  • 17:54  linje 12    │
│                                             │  • 18:02  linje 3     │
└─────────────────────────────────────────────┴───────────────────────┘
```

**Grid:**

```yaml
grid-template-columns: 1fr 1fr 1fr
grid-template-areas: |
  "header header header"
  "cam1   cam2   cam3"
  "doors  doors  buses"
```

**Components:**

- **Header** — `markdown` card. Time, date, weather state + current temp from
  `weather.forecast_hem`.
- **Camera tiles** — `picture-glance` cards using the
  `camera.*_high_resolution_channel` entities. Live stream enabled
  (`camera_view: live`). Tap → fullscreen.
- **Doors & locks strip** — `vertical-stack-in-card` with one row per door:
  - Entré: `lock.entre_2` + `binary_sensor.entre_dorr_2`, lock/unlock buttons
  - Groventré: `lock.groventre_3` + `binary_sensor.groventre_dorr_2`,
    lock/unlock buttons
  - Garage: door status only — `binary_sensor.garagedorr_dorr_2`. A
    `lock.garagedorr` entity exists but lock control was not requested
    for the kiosk.
  Implemented with `mushroom-template-card` per row for consistent styling
  with the rest of the dashboards.
- **Bus list** — card provided by the Trafiklab integration if it ships one;
  otherwise an `entities` card binding to the integration's departure sensor
  attributes (next 3–5 departures, each line shows minutes-until + line
  number + destination).

### View 2 — Ljus

4-column grid of room toggles. Each card is a `mushroom-template-card`:

- **Primary**: room name (Swedish — Köket, Vardagsrum, etc.)
- **Icon**: room-appropriate `mdi:*` icon
- **Icon color**: amber if any light in the room is on, otherwise disabled
- **Secondary**: "N lampor på" or "Alla av"
- **Tap**: toggles all lights in the room (`light.turn_on` /
  `light.turn_off` on the room's light entities)
- **Hold**: navigates to `/lovelace-hem/<room_path>` for granular control

**Rooms in scope** (those with controllable lights):

| Room | Area | Notes |
|------|------|-------|
| Köket | `kok` | Multiple Plejd lights |
| Vardagsrum | `vardagsrum` | Plejd |
| Gästrum | `gastrum` | Plejd |
| Garage | `garage` | Plejd |
| Partyrummet | `partyrummet` | Plejd |
| Entré | `entre` | `light.takspottar_2` |
| Utomhus | `utomhus` | Plejd outdoor lights |

Idas rum and Moas rum are intentionally excluded — they have no
controllable light entities (only Zigbee buttons and blinds).

**State derivation** uses Jinja templates against `area_entities('<area>')
| select('match', '^light\\.')`. No new helper entities or `light` groups
are created — the templates compute "any light on?" inline and the tap
action calls `light.turn_off` / `light.turn_on` with `entity_id` set to
the area's lights via template.

### View 3 — Mer

Mixed grid:

- **Dammsugare** — `mushroom-template-card` showing
  `vacuum.roborock_de_118057288_s5` state + battery
  (`sensor.roborock_de_118057288_s5_battery_level_p_3_1`), with start /
  return-to-base / pause action buttons.
- **Scener** — three `mushroom-template-card` action buttons:
  - **Allt släckt** — turn off all lights in all rooms
  - **Välkommen hem** — turn on outdoor + entré lights
  - **Natt** — turn off all lights except designated night-lights
  Implemented inline via `service: light.turn_off` calls on area groups; no
  entries in `scenes.yaml` unless the user later wants them named.
- **Birdcage camera** — `picture-glance` card for `camera.birdcage`, same
  style as the Hem cameras.

## Bus integration details

Integration: `MrSjodin/HomeAssistant_Trafiklab_Integration` (HACS).

Setup steps (executed during implementation, not part of the dashboard
file):

1. Register a Trafiklab Realtime API key at trafiklab.se (free tier).
2. Add the integration via HACS.
3. Add `trafiklab_api_key: <key>` to `secrets.yaml`.
4. Configure the integration via UI:
   - Find the Fornvägen stop using the integration's stop-search.
   - Filter departures by direction = Resecentrum (the integration supports
     direction/destination filtering; exact mechanism documented in the
     integration's README).
   - Configure to return next 5 departures.
5. The integration creates a `sensor.fornvagen_resecentrum` (or similarly
   named) entity. The dashboard binds to it.

**Fallback** — if `MrSjodin/HomeAssistant_Trafiklab_Integration` proves
unsuitable (broken, abandoned, or doesn't support direction filtering for
Östgötatrafiken stops), fall back to the `hasl-sensor/integration` HACS
integration which uses ResRobot and is more established. This is a
deviation handled during implementation, not a design change.

## Validation

After implementation:

1. **YAML syntax** — `python3 -c "import yaml; yaml.safe_load(open('/config/dashboards/entre.yaml'))"`
2. **HA config check** — `/config/scripts/ha core check`
3. **Entity references** — run the entity verification script from
   CLAUDE.md (Validating Lovelace Dashboards section) against
   `dashboards/entre.yaml`. Every referenced entity must exist and not be
   `unavailable`.
4. **Visual check** — `python3 /config/scripts/ha_screenshot.py
   /lovelace-entre/hem /config/www/screenshots/entre_hem.png 15` and view
   the screenshot to confirm landscape layout renders correctly. Repeat
   for `/lovelace-entre/ljus` and `/lovelace-entre/mer`.

## Open items (resolved at implementation time)

- Exact Fornvägen stop ID — looked up via the Trafiklab integration's
  stop-search helper.
- Whether `MrSjodin` integration provides a Lovelace card or only sensors
  — implementation chooses card vs. `entities` card binding accordingly.
(No further open items — light-group computation is decided: inline via
templates, no new group entities.)

## Out of scope

- Configuring the physical tablet (HA app kiosk URL, screen-on automation,
  etc.).
- A new HA area for the kiosk itself.
- Notifications or alerts (the kiosk is glanceable, not interactive
  beyond locks/lights/vacuum).
- Adding `lovelace-entre` to the existing `/lovelace-system` summary card.
