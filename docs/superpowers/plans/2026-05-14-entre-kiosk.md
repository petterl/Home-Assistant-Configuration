# Entré Kiosk Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a kiosk dashboard `/lovelace-entre` for a landscape wall tablet in the entré, with live cameras, weather, house-wide light toggles, bus departures, and door locks.

**Architecture:** Three-view YAML Lovelace dashboard (`Hem`, `Ljus`, `Mer`) using `custom:grid-layout` for landscape grids and `mushroom-template-card` for room/door/scene tiles. One new HACS integration (`MrSjodin/HomeAssistant_Trafiklab_Integration`) provides the bus departure sensor.

**Tech Stack:** Home Assistant YAML dashboards, layout-card, mushroom-cards, picture-glance, HACS, Trafiklab Realtime API.

**Spec:** `docs/superpowers/specs/2026-05-14-entre-kiosk-design.md`

**Verification pattern:** Because Lovelace dashboards have no unit tests, every visible task ends with the four CLAUDE.md validation steps:

1. `python3 -c "import yaml; yaml.safe_load(open('/config/dashboards/entre.yaml'))"` — YAML syntax
2. `/config/scripts/ha core check` — HA config
3. Entity reference check (script in CLAUDE.md "Validating Lovelace Dashboards")
4. `python3 /config/scripts/ha_screenshot.py "/lovelace-entre/<view>" "/config/www/screenshots/entre_<view>.png" 15` — visual check, then read the PNG

**Commit policy:** The user's CLAUDE.md says always ask before pushing. This plan creates *local* commits at each green checkpoint (no `git push`). If the user prefers a single squash at the end, skip the per-task commit steps and commit once at the end.

---

## Task 1: Install Trafiklab HACS integration and configure Fornvägen stop

This task is **mostly manual** because HACS install and integration config happen in the HA UI. The user must do steps 1–5; the agent verifies step 6.

**Files:**
- Modify: `/config/secrets.yaml` (add `trafiklab_api_key`)

- [ ] **Step 1: Request a Trafiklab Realtime API key** (user action)

The user goes to https://www.trafiklab.se, creates an account if needed, creates a new project, and requests an API key for the **Realtime API** (free tier). Copy the key.

- [ ] **Step 2: Add the API key to secrets.yaml** (agent or user)

Add this line to `/config/secrets.yaml`:

```yaml
trafiklab_api_key: <KEY-FROM-STEP-1>
```

Do **not** commit `secrets.yaml` (already in `.gitignore`).

- [ ] **Step 3: Install the HACS integration** (user action)

In HA → HACS → Integrations → ⋮ → Custom repositories → add:
- Repository: `https://github.com/MrSjodin/HomeAssistant_Trafiklab_Integration`
- Type: Integration

Then HACS → Integrations → search "Trafiklab" → Download → restart HA:

```bash
/config/scripts/ha core restart
```

- [ ] **Step 4: Configure the integration in HA UI** (user action)

Settings → Devices & Services → Add Integration → "Trafiklab Realtime".
- Enter the API key from step 1.
- Add a **Departures** sensor:
  - Stop search: "Fornvägen" → select the Fornvägen stop in Linköping
  - Direction filter: Resecentrum (or whichever the integration UI calls this — destination filter)
  - Departures to return: 5
- Save.

If "Fornvägen" returns multiple stops, pick the one closest to the user's home. If the UI doesn't support direction filtering directly, the dashboard will filter in templates at render time (Task 6 covers this fallback).

- [ ] **Step 5: Verify the sensor exists**

Run:

```bash
/config/scripts/ha search 'fornvagen|trafiklab' | head -20
```

Expected: at least one `sensor.*fornvagen*` (or similar) entity in the output, **not** `unavailable`.

Record the exact sensor entity_id — Task 6 will reference it. Note it here in the plan as a comment before continuing:

```
SENSOR_ID = sensor.________________________
```

- [ ] **Step 6: Check the sensor returns departures**

```bash
/config/scripts/ha state <SENSOR_ID>
```

Expected: state contains a time/minutes value, and `attributes` contains a list of upcoming departures with line numbers and destinations.

If the sensor is `unknown` for >5 minutes, retry the integration config (wrong stop ID is the usual cause). Worst case, fall back to `hasl-sensor/integration` (HACS) per the spec.

- [ ] **Step 7: Fallback path** — if `MrSjodin/HomeAssistant_Trafiklab_Integration` is broken or unavailable

Repeat steps 3–6 with `hasl-sensor/integration` instead:
- HACS Custom Repositories → `https://github.com/hasl-sensor/integration` as Integration
- Configure a "Departures" sensor (HASL exposes ResRobot-backed sensors). The Fornvägen stop ID comes from ResRobot's stop-search.
- Document the chosen integration in the plan checkbox above.

