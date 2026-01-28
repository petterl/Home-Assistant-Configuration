# Home Assistant - Intel NUC / Proxmox

## Setup
Family home (4-6 rooms). Lights, blinds, sensors. Full energy monitoring.
- Owner: Petter (primary phone: `notify.mobile_app_petter_iphone`)
- Kids' rooms: Ida, Moa

## Infrastructure
| Service | Host | Notes |
|---------|------|-------|
| Home Assistant | 192.168.1.60 | Proxmox VM |
| MariaDB | 192.168.1.61:3306 | Recorder, 10-day retention |
| InfluxDB | 192.168.1.62:8086 | Long-term → Grafana |
| MQTT | 192.168.1.63:1883 | Mosquitto |
| Zigbee | ConBee II | Z2M channel 11, frontend :8099, addon ID: `45df7312_zigbee2mqtt` |
| Reverse proxy | 192.168.1.70 | External HTTPS access |
| Home Connect | Cloud | Neff oven & hob (no energy data) |
| UniFi Protect | 192.168.1.1 (Zeus) | Cameras: ringklocka, uppfart, garage |
| Synology NAS | 192.168.1.50 (Atlas) | 8-bay NAS, backup storage |

## Custom Components
| Component | Purpose |
|-----------|---------|
| nordpool | Electricity spot prices (SE3) |
| smartthinq_sensors | LG appliances (torktumlare, 2x refrigerators) |
| icloud3 | Device tracking |
| forecast_solar | Solar production forecasts |
| unifi | UniFi network devices |
| unifiprotect | UniFi Protect cameras |
| synology_dsm | Synology NAS monitoring |

## File Structure
| File | Purpose |
|------|---------|
| `configuration.yaml` | Main config, includes, recorder, influxdb |
| `automations.yaml` | All automations |
| `template_sensors.yaml` | Template sensors (electricity pricing) |
| `sql_sensors.yaml` | SQL sensor (peak power) |
| `statistics_sensors.yaml` | Statistics sensors (24h energy) |
| `zigbee2mqtt/configuration.yaml` | Z2M devices and groups |
| `secrets.yaml` | Credentials (not in git) |
| `scripts/` | Utility scripts |
| `scripts/ha` | HA CLI wrapper (use for config validation, restarts) |
| `scripts/generate_claude_snapshot.py` | Generates codebase snapshot |
| `scripts/ha_screenshot.py` | Take dashboard screenshots |
| `esphome/` | ESPHome device configs (water meter, BT proxy) |

## Naming Conventions
- **Zigbee friendly names**: Swedish ("Ida tryckknapp", "Moas rullgardin")
- **Entity IDs**: snake_case with room prefix (`cover.idas_rullgardin`, `switch.moa_smartplug`)
- **Automation IDs**: snake_case (`ida_knapp_rullgardin_ner`)
- **Automation aliases**: Swedish, "Room/subject - Action" format ("Ida knapp - Rullgardin ner")
- **Notifications**: Swedish text

## Key Entities
| Entity | Purpose |
|--------|---------|
| `sensor.smart_meter_ts_65a_3_aktiv_effekt` | Real-time grid power (W) |
| `sensor.solarnet_effekt_solceller` | Current solar production (W) |
| `sensor.peak_power_5th_highest` | 5th highest power peak (kW) |
| `sensor.peak_power_top_5_average` | Average of top 5 peaks (kW) |
| `sensor.nordpool_kwh_se3_sek_3_10_025` | Current electricity price (SEK/kWh) |
| `sensor.energy_production_today` | Forecasted solar production today (kWh) |
| `sensor.water_meter_t_display_total_water_consumption` | Total water consumption (m³) |
| `binary_sensor.vatten_rinner` | Water flow detected (leak detection) |

## Energy Monitoring
- **Solar & Grid**: Fronius inverter with Smart Meter TS 65A-3 (all energy data from single source)
- **Solar Forecast**: Forecast.Solar integration for production predictions
- **Per-device**: Smart plugs with power metering (FTX, CASA, Frys, Ida, Moa)
- **Appliances**:
  - Neff oven/hob via Home Connect (status only, no energy)
  - LG torktumlare via SmartThinQ (has energy data)
