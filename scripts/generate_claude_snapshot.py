#!/usr/bin/env python3
"""
Generate a Claude-friendly snapshot of Home Assistant state.
Run via shell_command.generate_claude_snapshot or manually.
Output: /config/www/claude_snapshot.md (accessible via /local/claude_snapshot.md)
"""

import json
import os
from datetime import datetime
from pathlib import Path

# Home Assistant API
HA_URL = "http://localhost:8123"

# Static context - infrastructure and configuration reference
STATIC_CONTEXT = """
---

# Static Configuration Reference

## Infrastructure
| Service | Host | Port | Notes |
|---------|------|------|-------|
| Home Assistant | 192.168.1.60 | 8123 | Proxmox VM, external: home.sandholdt.se |
| MariaDB | 192.168.1.62 | 3306 | Recorder, 10-day retention |
| InfluxDB | 192.168.1.62 | 8086 | Long-term storage, database: homeassistant |
| MQTT | 192.168.1.63 | 1883 | Mosquitto broker |
| Zigbee2MQTT | localhost | 8099 | ConBee II, channel 11 |

## Key Entity IDs

**Energy Sensors:**
- `sensor.smart_meter_ts_65a_3_aktiv_effekt` - Current power (W)
- `sensor.smart_meter_ts_65a_3_energi_aktiv_import` - Grid import (kWh)
- `sensor.smart_meter_ts_65a_3_energi_aktiv_export` - Grid export (kWh)
- `sensor.solarnet_power_photovoltaics` - Solar production power (W)
- `sensor.fornvagen_19_linkoping_total_energi` - Solar total energy (kWh)

**Electricity Pricing:**
- `sensor.nord_pool_se3_aktuellt_pris` - Nord Pool spot price SE3
- `sensor.elpris_skelleftea_kraft` - Total price with markup (template)
- `sensor.ersattning_solproduktion` - Solar compensation price (template)
- `sensor.effektavgift_manad` - Monthly demand tariff cost (template)
- `sensor.peak_power_top_5_average` - Top 5 hourly peak average (SQL)

**Zigbee Devices:**
- `cover.idas_rullgardin` - Ida's roller blind
- `cover.moa_rullgardin` - Moa's roller blind
- `switch.ida_smartplug` - Ida's smart plug
- `switch.moa_smartplug` - Moa's smart plug
- MQTT topics: `zigbee2mqtt/Ida tryckknapp/action`, `zigbee2mqtt/Moa tryckknapp/action`

**Areas:**
- Idas rum, Moas rum, Köket, Vardagsrum, Partyrummet, Entré, Garageuppfart, Tvättstuga, Utomhus

## Pricing Structure

**Skellefteå Kraft (elhandel):**
- Spot price (SE3) + 0.06 SEK/kWh markup + 0.006 SEK/kWh elcertifikat
- Monthly fee: 39.20 SEK

**Effekttariff (elnät):**
- Summer (Apr-Oct): 22 kr/kW
- Winter (Nov-Mar): 43 kr/kW
- Based on average of 5 highest hourly peaks per month

**Solar compensation:**
- Spot price + 0.02 SEK/kWh bonus

---

## Current Configuration

### Template Sensors (configuration.yaml)

```yaml
template:
  - sensor:
      - name: "Elpris Skellefteå Kraft"
        unique_id: elpris_skelleftea_kraft
        unit_of_measurement: "SEK/kWh"
        device_class: monetary
        state: >
          {% set spot = states('sensor.nord_pool_se3_aktuellt_pris') | float(0) %}
          {% set markup = 0.066 %}
          {{ (spot + markup) | round(4) }}
        attributes:
          spot_price: "{{ states('sensor.nord_pool_se3_aktuellt_pris') }}"
          markup: "0.06 SEK/kWh"
          electricity_certificate: "0.006 SEK/kWh"
          monthly_fee: "39.20 SEK/month"

      - name: "Ersättning Solproduktion"
        unique_id: ersattning_solproduktion
        unit_of_measurement: "SEK/kWh"
        device_class: monetary
        state: >
          {% set spot = states('sensor.nord_pool_se3_aktuellt_pris') | float(0) %}
          {% set bonus = 0.02 %}
          {{ (spot + bonus) | round(4) }}

      - name: "Effektavgift Månad"
        unique_id: effektavgift_manad
        unit_of_measurement: "SEK"
        device_class: monetary
        state: >
          {% set peak_kw = states('sensor.peak_power_top_5_average') | float(0) %}
          {% set month = now().month %}
          {% if month >= 4 and month <= 10 %}
            {% set rate = 22 %}
          {% else %}
            {% set rate = 43 %}
          {% endif %}
          {{ (peak_kw * rate) | round(2) }}
```

### SQL Sensor (Peak Power)

```yaml
sql:
  - name: "Peak Power Top 5 Average"
    db_url: !secret mysql_url
    query: >
      SELECT ROUND(AVG(hourly_max) / 1000, 3) as top5_avg_kw
      FROM (
        SELECT MAX(CAST(state AS DECIMAL(10,2))) as hourly_max
        FROM states
        JOIN states_meta ON states.metadata_id = states_meta.metadata_id
        WHERE states_meta.entity_id = 'sensor.smart_meter_ts_65a_3_aktiv_effekt'
          AND state NOT IN ('unknown', 'unavailable', '')
          AND last_updated >= DATE_FORMAT(NOW(), '%Y-%m-01')
        GROUP BY DATE(last_updated), HOUR(last_updated)
        ORDER BY hourly_max DESC
        LIMIT 5
      ) as top5
    column: top5_avg_kw
    unit_of_measurement: "kW"
    device_class: power
```

### Automations

```yaml
# Ida's blind control
- id: ida_knapp_rullgardin_ner
  alias: "Ida knapp - Rullgardin ner"
  trigger:
    - platform: mqtt
      topic: zigbee2mqtt/Ida tryckknapp/action
      payload: close
  action:
    - service: cover.set_cover_position
      target:
        entity_id: cover.idas_rullgardin
      data:
        position: 46
    - service: switch.turn_off
      target:
        entity_id: switch.ida_smartplug

- id: ida_knapp_rullgardin_upp
  alias: "Ida knapp - Rullgardin upp"
  trigger:
    - platform: mqtt
      topic: zigbee2mqtt/Ida tryckknapp/action
      payload: open
  action:
    - service: cover.set_cover_position
      target:
        entity_id: cover.idas_rullgardin
      data:
        position: 100
    - service: switch.turn_on
      target:
        entity_id: switch.ida_smartplug

# Moa's blind control (same pattern)
# Git auto-pull via webhook, startup, and scheduled
```

### Zigbee2MQTT Devices

```yaml
devices:
  "0x2c1165fffeb66864":
    friendly_name: Ida tryckknapp
  "0xb4e3f9fffe8929d7":
    friendly_name: Idas rullgardin
  "0x2c1165fffea5e438":
    friendly_name: Moa tryckknapp
  "0xb4e3f9fffef669f8":
    friendly_name: Moa rullgardin
  "0xb4e3f9fffe9f8222":
    friendly_name: Moa repeater
  "0xf84477fffe7c461f":
    friendly_name: Moa smartplug
  "0xd4fe28fffe2feda5":
    friendly_name: Ida smartplug
```

---

## Prompt Templates

### For debugging automation issues:

```
I have a Home Assistant automation that isn't working.

[Paste the Live State section above]

The automation:
[Paste your automation YAML]

The problem:
[Describe what's happening vs what should happen]

Error from logs (if any):
[Paste relevant log entries]
```

### For creating new automations:

```
I want to create a Home Assistant automation for:
[Describe what you want]

My setup:
- Zigbee2MQTT with MQTT broker at 192.168.1.63
- Available devices: [list from Live State above]
- Relevant sensors: [list from Live State above]

Please provide the automation YAML.
```

### For template sensor help:

```
I need help with a Home Assistant template sensor.

Current sensors I have:
[Paste from Live State section]

I want to create a sensor that:
[Describe the calculation or logic]

Please provide the template YAML for configuration.yaml.
```

### For energy/pricing questions:

```
I have questions about my energy setup in Home Assistant.

My pricing structure:
- Electricity: Skellefteå Kraft, SE3 spot + 0.066 SEK/kWh markup
- Effekttariff: 22 kr/kW summer, 43 kr/kW winter (top 5 hourly peaks)
- Solar compensation: spot + 0.02 SEK/kWh

[Paste Energy Dashboard section from Live State]

Question:
[Your question]
```

### For Grafana dashboard help:

```
I want to create a Grafana panel for:
[Describe what you want]

My InfluxDB setup:
- Host: 192.168.1.62:8086
- Database: homeassistant
- Data comes from Home Assistant InfluxDB integration

[Paste relevant sensors from Live State]

Please provide the InfluxQL query and panel JSON.
```

---

## Troubleshooting Checklist

### Automation not triggering:
1. Check Developer Tools → States for entity state
2. Check Developer Tools → Events for MQTT messages
3. Verify automation is enabled
4. Check logs: Settings → System → Logs

### Template sensor shows "unknown":
1. Check source sensor exists and has valid state
2. Test template in Developer Tools → Template
3. Verify float() has default value for unavailable states

### Zigbee device offline:
1. Check Zigbee2MQTT frontend (port 8099)
2. Verify device in network map
3. Check if battery powered device needs new battery
4. Try re-pairing close to coordinator

### Database issues:
1. MariaDB: Check connection at 192.168.1.62:3306
2. InfluxDB: Check connection at 192.168.1.62:8086
3. Verify credentials in secrets.yaml

### Git sync not working:
1. Check shell_command output in logs
2. Verify webhook URL is correct
3. Test manually: Developer Tools → Services → shell_command.git_pull
"""