No commit at this task — `secrets.yaml` is excluded from git, and no dashboard files exist yet.

---

## Task 2: Create dashboard skeleton and register it

**Files:**
- Create: `/config/dashboards/entre.yaml`
- Modify: `/config/configuration.yaml` (add dashboard entry under `lovelace.dashboards`)

- [ ] **Step 1: Create empty 3-view skeleton at `/config/dashboards/entre.yaml`**

```yaml
title: Entré

views:
  - title: Hem
    path: hem
    icon: mdi:home
    type: custom:grid-layout
    layout:
      grid-template-columns: 1fr 1fr 1fr
      grid-template-rows: auto
      grid-template-areas: |
        "header header header"
        "cam1   cam2   cam3"
        "doors  doors  buses"
    cards: []

  - title: Ljus
    path: ljus
    icon: mdi:lightbulb-group
    type: custom:grid-layout
    layout:
      grid-template-columns: repeat(4, 1fr)
      grid-template-rows: auto
    cards: []

  - title: Mer
    path: mer
    icon: mdi:dots-horizontal
    type: custom:grid-layout
    layout:
      grid-template-columns: 1fr 1fr 1fr
      grid-template-rows: auto
    cards: []
```

- [ ] **Step 2: Register the dashboard in configuration.yaml**

In `/config/configuration.yaml`, in the `lovelace.dashboards` block, append after the `lovelace-vatten` entry (around line 83):

```yaml
    lovelace-entre:
      mode: yaml
      title: Entré
      icon: mdi:tablet-dashboard
      show_in_sidebar: true
      filename: dashboards/entre.yaml
```

- [ ] **Step 3: Validate YAML syntax**

```bash
python3 -c "import yaml; yaml.safe_load(open('/config/dashboards/entre.yaml')); print('OK')"
```

Expected: `OK`.

- [ ] **Step 4: Validate HA config**

```bash
/config/scripts/ha core check
```

Expected: ends with `Configuration valid!` (or equivalent success message).

- [ ] **Step 5: Reload HA (or restart if necessary)**

A config-only change to `lovelace.dashboards` requires a full restart:

```bash
/config/scripts/ha core restart
```

Wait ~30s for HA to come back up.

- [ ] **Step 6: Verify the dashboard appears in the sidebar**

```bash
curl -s "http://supervisor/core/api/lovelace/dashboards" -H "Authorization: Bearer $SUPERVISOR_TOKEN" | python3 -m json.tool | grep -A 2 lovelace-entre
```

Expected: an entry with `url_path: lovelace-entre`.

- [ ] **Step 7: Visual check — empty dashboard renders**

```bash
python3 /config/scripts/ha_screenshot.py "/lovelace-entre/hem" "/config/www/screenshots/entre_hem_skeleton.png" 15
```

Then `Read` the file — confirm a blank dashboard with three tabs visible (`Hem`, `Ljus`, `Mer`).

- [ ] **Step 8: Commit**

```bash
git add /config/dashboards/entre.yaml /config/configuration.yaml
git commit -m "feat(dashboard): add empty entré kiosk dashboard skeleton"
```

---

## Task 3: Hem view — header (clock + weather)

**Files:**
- Modify: `/config/dashboards/entre.yaml` (Hem view, `cards:`)

- [ ] **Step 1: Add the header markdown card**

Replace the Hem view's `cards: []` with a list containing this single markdown card:

```yaml
    cards:
      - type: markdown
        view_layout:
          grid-area: header
        content: |
          ## {{ now().strftime('%H:%M') }} — {{ ['måndag','tisdag','onsdag','torsdag','fredag','lördag','söndag'][now().weekday()] }} {{ now().day }} {{ ['januari','februari','mars','april','maj','juni','juli','augusti','september','oktober','november','december'][now().month - 1] }}

          **{{ states('weather.forecast_hem') | replace('partlycloudy','Delvis molnigt') | replace('cloudy','Molnigt') | replace('sunny','Soligt') | replace('clear-night','Klart') | replace('rainy','Regn') | replace('snowy','Snö') | replace('fog','Dimma') | title }}** · {{ state_attr('weather.forecast_hem','temperature') }} °C
        card_mod:
          style: |
            ha-card {
              background: rgba(var(--rgb-primary-text-color), 0.05);
              text-align: center;
            }
```

- [ ] **Step 2: Validate**

```bash
python3 -c "import yaml; yaml.safe_load(open('/config/dashboards/entre.yaml')); print('OK')"
/config/scripts/ha core check
```

Both expected to pass.

- [ ] **Step 3: Verify the weather entity exists**

```bash
/config/scripts/ha state weather.forecast_hem
```

Expected: state like `partlycloudy`, attributes include `temperature`.

