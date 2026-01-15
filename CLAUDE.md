# Home Assistant - Intel NUC / Proxmox

## Setup
Family home (4-6 rooms). Lights, blinds, sensors. Full energy monitoring.
- Owner: Petter (primary phone: `notify.mobile_app_petters_iphone`)
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

## Custom Components
| Component | Purpose |
|-----------|---------|
| nordpool | Electricity spot prices (SE3) |
| smartthinq_sensors | LG appliances |
| icloud3 | Device tracking |

## File Structure
| File | Purpose |
|------|---------|
| `configuration.yaml` | Main config, includes, recorder, influxdb |
| `automations.yaml` | All automations |
| `template_sensors.yaml` | Template sensors (electricity pricing) |
| `sql_sensors.yaml` | SQL sensor (peak power) |
| `zigbee2mqtt/configuration.yaml` | Z2M devices and groups |
| `secrets.yaml` | Credentials (not in git) |
| `scripts/` | Utility scripts |
| `scripts/ha` | HA CLI wrapper (use for config validation, restarts) |
| `scripts/generate_claude_snapshot.py` | Generates codebase snapshot |

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
| `sensor.peak_power_5th_highest` | 5th highest power peak (kW) |
| `sensor.peak_power_top_5_average` | Average of top 5 peaks (kW) |

## Energy Monitoring
- **Solar & Grid**: Fronius inverter with Smart Meter TS 65A-3 (all energy data from single source)
- **Per-device**: Smart plugs with power metering (FTX, CASA, Frys)
- **Appliances**: Neff oven/hob via Home Connect (status only, no energy)
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

## Git Sync
Automations auto-pull from GitHub on webhook, startup, and every 6h.
Smart reload: only restarts services whose files changed (automations, scripts, scenes, Z2M).

### Git Push (for Claude)
When asked to commit and push changes:
1. Stage and commit as normal: `git add <files> && git commit -m "message"`
2. Push using PAT from secrets.yaml:
   ```bash
   git push https://<github_pat>@github.com/<github_repo>.git master
   ```
   Read `secrets.yaml` for `github_pat` and `github_repo` values.

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
- ESPHome devices

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

## Quick Reference

### HA CLI Wrapper (for Claude)
The `ha` command is available via `/config/scripts/ha`. **Always use this to validate config after changes.**

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
