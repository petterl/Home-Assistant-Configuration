#!/bin/bash
cd "/config" 2>/dev/null || cd "."
echo "# HA CONFIG EXPORT - $(date '+%Y-%m-%d %H:%M')"
echo "# HA Version: $(cat .HA_VERSION 2>/dev/null)"
echo ""
output_file() { [ -f "$1" ] && echo "# === FILE: $1 ===" && echo '```yaml' && cat "$1" && echo '```' && echo ""; }
for f in configuration.yaml automations.yaml scripts.yaml scenes.yaml sensor.yaml binary_sensor.yaml switch.yaml groups.yaml customize.yaml zones.yaml logger.yaml input_select.yaml input_boolean.yaml template.yaml; do output_file "$f"; done
for dir in sensor binary_sensor switch automation script group camera media_player device_tracker shell_command packages bin; do [ -d "$dir" ] && for f in "$dir"/*.yaml; do [ -f "$f" ] && output_file "$f"; done; done
echo "# === END ==="