- [ ] **Step 4: Reload Lovelace and screenshot**

YAML dashboards reload automatically on file save. Take screenshot:

```bash
python3 /config/scripts/ha_screenshot.py "/lovelace-entre/hem" "/config/www/screenshots/entre_hem_header.png" 15
```

Read the PNG. Expected: a header showing current time, Swedish weekday + date, and weather state + temp.

- [ ] **Step 5: Commit**

```bash
git add /config/dashboards/entre.yaml
git commit -m "feat(dashboard): add Hem header (clock + weather)"
```

---

## Task 4: Hem view — three camera tiles

**Files:**
- Modify: `/config/dashboards/entre.yaml` (Hem view, append three picture-glance cards)

- [ ] **Step 1: Verify camera entities are recording**

```bash
/config/scripts/ha state camera.ringklocka_high_resolution_channel
/config/scripts/ha state camera.uppfart_high_resolution_channel
/config/scripts/ha state camera.garage_high_resolution_channel
```

Expected: each returns state `recording` or `idle`, not `unavailable`.

- [ ] **Step 2: Append the three camera cards to the Hem view**

After the header markdown card in the Hem view's `cards:` list, add:

```yaml
      - type: picture-glance
        view_layout:
          grid-area: cam1
        title: Ringklocka
        camera_image: camera.ringklocka_high_resolution_channel
        camera_view: live
        entities: []
        tap_action:
          action: more-info
          entity: camera.ringklocka_high_resolution_channel

      - type: picture-glance
        view_layout:
          grid-area: cam2
        title: Uppfart
        camera_image: camera.uppfart_high_resolution_channel
        camera_view: live
        entities: []
        tap_action:
          action: more-info
          entity: camera.uppfart_high_resolution_channel

      - type: picture-glance
        view_layout:
          grid-area: cam3
        title: Garage
        camera_image: camera.garage_high_resolution_channel
        camera_view: live
        entities: []
        tap_action:
          action: more-info
          entity: camera.garage_high_resolution_channel
```

- [ ] **Step 3: Validate**

```bash
python3 -c "import yaml; yaml.safe_load(open('/config/dashboards/entre.yaml')); print('OK')"
/config/scripts/ha core check
```

- [ ] **Step 4: Screenshot and verify**

```bash
python3 /config/scripts/ha_screenshot.py "/lovelace-entre/hem" "/config/www/screenshots/entre_hem_cameras.png" 20
```

Cameras need extra time to render — use `20` seconds. Read the PNG. Expected: three camera tiles below the header, all showing live feeds (not "loading" placeholders). If any are still loading, increase the screenshot delay to `30` and re-take.

- [ ] **Step 5: Commit**

```bash
git add /config/dashboards/entre.yaml
git commit -m "feat(dashboard): add three live camera tiles to Hem view"
```

---

## Task 5: Hem view — doors & locks strip

**Files:**
- Modify: `/config/dashboards/entre.yaml` (Hem view, append doors block)

- [ ] **Step 1: Verify door/lock entities**

```bash
/config/scripts/ha state lock.entre_2
/config/scripts/ha state lock.groventre_3
/config/scripts/ha state binary_sensor.entre_dorr_2
/config/scripts/ha state binary_sensor.groventre_dorr_2
/config/scripts/ha state binary_sensor.garagedorr_dorr_2
```

Expected: all five return valid states.

- [ ] **Step 2: Append the doors-and-locks card**

After the three camera cards, append:

```yaml
      - type: vertical-stack
        view_layout:
          grid-area: doors
        cards:
          - type: markdown
            content: "## Dörrar & lås"

          - type: tile
            entity: lock.entre_2
            name: Entré
            icon: mdi:door
            features:
              - type: lock-commands
              - type: lock-open-door

          - type: custom:mushroom-template-card
            primary: ""
            secondary: >-
              Dörr: {% if is_state('binary_sensor.entre_dorr_2','on') %}Öppen{% else %}Stängd{% endif %}
            icon: mdi:door-closed
            icon_color: >-
              {% if is_state('binary_sensor.entre_dorr_2','on') %}red{% else %}grey{% endif %}
            tap_action:
              action: more-info
              entity: binary_sensor.entre_dorr_2

          - type: tile
            entity: lock.groventre_3
            name: Groventré
            icon: mdi:door
            features:
              - type: lock-commands

          - type: custom:mushroom-template-card
            primary: ""
            secondary: >-
              Dörr: {% if is_state('binary_sensor.groventre_dorr_2','on') %}Öppen{% else %}Stängd{% endif %}
            icon: mdi:door-closed
            icon_color: >-
              {% if is_state('binary_sensor.groventre_dorr_2','on') %}red{% else %}grey{% endif %}
            tap_action:
              action: more-info
              entity: binary_sensor.groventre_dorr_2

          - type: custom:mushroom-template-card
            primary: Garage
            secondary: >-
              {% if is_state('binary_sensor.garagedorr_dorr_2','on') %}Öppen{% else %}Stängd{% endif %}
            icon: mdi:garage
            icon_color: >-
              {% if is_state('binary_sensor.garagedorr_dorr_2','on') %}red{% else %}green{% endif %}
            tap_action:
              action: more-info
              entity: binary_sensor.garagedorr_dorr_2
```