def get_token():
    """Try to get a long-lived access token from secrets or env."""
    # Try environment variable first (works in add-on context)
    token = os.environ.get("SUPERVISOR_TOKEN") or os.environ.get("HASSIO_TOKEN")
    if token:
        return token

    # Try secrets.yaml
    secrets_path = Path("/config/secrets.yaml")
    if secrets_path.exists():
        try:
            import yaml
            with open(secrets_path) as f:
                secrets = yaml.safe_load(f)
                if secrets and "claude_snapshot_token" in secrets:
                    return secrets["claude_snapshot_token"]
        except Exception:
            pass

    return None


def fetch_states(token):
    """Fetch all entity states from Home Assistant API."""
    import urllib.request
    import ssl

    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    req = urllib.request.Request(
        f"{HA_URL}/api/states",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    )

    try:
        with urllib.request.urlopen(req, context=ctx, timeout=30) as response:
            return json.loads(response.read().decode())
    except Exception as e:
        return {"error": str(e)}


def fetch_config(token):
    """Fetch Home Assistant config."""
    import urllib.request
    import ssl

    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    req = urllib.request.Request(
        f"{HA_URL}/api/config",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    )

    try:
        with urllib.request.urlopen(req, context=ctx, timeout=30) as response:
            return json.loads(response.read().decode())
    except Exception as e:
        return {"error": str(e)}