- **Peak power pricing**: Summer (Apr-Oct) 22 kr/kW, Winter (Nov-Mar) 43 kr/kW

## Zigbee Devices
| Room | Devices |
|------|---------|
| Idas rum | Tryckknapp, rullgardin, smartplug, repeater |
| Moas rum | Tryckknapp, rullgardin, smartplug, repeater |
| Gästrum | Tryckknapp, 2x gardin (group), repeater |
| Tvättstuga | FTX, CASA |
| Partyrummet | Frys |

Bindings: Buttons bound directly to blinds/plugs for offline control.

## ESPHome Devices
| Device | Purpose |
|--------|---------|
| `t-display` (water meter) | Kamstrup Multical 21 water meter reader via wM-Bus |
| `bt-proxy-1` | Bluetooth proxy with iGrill thermometer support |

Water meter: LilyGo T-Display with CC1101 radio module, receives encrypted wM-Bus transmissions.

## Cameras (UniFi Protect)
| Camera | Location |
|--------|----------|
| `camera.ringklocka_*` | Front door (doorbell with AI detection) |
| `camera.uppfart_*` | Driveway |
| `camera.garage_*` | Garage |

All cameras support: motion, person, vehicle, animal, smoke/CO detection.

## Media Players (Sonos)
| Room | Device |
|------|--------|
| Köket | Sonos One |
| Vardagsrum | Sonos Playbar (ljud) |
| Garage | Sonos One |
| Partyrummet | Sonos system (sub + surrounds) |
| Portabel | Sonos Move |
| Idas rum | Clock (display) |
| Moas rum | Mini |

Group: `media_player.alla_hogtalare`

## LG Appliances (SmartThinQ)
| Appliance | Entities |
|-----------|----------|
| Torktumlare | `sensor.torktumlare_*` - status, energy, job state |
| Höger kyl | `climate.hoger_kyl_*`, `sensor.hoger_kyl_*` |
| Vänster kyl | `climate.vanster_kyl_*`, `sensor.vanster_kyl_*` |

Refrigerators have climate controls for fridge and freezer compartments.

## External Switches
| Switch | Purpose |
|--------|---------|
| `switch.uttag_brevlada` | Outdoor outlet at mailbox |
| `switch.uttag_syrepump` | Oxygen pump (aquarium/pond) |

## Git Sync
Automations auto-pull from GitHub on webhook, startup, and every 6h.
Smart reload: only restarts services whose files changed (automations, scripts, scenes, Z2M).

### Git Workflow Rules
1. **Always ask user before pushing** - Never push without explicit permission
2. **Smart commit messages** - Use descriptive messages based on what changed (not generic timestamps)
3. **Handle untracked files first** - New files must be added to git or .gitignore before pushing
4. **Stage specific files** - Use `git add <specific-files>`, never `git add -A` or `git add .`

### Git Push (for Claude)
When asked to commit and push changes:
1. Check for untracked files first: `git ls-files --others --exclude-standard`
2. If untracked files exist, ask user: add to git or .gitignore?
3. Stage specific files: `git add <files>`
4. Commit with descriptive message: `git commit -m "Update automations and template sensors"`
5. Push using PAT from secrets.yaml:
   ```bash
   git push https://<github_pat>@github.com/<github_repo>.git master
   ```
   Read `secrets.yaml` for `github_pat` and `github_repo` values.

### Commit Message Format
- `Update automations` - when automations.yaml changed
- `Update configuration` - when configuration.yaml changed
- `Update ESPHome: device-name` - when esphome/ changed
- `Update dashboards` - when dashboards/ changed
- `feat: Description` - new features
- `fix: Description` - bug fixes

### Querying HA Entities (for Claude)
Use the Supervisor API to query entity states and validate automations.
The `$SUPERVISOR_TOKEN` environment variable is automatically available.