**Why two cards per door**: Lovelace's `service:` field can't be templated, so a single tap-target can't dynamically choose lock vs unlock. The HA-native `tile` card has built-in lock/unlock controls (`lock-commands` feature) that handle both directions correctly. The accompanying mushroom card shows door open/closed status next to it.

The `lock-open-door` feature on entré requires the lock to support remote door-opening; if it doesn't, HA hides the feature automatically (no harm).

- [ ] **Step 3: Validate**

```bash
python3 -c "import yaml; yaml.safe_load(open('/config/dashboards/entre.yaml')); print('OK')"
/config/scripts/ha core check
```

- [ ] **Step 4: Screenshot and verify**

```bash
python3 /config/scripts/ha_screenshot.py "/lovelace-entre/hem" "/config/www/screenshots/entre_hem_doors.png" 15
```

Read the PNG. Expected: doors strip in the bottom-left grid area, three rows (Entré, Groventré, Garage), each with door state + lock state shown. Do **not** tap the locks during testing — that would lock/unlock real doors.

- [ ] **Step 5: Commit**

```bash
git add /config/dashboards/entre.yaml
git commit -m "feat(dashboard): add doors & locks strip to Hem view"
```

---

## Task 6: Hem view — bus departures list

**Prerequisite:** Task 1 must be complete. The actual sensor entity_id determined during Task 1:

```
BUS_SENSOR = sensor.fornvagen_kommande_avgangar
```

**Known schema** (verified at end of Task 1):
- State: minutes until next bus (integer)
- Attribute `upcoming`: list of upcoming departures. Fields per entry:
  - `line` (e.g. `"15"`)
  - `destination` (e.g. `"Resecentrum"` or `"Södra Ullstämma"`)
  - `time_formatted` (e.g. `"13:25"`)
  - `minutes_until` (integer)
  - `delay_minutes` (integer)
  - `canceled` (bool)
  - `platform` (e.g. `"A"`, `"B"`)
- **Both directions are returned** — we filter for `destination == 'Resecentrum'` in the template.

**Files:**
- Modify: `/config/dashboards/entre.yaml` (Hem view, append bus card)

- [ ] **Step 1: Append the bus departures markdown card**

After the doors card in the Hem view's `cards:` list, append:

```yaml
      - type: markdown
        view_layout:
          grid-area: buses
        content: |
          ## Fornvägen → Resecentrum

          {% set deps = state_attr('sensor.fornvagen_kommande_avgangar', 'upcoming') or [] %}
          {% set filtered = deps | selectattr('destination', 'eq', 'Resecentrum') | list %}
          {% if filtered | length == 0 %}
          _Inga avgångar mot Resecentrum inom kort_
          {% else %}
          {% for d in filtered[:5] %}
          - **{{ d.time_formatted }}** linje {{ d.line }}{% if d.delay_minutes and d.delay_minutes != 0 %} ({{ '%+d' | format(d.delay_minutes) }} min){% endif %}{% if d.canceled %} **INSTÄLLD**{% endif %} · om {{ d.minutes_until }} min
          {% endfor %}
          {% endif %}
        card_mod:
          style: |
            ha-card {
              background: rgba(var(--rgb-primary-text-color), 0.05);
            }
```

Format per line: `**HH:MM** linje N (±D min) · om M min`. Delay is shown only if non-zero. Cancelled departures are marked.

- [ ] **Step 2: Validate**

```bash
python3 -c "import yaml; yaml.safe_load(open('/config/dashboards/entre.yaml')); print('OK')"
/config/scripts/ha core check
```

- [ ] **Step 3: Verify the template renders against the real sensor**

```bash
/config/scripts/ha template "{% set deps = state_attr('sensor.fornvagen_kommande_avgangar', 'upcoming') or [] %}{{ deps | selectattr('destination','eq','Resecentrum') | list | length }} departures to Resecentrum (of {{ deps | length }} total)"
```

Expected: a string like `2 departures to Resecentrum (of 4 total)`. The exact numbers depend on time of day; both > 0 during service hours. If the template errors, the attribute path is wrong.

- [ ] **Step 4: Screenshot and verify**

```bash
python3 /config/scripts/ha_screenshot.py "/lovelace-entre/hem" "/config/www/screenshots/entre_hem_buses.png" 15
```

