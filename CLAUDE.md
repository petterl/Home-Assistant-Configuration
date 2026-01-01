# Home Assistant - Intel NUC / Proxmox

## Setup
Family home (4-6 rooms). Lights, blinds, sensors. Full energy monitoring.

## Infrastructure
| Service | Host | Notes |
|---------|------|-------|
| MariaDB | 192.168.1.62 | Recorder, 10-day retention |
| InfluxDB | 192.168.1.62:8086 | Long-term → Grafana |
| MQTT | 192.168.1.63:1883 | |
| Zigbee | ConBee II | Z2M channel 11, frontend :8099 |
| Reverse proxy | Custom | External HTTPS access |

## Energy Monitoring
- **Solar**: Fronius inverter
- **Grid**: DSMR Slimmelezer (P1 port)
- **Per-device**: Smart plugs with power metering

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