**Find entities by pattern:**
```bash
curl -s -X POST "http://supervisor/core/api/template" \
  -H "Authorization: Bearer $SUPERVISOR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"template": "{{ states | selectattr(\"entity_id\", \"search\", \"PATTERN\") | map(attribute=\"entity_id\") | list }}"}'
```

**Get entity state and attributes:**
```bash
curl -s -X POST "http://supervisor/core/api/template" \
  -H "Authorization: Bearer $SUPERVISOR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"template": "{{ states(\"sensor.example\") }} - {{ state_attr(\"sensor.example\", \"attribute_name\") }}"}'
```

**Validate template expressions:**
```bash
curl -s -X POST "http://supervisor/core/api/template" \
  -H "Authorization: Bearer $SUPERVISOR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"template": "{{ YOUR_TEMPLATE_HERE }}"}'
```

Always verify entity names exist before creating automations.

## Backups
- Proxmox VM snapshots
- HA built-in snapshots
- Git (this repo) for config
- External backup

## Current Focus
- Database performance & stability
- Expanding Zigbee mesh
- Building automations (lights, blinds, sensors)
- Lovelace & Grafana dashboards
- Google Home/Alexa integration
- Water leak detection automations

## Best Practices

### Config Changes
1. Always validate YAML before restart: `/config/scripts/ha core check`
2. Test automations in Developer Tools → Services first
3. Commit working config to git before major changes
4. Use `secrets.yaml` for all credentials: `!secret key_name`

### Database Health
- Exclude noisy entities from recorder (updates, system sensors)
- InfluxDB: only store what you'll graph
- Monitor MariaDB size, should stay stable with 10-day purge

### Zigbee Reliability
- Mains-powered devices act as routers → better mesh
- Pair new devices close to coordinator, then relocate
- Swedish friendly names for consistency

### Energy Dashboard
- Fronius Smart Meter: provides all solar and grid data via Solarnet integration
- Exclude high-frequency energy sensors from recorder if causing bloat

### Automations
- Keep it simple, one trigger/action to start
- Use scripts for reusable logic
- Blueprints for common patterns (motion lights, etc.)
- **NEVER use `!secret` in automations.yaml** - prevents UI editing. Use hardcoded values or move secret-dependent automations to configuration.yaml

## Quick Reference

### Startup Tasks (for Claude)
Run these commands at the start of each session after addon restart to ensure tools are available:

```bash
# Install required pip packages (PEP 668 workaround)
pip install --break-system-packages pyyaml selenium 2>/dev/null || true
```

The addon's `persistent_pip_packages` config doesn't handle PEP 668, so this manual install is needed.

### HA CLI Wrapper (for Claude)
The `ha` command is available via `/config/scripts/ha`. **Always use this to validate config after changes.**

**WARNING:** NEVER run `ha core stop` - Claude runs in a HA addon, so stopping HA will kill the addon and you won't be able to restart it.

```bash
/config/scripts/ha core check       # validate config - RUN AFTER EVERY YAML CHANGE
/config/scripts/ha core restart     # apply changes (restarts HA)
/config/scripts/ha core logs        # show recent logs
/config/scripts/ha core info        # show HA version and status
/config/scripts/ha addons           # list all addons
/config/scripts/ha addons restart <slug>  # restart specific addon
```

**Workflow for config changes:**
1. Edit YAML files
2. Run `/config/scripts/ha core check` to validate
3. If valid, either let auto-reload pick up changes or run `ha core restart`

### Screenshot Tools (for Claude)
Take screenshots of HA dashboards for visual verification. Dependencies installed at boot.

```bash
# Take screenshot
python3 /config/scripts/ha_screenshot.py "/lovelace-elektricitet/oversikt" "/config/www/screenshots/screenshot.png" 15

# View screenshot (Claude can read images)
# Read /config/www/screenshots/screenshot.png
```

Credentials stored in `secrets.yaml`:
- `ha_username`: screenshot_bot
- `ha_password`: (stored in secrets)