Read the PNG. Expected: bus list in the bottom-right grid area showing 1–5 upcoming departures to Resecentrum.

- [ ] **Step 5: Run the entity-reference check on the whole dashboard**

Use the script from CLAUDE.md → "Validating Lovelace Dashboards" → entity verification. Paste into a heredoc:

```bash
python3 << 'EOF'
import yaml, json, urllib.request, os

with open('/config/dashboards/entre.yaml') as f:
    dashboard = yaml.safe_load(f)

entities = set()
def find_entities(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in ('entity','camera_image') and isinstance(v, str) and '.' in v:
                entities.add(v)
            elif k == 'entities' and isinstance(v, list):
                for item in v:
                    if isinstance(item, str) and '.' in item:
                        entities.add(item)
                    elif isinstance(item, dict) and 'entity' in item:
                        entities.add(item['entity'])
            else:
                find_entities(v)
    elif isinstance(obj, list):
        for item in obj:
            find_entities(item)

find_entities(dashboard)
token = os.environ['SUPERVISOR_TOKEN']
for entity in sorted(entities):
    data = json.dumps({"template": f"{{{{ states('{entity}') }}}}"}).encode()
    req = urllib.request.Request('http://supervisor/core/api/template', data=data,
        headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'})
    state = urllib.request.urlopen(req).read().decode().strip()
    status = 'X' if state in ['unavailable','unknown'] else 'OK'
    print(f"{status} {entity}: {state[:40]}")
EOF
```

Expected: every entity prints `OK`. Any `X` is a bug to fix before commit.