def categorize_entities(states):
    """Group entities by domain and filter out noisy ones."""
    categories = {}

    # Domains to include
    priority_domains = {
        "sensor": [],
        "binary_sensor": [],
        "switch": [],
        "light": [],
        "cover": [],
        "climate": [],
        "automation": [],
        "person": [],
        "weather": [],
        "media_player": [],
        "input_button": [],
        "input_boolean": [],
        "input_number": [],
        "input_select": [],
    }

    # Entity patterns to exclude
    exclude_patterns = [
        "_uptime", "_last_boot", "_last_seen", "_update",
        "sun_", "_ip_address", "_mac_address", "_ssid",
        "_memory", "_cpu", "_disk", "_load"
    ]

    for state in states:
        entity_id = state.get("entity_id", "")
        domain = entity_id.split(".")[0] if "." in entity_id else "unknown"

        # Skip excluded patterns
        if any(pattern in entity_id.lower() for pattern in exclude_patterns):
            continue

        # Only include priority domains
        if domain not in priority_domains:
            continue

        if domain not in categories:
            categories[domain] = []

        categories[domain].append({
            "entity_id": entity_id,
            "state": state.get("state"),
            "friendly_name": state.get("attributes", {}).get("friendly_name", ""),
            "unit": state.get("attributes", {}).get("unit_of_measurement", ""),
            "device_class": state.get("attributes", {}).get("device_class", ""),
        })

    return categories


