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
- **Solar**: Fronius inverter
- **Grid**: DSMR Slimmelezer (P1 port)
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
- Fronius: use modbus or API integration, watch polling intervals
- Slimmelezer: updates every 10s, good for real-time
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