This catches entities referenced only inside Jinja templates (which the script's `entity`/`camera_image` extraction misses) — manually scan the YAML for `is_state(`, `states(`, `state_attr(` and verify those entity_ids too.

- [ ] **Step 6: Commit**

```bash
git add /config/dashboards/entre.yaml
git commit -m "feat(dashboard): add Fornvägen→Resecentrum bus departures to Hem view"
```

---

## Task 7: Ljus view — per-room light toggles

**Files:**
- Modify: `/config/dashboards/entre.yaml` (Ljus view, replace `cards: []`)

- [ ] **Step 1: Verify each area has lights**

```bash
for area in kok vardagsrum gastrum garage partyrummet entre utomhus; do
  echo "=== $area ==="
  /config/scripts/ha template "{{ area_entities('$area') | select('match','^light\\.') | list }}"
done
```

Expected: each area returns a non-empty list (at minimum `entre` returns `['light.takspottar_2']` and `light.water_meter_t_display_display_backlight` — filter that one out in the template; see Step 2).

If any area returns `[]`, drop it from the Ljus grid in step 2.

- [ ] **Step 2: Replace the Ljus view's `cards: []` with seven room cards**

Use a `decluttering-template`-free inline approach (no new templates needed since we already use mushroom in other views).

```yaml
    cards:
      - type: custom:mushroom-template-card
        primary: Köket
        icon: mdi:silverware-fork-knife
        secondary: >-
          {% set ls = expand(area_entities('kok')) | selectattr('domain','eq','light') | list %}
          {% set on = ls | selectattr('state','eq','on') | list | length %}
          {% if on > 0 %}{{ on }} lampor på{% else %}Alla av{% endif %}
        icon_color: >-
          {% set ls = expand(area_entities('kok')) | selectattr('domain','eq','light') | list %}
          {% if ls | selectattr('state','eq','on') | list | length > 0 %}amber{% else %}disabled{% endif %}
        tap_action:
          action: call-service
          service: light.toggle
          service_data:
            entity_id: >-
              {{ area_entities('kok') | select('match','^light\\.') | reject('search','water_meter') | list }}
        hold_action:
          action: navigate
          navigation_path: /lovelace-hem/koket

      - type: custom:mushroom-template-card
        primary: Vardagsrum
        icon: mdi:sofa
        secondary: >-
          {% set ls = expand(area_entities('vardagsrum')) | selectattr('domain','eq','light') | list %}
          {% set on = ls | selectattr('state','eq','on') | list | length %}
          {% if on > 0 %}{{ on }} lampor på{% else %}Alla av{% endif %}
        icon_color: >-
          {% set ls = expand(area_entities('vardagsrum')) | selectattr('domain','eq','light') | list %}
          {% if ls | selectattr('state','eq','on') | list | length > 0 %}amber{% else %}disabled{% endif %}
        tap_action:
          action: call-service
          service: light.toggle
          service_data:
            entity_id: "{{ area_entities('vardagsrum') | select('match','^light\\.') | list }}"
        hold_action:
          action: navigate
          navigation_path: /lovelace-hem/vardagsrum

      - type: custom:mushroom-template-card
        primary: Gästrum
        icon: mdi:bed
        secondary: >-
          {% set ls = expand(area_entities('gastrum')) | selectattr('domain','eq','light') | list %}
          {% set on = ls | selectattr('state','eq','on') | list | length %}
          {% if on > 0 %}{{ on }} lampor på{% else %}Alla av{% endif %}
        icon_color: >-
          {% set ls = expand(area_entities('gastrum')) | selectattr('domain','eq','light') | list %}
          {% if ls | selectattr('state','eq','on') | list | length > 0 %}amber{% else %}disabled{% endif %}
        tap_action:
          action: call-service
          service: light.toggle
          service_data:
            entity_id: "{{ area_entities('gastrum') | select('match','^light\\.') | list }}"
        hold_action:
          action: navigate
          navigation_path: /lovelace-hem/gastrum

      - type: custom:mushroom-template-card
        primary: Garage
        icon: mdi:garage
        secondary: >-
          {% set ls = expand(area_entities('garage')) | selectattr('domain','eq','light') | list %}
          {% set on = ls | selectattr('state','eq','on') | list | length %}
          {% if on > 0 %}{{ on }} lampor på{% else %}Alla av{% endif %}
        icon_color: >-
          {% set ls = expand(area_entities('garage')) | selectattr('domain','eq','light') | list %}
          {% if ls | selectattr('state','eq','on') | list | length > 0 %}amber{% else %}disabled{% endif %}
        tap_action:
          action: call-service
          service: light.toggle
          service_data:
            entity_id: "{{ area_entities('garage') | select('match','^light\\.') | list }}"
        hold_action:
          action: navigate
          navigation_path: /lovelace-hem/garage

      - type: custom:mushroom-template-card
        primary: Partyrummet
        icon: mdi:party-popper
        secondary: >-
          {% set ls = expand(area_entities('partyrummet')) | selectattr('domain','eq','light') | list %}
          {% set on = ls | selectattr('state','eq','on') | list | length %}
          {% if on > 0 %}{{ on }} lampor på{% else %}Alla av{% endif %}
        icon_color: >-
          {% set ls = expand(area_entities('partyrummet')) | selectattr('domain','eq','light') | list %}
          {% if ls | selectattr('state','eq','on') | list | length > 0 %}amber{% else %}disabled{% endif %}
        tap_action:
          action: call-service
          service: light.toggle
          service_data:
            entity_id: "{{ area_entities('partyrummet') | select('match','^light\\.') | list }}"
        hold_action:
          action: navigate
          navigation_path: /lovelace-hem/partyrummet

      - type: custom:mushroom-template-card
        primary: Entré
        icon: mdi:door-open
        secondary: >-
          {% if is_state('light.takspottar_2','on') %}På{% else %}Av{% endif %}
        icon_color: >-
          {% if is_state('light.takspottar_2','on') %}amber{% else %}disabled{% endif %}
        tap_action:
          action: call-service
          service: light.toggle
          service_data:
            entity_id: light.takspottar_2
        hold_action:
          action: navigate
          navigation_path: /lovelace-hem/entre

      - type: custom:mushroom-template-card
        primary: Utomhus
        icon: mdi:tree
        secondary: >-
          {% set ls = expand(area_entities('utomhus')) | selectattr('domain','eq','light') | list %}
          {% set on = ls | selectattr('state','eq','on') | list | length %}
          {% if on > 0 %}{{ on }} lampor på{% else %}Alla av{% endif %}
        icon_color: >-
          {% set ls = expand(area_entities('utomhus')) | selectattr('domain','eq','light') | list %}
          {% if ls | selectattr('state','eq','on') | list | length > 0 %}amber{% else %}disabled{% endif %}
        tap_action:
          action: call-service
          service: light.toggle
          service_data:
            entity_id: "{{ area_entities('utomhus') | select('match','^light\\.') | list }}"
        hold_action:
          action: navigate
          navigation_path: /lovelace-hem/utomhus
```

**Note on `light.toggle` behavior**: with mixed states (some lights on, some off in the same room), `light.toggle` flips each light individually rather than the room as a whole. The first tap leaves mixed states; the second tap resolves to "all off" or "all on" depending on starting state. This is acceptable for kiosk use; if it's too quirky in practice, a follow-up can introduce a script `script.toggle_area_lights` that decides on/off based on majority state.

**Note on the Entré card**: it controls a single light entity rather than the whole area, because the area contains `light.water_meter_t_display_display_backlight` which is not a real ceiling light. If the area gains more genuine lights later, swap this card to use the area-based template like the others.

**Note on `hold_action` navigation paths**: these should match the view paths in `dashboards/hem.yaml`. Verify in step 4 below before committing.

- [ ] **Step 3: Validate**

```bash
python3 -c "import yaml; yaml.safe_load(open('/config/dashboards/entre.yaml')); print('OK')"
/config/scripts/ha core check
```

- [ ] **Step 4: Verify the Hem dashboard view paths used in `hold_action`**

```bash
grep -E '^  *path:' /config/dashboards/hem.yaml
```

For any room above whose path doesn't exist in `hem.yaml` (e.g., maybe it's `kok` not `koket`), update the `navigation_path` in the corresponding card. Re-run the YAML and HA validators after edits.

