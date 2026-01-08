# Home Assistant - Intel NUC / Proxmox

## Setup
Family home (4-6 rooms). Lights, blinds, sensors. Full energy monitoring.

## Infrastructure
| Service | Host | Notes |
|---------|------|-------|
| MariaDB | 192.168.1.61:3306 | Recorder, 10-day retention |
| InfluxDB | 192.168.1.62:8086 | Long-term → Grafana |
| MQTT | 192.168.1.63:1883 | Mosquitto |
| Zigbee | ConBee II | Z2M channel 11, frontend :8099 |
| Reverse proxy | 192.168.1.70 | External HTTPS access |
| Home Connect | Cloud | Neff oven & hob (no energy data) |

## File Structure
| File | Purpose |
|------|---------|
| `configuration.yaml` | Main config, includes, recorder, influxdb |
| `automations.yaml` | All automations |
| `template_sensors.yaml` | Template sensors (electricity pricing) |
| `sql_sensors.yaml` | SQL sensor (peak power) |
| `zigbee2mqtt/configuration.yaml` | Z2M devices and groups |
| `secrets.yaml` | Credentials (not in git) |

## Energy Monitoring
- **Solar**: Fronius inverter
- **Grid**: DSMR Slimmelezer (P1 port)
- **Per-device**: Smart plugs with power metering (FTX, CASA, Frys)
- **Appliances**: Neff oven/hob via Home Connect (status only, no energy)

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
1. Always validate YAML before restart: `ha core check`
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
```bash
ha core check       # validate config
ha core restart     # apply changes
ha core logs -f     # follow logs
```