### Validating Lovelace Dashboards
YAML dashboards are in `dashboards/`. Validate with:

```bash
# Validate apexcharts-card configurations (checks for common issues)
python3 /config/scripts/validate_apexcharts.py /config/dashboards/DASHBOARD.yaml
```

### Full-width Cards (layout-card)
To make cards span multiple columns, use layout-card (installed via HACS):
```yaml
views:
  - title: My View
    type: custom:grid-layout  # Required on the view
    cards:
      - type: custom:apexcharts-card
        view_layout:
          grid-column: span 2  # Span 2 columns
        # ... rest of card config
```

```bash
# 1. Validate YAML syntax
python3 -c "import yaml; yaml.safe_load(open('/config/dashboards/DASHBOARD.yaml')); print('Valid')"

# 2. Run HA config check
/config/scripts/ha core check

# 3. Extract and verify all entity references exist
python3 << 'EOF'
import yaml, json, urllib.request, os

with open('/config/dashboards/DASHBOARD.yaml') as f:
    dashboard = yaml.safe_load(f)

entities = set()
def find_entities(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == 'entity' and isinstance(v, str) and '.' in v:
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
    status = '✗' if state in ['unavailable', 'unknown'] else '✓'
    print(f"{status} {entity}: {state[:40]}")
EOF
```

### Querying InfluxDB
```bash
# List measurements
curl -s "http://192.168.1.62:8086/query?db=homeassistant&q=SHOW+MEASUREMENTS" | python3 -c "import sys,json; print('\n'.join([m[0] for m in json.load(sys.stdin)['results'][0]['series'][0]['values']]))"

# Query data
curl -s "http://192.168.1.62:8086/query?db=homeassistant" --data-urlencode "q=SELECT mean(value) FROM \"W\" WHERE entity_id='smart_meter_ts_65a_3_aktiv_effekt' AND time > now() - 1h GROUP BY time(5m)"

# Check entity data exists
curl -s "http://192.168.1.62:8086/query?db=homeassistant" --data-urlencode "q=SELECT count(value) FROM \"W\" WHERE entity_id='ENTITY_ID'"
```

### Grafana Dashboards
Dashboards stored in `/config/grafana/`. After editing:
1. Validate JSON: `python3 -c "import json; json.load(open('/config/grafana/FILE.json')); print('Valid')"`
2. Re-import in Grafana UI (Dashboards → Import → Upload JSON)
3. Datasource UID must match: `influxdb` (lowercase)

### Calling HA Services
```bash
curl -s -X POST "http://supervisor/core/api/services/DOMAIN/SERVICE" \
  -H "Authorization: Bearer $SUPERVISOR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"entity_id": "ENTITY_ID"}'
```

### Checking Automation Traces
```bash
curl -s "http://supervisor/core/api/states/automation.AUTOMATION_ID" \
  -H "Authorization: Bearer $SUPERVISOR_TOKEN" | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'State: {d[\"state\"]}'); print(f'Last triggered: {d[\"attributes\"].get(\"last_triggered\", \"never\")}')"
```

## Review Prompts

### Full Setup Review
Run periodically to analyze configuration and suggest improvements:

```
Review the current HA setup: automations, template sensors, dashboards, and Zigbee config.
Identify duplication, anti-patterns, and suggest best practices.
Look for opportunities to use blueprints, consolidate sensors, or improve efficiency.
```

### Quick Health Check
Fast check for errors and issues:

```
Check HA logs for errors, verify all automations are enabled, and confirm key sensors are working.
```

### Energy Dashboard Review
Review energy monitoring setup:

```
Review the energy monitoring setup: Nordpool integration, peak power tracking,
solar production, and consumption sensors. Suggest improvements for cost optimization.
```

### Zigbee Network Review
Check Zigbee mesh health:

```
Review Zigbee2MQTT configuration, device bindings, and mesh topology.
Check for devices with poor link quality or missing router coverage.
```