- [ ] **Step 5: Verify a template renders**

```bash
/config/scripts/ha template "{{ area_entities('kok') | select('match','^light\\.') | list }}"
```

Expected: a list of light entity_ids.

- [ ] **Step 6: Screenshot and verify**

```bash
python3 /config/scripts/ha_screenshot.py "/lovelace-entre/ljus" "/config/www/screenshots/entre_ljus.png" 15
```

Read the PNG. Expected: a 4-column grid of seven room tiles. Tiles for rooms with lights currently on should show amber icons.

- [ ] **Step 7: Commit**

```bash
git add /config/dashboards/entre.yaml
git commit -m "feat(dashboard): add Ljus view with per-room light toggles"
```

---

## Task 8: Mer view — vacuum, scenes, birdcage camera

**Files:**
- Modify: `/config/dashboards/entre.yaml` (Mer view, replace `cards: []`)

- [ ] **Step 1: Verify vacuum and birdcage entities**

```bash
/config/scripts/ha state vacuum.roborock_de_118057288_s5
/config/scripts/ha state sensor.roborock_de_118057288_s5_battery_level_p_3_1
/config/scripts/ha state camera.birdcage
```

Expected: all three return valid states.

- [ ] **Step 2: Replace the Mer view's `cards: []` with vacuum + scenes + birdcage**

```yaml
    cards:
      - type: custom:mushroom-template-card
        primary: Dammsugare (Gun Gun)
        secondary: >-
          {{ states('vacuum.roborock_de_118057288_s5') | capitalize }} · {{ states('sensor.roborock_de_118057288_s5_battery_level_p_3_1') }}%
        icon: mdi:robot-vacuum
        icon_color: >-
          {% set s = states('vacuum.roborock_de_118057288_s5') %}
          {% if s == 'cleaning' %}blue
          {% elif s == 'error' %}red
          {% elif s == 'docked' %}green{% else %}grey{% endif %}
        tap_action:
          action: more-info
          entity: vacuum.roborock_de_118057288_s5

      - type: horizontal-stack
        cards:
          - type: custom:mushroom-template-card
            primary: Start
            icon: mdi:play
            icon_color: green
            tap_action:
              action: call-service
              service: vacuum.start
              service_data:
                entity_id: vacuum.roborock_de_118057288_s5
          - type: custom:mushroom-template-card
            primary: Pausa
            icon: mdi:pause
            icon_color: amber
            tap_action:
              action: call-service
              service: vacuum.pause
              service_data:
                entity_id: vacuum.roborock_de_118057288_s5
          - type: custom:mushroom-template-card
            primary: Dock
            icon: mdi:home-import-outline
            icon_color: blue
            tap_action:
              action: call-service
              service: vacuum.return_to_base
              service_data:
                entity_id: vacuum.roborock_de_118057288_s5

      - type: custom:mushroom-template-card
        primary: Allt släckt
        icon: mdi:lightbulb-off
        icon_color: grey
        tap_action:
          action: call-service
          service: light.turn_off
          service_data:
            entity_id: all

      - type: custom:mushroom-template-card
        primary: Välkommen hem
        icon: mdi:home-heart
        icon_color: amber
        tap_action:
          action: call-service
          service: light.turn_on
          service_data:
            entity_id: >-
              {{ (area_entities('utomhus') | select('match','^light\\.') | list)
                + ['light.takspottar_2'] }}

      - type: custom:mushroom-template-card
        primary: Natt
        icon: mdi:weather-night
        icon_color: indigo
        tap_action:
          action: call-service
          service: light.turn_off
          service_data:
            entity_id: all

      - type: picture-glance
        title: Fågelbur
        camera_image: camera.birdcage
        camera_view: live
        entities: []
        tap_action:
          action: more-info
          entity: camera.birdcage
```

**Note on "Natt" vs "Allt släckt"**: the spec said *Natt* should "turn off all lights except designated night-lights" — but the project has no night-lights defined as a labeled group. Until such a group exists, **Natt** behaves identically to **Allt släckt**. If the user wants distinct behavior, they should later create a `light.night_lights` group and update this card.

- [ ] **Step 3: Validate**

```bash
python3 -c "import yaml; yaml.safe_load(open('/config/dashboards/entre.yaml')); print('OK')"
/config/scripts/ha core check
```