def generate_markdown(config, categories, timestamp):
    """Generate Claude-friendly markdown snapshot."""

    md = f"""# Home Assistant Snapshot for Claude
Generated: {timestamp}

Copy this entire file and paste it into Claude Desktop when asking for help with your Home Assistant setup.

---

# Live State

## System Info
- **Version**: {config.get('version', 'unknown')}
- **Location**: {config.get('location_name', 'unknown')}
- **Timezone**: {config.get('time_zone', 'unknown')}

## Current Entity States

"""

    # Domain display names
    domain_names = {
        "sensor": "Sensors",
        "binary_sensor": "Binary Sensors",
        "switch": "Switches",
        "light": "Lights",
        "cover": "Covers",
        "climate": "Climate",
        "automation": "Automations",
        "person": "Persons",
        "weather": "Weather",
        "media_player": "Media Players",
        "input_button": "Input Buttons",
        "input_boolean": "Input Booleans",
        "input_number": "Input Numbers",
        "input_select": "Input Selects",
    }

    for domain, entities in sorted(categories.items()):
        if not entities:
            continue

        md += f"### {domain_names.get(domain, domain.title())}\n\n"
        md += "| Entity | State | Name |\n"
        md += "|--------|-------|------|\n"

        for e in sorted(entities, key=lambda x: x["entity_id"]):
            state = e["state"]
            if e["unit"]:
                state = f"{state} {e['unit']}"
            name = e["friendly_name"] or e["entity_id"].split(".")[1]
            # Escape pipe characters in state
            state = str(state).replace("|", "\\|")
            name = str(name).replace("|", "\\|")
            md += f"| `{e['entity_id']}` | {state} | {name} |\n"

        md += "\n"

    # Add energy-specific section
    md += """---

## Energy Dashboard Entities

Key sensors for energy monitoring:

| Purpose | Entity ID | Current Value |
|---------|-----------|---------------|
"""

    energy_sensors = [
        ("Grid Power", "sensor.smart_meter_ts_65a_3_aktiv_effekt"),
        ("Grid Import", "sensor.smart_meter_ts_65a_3_energi_aktiv_import"),
        ("Grid Export", "sensor.smart_meter_ts_65a_3_energi_aktiv_export"),
        ("Solar Power", "sensor.solarnet_power_photovoltaics"),
        ("Solar Total", "sensor.fornvagen_19_linkoping_total_energi"),
        ("Spot Price", "sensor.nord_pool_se3_aktuellt_pris"),
        ("Total Price", "sensor.elpris_skelleftea_kraft"),
        ("Solar Compensation", "sensor.ersattning_solproduktion"),
        ("Peak Power Avg", "sensor.peak_power_top_5_average"),
        ("Effektavgift", "sensor.effektavgift_manad"),
    ]

    # Find these sensors in categories
    all_sensors = categories.get("sensor", [])
    sensor_dict = {s["entity_id"]: s for s in all_sensors}

    for purpose, entity_id in energy_sensors:
        if entity_id in sensor_dict:
            s = sensor_dict[entity_id]
            state = s["state"]
            if s["unit"]:
                state = f"{state} {s['unit']}"
            md += f"| {purpose} | `{entity_id}` | {state} |\n"
        else:
            md += f"| {purpose} | `{entity_id}` | (not found) |\n"

    # Add static context
    md += STATIC_CONTEXT

    return md


def main():
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    token = get_token()
    if not token:
        # Write error file with setup instructions
        output = f"""# Home Assistant Snapshot - Setup Required
Generated: {timestamp}

## Setup Required: Add API Token

To use this feature, add a long-lived access token to secrets.yaml:

```yaml
claude_snapshot_token: "your-long-lived-access-token-here"
```

**To create a token:**
1. Go to your Profile in Home Assistant (click your name in sidebar)
2. Scroll to "Long-Lived Access Tokens"
3. Click "Create Token"
4. Name it "Claude Snapshot"
5. Copy the token to secrets.yaml

After adding the token, run the script again.

{STATIC_CONTEXT}
"""
        output_path = Path("/config/www/claude_snapshot.md")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(output)
        print(f"Setup required. Wrote instructions to {output_path}")
        return

    # Fetch data
    states = fetch_states(token)
    config = fetch_config(token)

    if isinstance(states, dict) and "error" in states:
        output = f"""# Home Assistant Snapshot - Error
Generated: {timestamp}

## Error fetching states

{states['error']}

Check that:
1. Home Assistant is running
2. The token in secrets.yaml is valid
3. The API is accessible at {HA_URL}

{STATIC_CONTEXT}
"""
    else:
        categories = categorize_entities(states)
        output = generate_markdown(config, categories, timestamp)

    # Write to www folder (accessible via /local/)
    output_path = Path("/config/www/claude_snapshot.md")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(output)

    print(f"Snapshot written to {output_path}")
    print(f"Access via: https://home.sandholdt.se:8123/local/claude_snapshot.md")


if __name__ == "__main__":
    main()