- [ ] **Step 4: Screenshot and verify**

```bash
python3 /config/scripts/ha_screenshot.py "/lovelace-entre/mer" "/config/www/screenshots/entre_mer.png" 20
```

Read the PNG. Expected: a vacuum tile, three start/pause/dock buttons, three scene buttons (Allt släckt / Välkommen hem / Natt), and the birdcage camera tile.

- [ ] **Step 5: Commit**

```bash
git add /config/dashboards/entre.yaml
git commit -m "feat(dashboard): add Mer view (vacuum, scenes, birdcage)"
```

---

## Task 9: Final validation pass

**Files:** none modified.

- [ ] **Step 1: Full entity reference scan**

Run the entity verification script from CLAUDE.md against the final dashboard:

```bash
python3 << 'EOF'
import yaml, json, urllib.request, os, re

with open('/config/dashboards/entre.yaml') as f:
    raw = f.read()
    dashboard = yaml.safe_load(raw)

entities = set()
def find_entities(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in ('entity','camera_image') and isinstance(v, str) and '.' in v:
                entities.add(v)
            elif k == 'entities' and isinstance(v, list):
                for item in v:
                    if isinstance(item, str) and '.' in item:
                        entities.add(item)
                    elif isinstance(item, dict) and 'entity' in item:
                        entities.add(item['entity'])
            else:
                find_entities(v)
    elif isinstance(obj, list):
        for item in obj:
            find_entities(item)

find_entities(dashboard)

# Also pick up entities referenced inside Jinja templates
for m in re.finditer(r"(?:is_state|states|state_attr)\s*\(\s*['\"]([a-z_]+\.[a-z0-9_]+)['\"]", raw):
    entities.add(m.group(1))
for m in re.finditer(r"entity_id:\s*['\"]?([a-z_]+\.[a-z0-9_]+)['\"]?\b", raw):
    entities.add(m.group(1))

token = os.environ['SUPERVISOR_TOKEN']
bad = []
for entity in sorted(entities):
    data = json.dumps({"template": f"{{{{ states('{entity}') }}}}"}).encode()
    req = urllib.request.Request('http://supervisor/core/api/template', data=data,
        headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'})
    state = urllib.request.urlopen(req).read().decode().strip()
    status = 'X' if state in ['unavailable','unknown'] else 'OK'
    if status == 'X':
        bad.append(entity)
    print(f"{status} {entity}: {state[:40]}")

print(f"\n{len(bad)} broken entity references: {bad}")
EOF
```

Expected: `0 broken entity references`. Fix any reported bad entities and re-run before continuing.

- [ ] **Step 2: Screenshot all three views**

```bash
python3 /config/scripts/ha_screenshot.py "/lovelace-entre/hem"  "/config/www/screenshots/entre_final_hem.png"  20
python3 /config/scripts/ha_screenshot.py "/lovelace-entre/ljus" "/config/www/screenshots/entre_final_ljus.png" 15
python3 /config/scripts/ha_screenshot.py "/lovelace-entre/mer"  "/config/www/screenshots/entre_final_mer.png"  20
```

Read each PNG. Confirm:
- **Hem**: header (clock + weather), three live cameras, doors/locks strip, bus list.
- **Ljus**: 4-column grid of 7 room tiles, correct on/off colors.
- **Mer**: vacuum tile + start/pause/dock row, three scene buttons, birdcage live camera.

- [ ] **Step 3: HA log check**

```bash
/config/scripts/ha core logs | grep -iE 'error|warning' | grep -iE 'entre|trafiklab' | head -20
```

Expected: no errors mentioning the new dashboard or Trafiklab. Investigate any matches.

- [ ] **Step 4: Ask the user before pushing**

CLAUDE.md rule: always ask before pushing. Show the user the commits made so far:

```bash
git log --oneline master..HEAD
```

Then ask: "Ready to push these N commits to master?" — only push on explicit yes:

```bash
git push https://<github_pat>@github.com/<github_repo>.git master
```

(Read `github_pat` and `github_repo` from `secrets.yaml`.)

---

## Risk register

- **Camera streams hurt tablet performance** — if the tablet struggles with three live streams, downgrade `camera_view: live` to `camera_view: auto` on the Hem cameras (auto uses a stream when interacting, snapshot otherwise). This is a one-line change.
- **Trafiklab API rate limits** — the free tier has request limits. The integration handles polling intervals; default should be safe. If departures stop updating, check the integration's logs.
- **Door lock tap actions are immediate** — there's no confirmation dialog before locking/unlocking. If the user prefers a confirmation step, wrap each lock tap_action in a `confirmation: text:` block. This is a known trade-off chosen for speed of kiosk use.
