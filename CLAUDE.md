# Home Assistant - Intel NUC / Proxmox

> **Håll den här filen uppdaterad — alltid.** Varje gång något läggs till, ändras eller tas bort
> i setupen (integrationer, enheter, USB-passthrough, entiteter, automationer, addons, gotchas
> som upptäckts under felsökning) ska CLAUDE.md uppdateras i samma arbetspass och committas
> tillsammans med ändringen. En ändring är inte klar förrän den finns dokumenterad här.

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
| Reverse proxy | 192.168.1.70 (LXC 200) | Plain nginx. One site-file per service under `/etc/nginx/sites-enabled/`, own certbot cert per subdomain. HTTPS on per-service port (home:8123, maffia+grocy share 8443 via SNI). External access = `https://<svc>.sandholdt.se:<port>` (WAN:port→.70:port; WAN:443 = gateway UI). SSH alias `nginx-proxy` |
| Docker host | 192.168.1.66 (LXC 105 "docker") | Ubuntu 24.04, Docker/Compose. Runs maffia-game (Caddy owns :80/443) + Grocy container. SSH alias `docker` (`maffia` kept as alias). Renamed from "maffia" 2026-07-19 |
| Grocy | Container on docker host `.66:9283` | Inventory/stock mgmt (`lscr.io/linuxserver/grocy`, compose in `/opt/grocy`). HTTPS via reverse proxy → `https://grocy.sandholdt.se:8443`. Upgrade: `docker compose pull && up -d` |
| Home Connect | Cloud | Neff oven & hob (no energy data) |
| UniFi Protect | 192.168.1.1 (Zeus) | Cameras: ringklocka, uppfart, garage |
| Synology NAS | 192.168.1.9 (Atlas) | 8-bay NAS, backup storage, Plex media, Frigate NFS storage |
| Music Assistant | HA Addon | Multi-room Sonos via Plex |
| JupyterLab | 172.30.33.4:8099 | HA Addon, nginx patched for Claude access |
| Frigate | HA Addon (`ccab4aaf_frigate`) | NVR for birdhouse camera, motion recording (repo `blakeblackshear/frigate-hass-addons`) |
| MeshCore | Wio Tracker L1 via USB (`ttyACM1`) | LoRa-mesh basnod `SE-Ullstamma-Base`, rapporterar till meshat.se:s MQTT. Se [MeshCore](#meshcore-lora-mesh) |
| USB-passthrough | Proxmox `ares`, VM 102 | `usb0`=ConBee II `1cf1:0030` (`ttyACM0`), `usb1`=RFXtrx433 `0403:6001` (`ttyUSB0`, integration `rfxtrx` — se [RFXtrx](#rfxtrx-433-mhz)), `usb2`=Wio Tracker L1 `2886:1667` (`ttyACM1`). Passthrough per vendor:device-id. Proxmox-token är read-only → ändringar görs i Proxmox-UI:t |

## Källaren (Grocy-bestånd)
Dryckesbeståndet i källarens vinhylla, läst ur Grocy. Inmatning sker i dryck-appen
(`dryck.sandholdt.se:8443`), inte i HA.

| Entitet | Syfte |
|---------|-------|
| `sensor.kallaren_grocy` | Hela beståndet. State = antal flaskor, attribut `items`/`groups`/`by_country`/`by_vintage`/`n_*`/`error`. Exkluderad från recorder & InfluxDB |
| `sensor.kallaren_flaskor` | Bara antalet, recordat → trendgraf |
| `script.kallaren_drick_upp` | Konsumerar valda flaskan i Grocy |
| `script.kallaren_satt_betyg` | Skriver `rating`/`tasting_notes` på senast druckna |
| `automation.kallaren_fyll_flaskvaljaren` | Håller `input_select.kallaren_flaska` i synk |

- Data hämtas av `scripts/grocy_kallaren.py` (joinar `/api/stock`, `/api/objects/products`,
  `/api/objects/product_groups`, `/api/objects/locations`) var 5:e minut. Grocy-integrationen
  används **inte** för lagret — den exponerar inte userfields (årgång, druva, land, betyg).
- Enhetstester: `cd /config/scripts && python3 -m unittest discover -s . -p "test_grocy_*.py"`
- Testdata för att verifiera vyerna: `python3 scripts/grocy_testdata.py --add|--list|--remove`
  (produkter med prefix `ZZ Test `). **Kör alltid `--remove` efteråt.**
- Grocy-schemat (grupper, userfields, enheter, locations) ägs av dryck-appens bootstrap —
  ändra det aldrig härifrån.
- `groups`-attributet listar alla grupper som förekommer i beståndet — de fem riktiga
  Grocy-grupperna **plus** en sensor-egen bucket `Övrigt` som `grocy_kallaren.py` lägger
  till för produkter utan produktgrupp (t.ex. produkt 3). `Övrigt` finns inte i Grocy och
  har inget filterchip, men beståndsvyn itererar `groups` så inget lager blir osynligt.
- `PUT /api/userfields/products/{id}` merge:ar; `rating`/`vintage` returneras som strängar.
- Automationens entity_id blev `kallaren_fyll_flaskvaljaren` (inte `-vare`) eftersom HA
  slugifierar den svenska aliasen "Källaren - Fyll flaskväljaren" — bestämd form ger ett
  extra n. Kontrollera alltid faktiskt entity_id, lita inte på id-fältet i automations.yaml.

## Custom Components
| Component | Purpose |
|-----------|---------|
| nordpool | Electricity spot prices (SE3) |
| smartthinq_sensors | LG appliances (torktumlare, 2x refrigerators) |
| icloud3 | Device tracking |
| solcast_solar | Solar production forecasts (Solcast PV) |
| unifi | UniFi network devices |
| unifiprotect | UniFi Protect cameras |
| synology_dsm | Synology NAS monitoring |
| music_assistant | Multi-room audio management |
| xiaomi_home | Xiaomi/Roborock devices (vacuum) |
| frigate | Frigate NVR integration (HACS) — birdhouse camera + motion recording |
| meshcore | MeshCore LoRa-mesh (HACS custom repo `meshcore-dev/meshcore-ha`) — basnod över USB + MQTT till meshat.se |

## File Structure
| File | Purpose |
|------|---------|
| `configuration.yaml` | Main config, includes, recorder, influxdb |
| `automations.yaml` | All automations |
| `template_sensors.yaml` | Template sensors (electricity pricing) |
| `sql_sensors.yaml` | SQL sensor (peak power) |
| `statistics_sensors.yaml` | Statistics sensors (24h energy) |
| `zigbee2mqtt/configuration.yaml` | Z2M devices |
| `secrets.yaml` | Credentials (not in git) |
| `scripts/` | Utility scripts |
| `scripts/ha` | HA CLI wrapper (use for config validation, restarts) |
| `scripts/generate_claude_snapshot.py` | Generates codebase snapshot |
| `scripts/ha_screenshot.py` | Take dashboard screenshots |
| `scripts/robonect.py` | Robonect (Gordon-mowern) API-klient/CLI — läs/styr/inställningar |
| `esphome/` | ESPHome device configs (water meter, BT proxy) |
| `dashboards/` | YAML Lovelace dashboards |
| `www/meshcore-node-card.js` | Eget Lovelace-kort `custom:meshcore-node-card` (MeshCore-dashboarden) |
| `themes/` | Teman (`!include_dir_merge_named`): `icloud3_theme`, `meshcore/` (MeshCore Dark) |

## Lovelace Dashboards
| Dashboard | Path | Purpose |
|-----------|------|---------|
| Hem | `/lovelace-hem` | Room-based control (13 views: Översikt + rooms + dammsugare) |
| Elektricitet | `/lovelace-elektricitet` | Energy monitoring (6 views) |
| Klimat | `/lovelace-klimat` | Temperature, humidity, CO2 (2 views) |
| Batteri | `/lovelace-batteri` | Device battery status (2 views) |
| Vatten | `/lovelace-vatten` | Water consumption & leak detection (2 views) |
| System | `/lovelace-system` | Git status, automations, NAS health (1 view) |
| Källaren | `/lovelace-kallaren` | Grocy drinks inventory (4 views: Bestånd, Hantera, Statistik, Grocy) |
| MeshCore | `/lovelace-meshcore` | LoRa-mesh: basnod, repeater, skicka meddelande, kontakter, meddelandelogg, automationer, 7-dagarsgraf (1 view, tema `MeshCore Dark`) |

Dashboard cards use: Mushroom cards, ApexCharts, layout-card (grid-layout), decluttering-card templates.

## HA Areas
Areas are configured for room-based entity grouping:
`idas_rum`, `moas_rum`, `gastrum`, `vardagsrum`, `kok`, `garage`, `partyrummet`, `tvattstuga`, `sovrum`, `entre`, `groventre`, `garageuppfart`, `utomhus`, `system`, `grillen`

Query entities by area:
```bash
curl -s -X POST "http://supervisor/core/api/template" \
  -H "Authorization: Bearer $SUPERVISOR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"template": "{{ area_entities(\"kok\") | join(\"\n\") }}"}'
```

## Naming Conventions
- **Zigbee friendly names**: Swedish ("Ida tryckknapp", "Moas rullgardin")
- **Entity IDs**: snake_case with room prefix (`cover.idas_rullgardin`, `cover.moas_rullgardin`)
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
| `sensor.solcast_pv_forecast_forecast_today` | Forecasted solar production today (kWh) |
| `sensor.water_meter_t_display_total_water_consumption` | Total water consumption (m³) |
| `binary_sensor.vatten_rinner` | Water flow detected (leak detection) |

## Energy Monitoring
- **Solar & Grid**: Fronius inverter with Smart Meter TS 65A-3 (all energy data from single source)
- **Solar Forecast**: Solcast PV integration for production predictions (`sensor.solcast_pv_forecast_forecast_today`, `sensor.solcast_pv_forecast_forecast_tomorrow`)
- **Per-device**: Smart plugs with power metering (FTX, CASA, Frys, Network)
- **Appliances**:
  - Neff oven/hob via Home Connect (status only, no energy)
  - LG torktumlare via SmartThinQ (has energy data)
- **Peak power pricing**: Summer (Apr-Oct) 22 kr/kW, Winter (Nov-Mar) 43 kr/kW
- **24h energy tracking**: Statistics sensors in `statistics_sensors.yaml` (FTX, CASA, Frys, Network, Torktumlare)

### Fronius Modbus Registers
Export control via SunSpec registers:
| Register | Name | Description |
|----------|------|-------------|
| 40236 | WMaxLimPct_SF | Export power limit % (0=none, 100=full) |
| 40246 | WMaxLim_Ena | Limit enable (0=off, 1=on) |

To limit: Set 40236=0, then 40246=1. To restore: Set 40246=0.

## Solar System

**Total capacity**: 11.89 kWp DC / 10 kW AC
**Inverter**: Fronius Symo GEN24 10.0 Plus
**Panel model**: JA Solar JAM54S30 410/MR (410 Wp per panel)
**Total panels**: 29

### Roof Configuration

**Site 1: Southern roof (Södra taket)**
- Panels: 17
- DC Capacity: 6.97 kWp
- Tilt: 30°
- Azimuth: 155° (south-southeast, 25° east of due south)

**Site 2: Southwest roofs (Sydvästra taken)**
- Panels: 12 (4 + 8 from two segments)
- DC Capacity: 4.92 kWp
- Tilt: 30°
- Azimuth: -115° (west-southwest, 90° west of Site 1)

### Solcast Configuration

Two rooftop sites configured:

| Setting | Site 1 (South) | Site 2 (Southwest) |
|---------|----------------|-------------------|
| DC Capacity | 6.97 kWp | 4.92 kWp |
| AC Capacity | 5.9 kW | 4.1 kW |
| Tilt | 30° | 30° |
| Azimuth | 155° | -115° |
| Efficiency factor | 0.85 | 0.85 |

Note: Azimuth uses scale where 0° = north, ±180° = south, 90° = east, -90° = west.

### Integration
- Solcast PV Forecast integration installed via HACS
- Forecast updates automated at 06:00 and 12:00 to conserve API calls (free tier: 10/day)
- Data feeds into Home Assistant energy dashboard

## Zigbee Devices
| Room | Devices |
|------|---------|
| Idas rum | Tryckknapp, rullgardin, repeater |
| Moas rum | Tryckknapp, rullgardin, repeater |
| Gästrum | Tryckknapp, 2x gardin, repeater |
| Tvättstuga | FTX, CASA, vattensensor fjärrvärme |
| Partyrummet | Frys, vattensensor frys |
| Network | Network smartplug (power monitoring only) |

Button control: All buttons have direct Zigbee bindings to their covers (cluster 258 windowCovering) AND HA automations (blueprint `custom/blind_button_control.yaml`) as backup. Gästrum button is bound to both `Gästrum höger gardin` and `Gästrum vänster gardin`. HA automations target `cover.gastrum_gardiner_ha` (HA cover group containing both).

Water leak sensors: `binary_sensor.vattensensor_frys_water_leak`, `binary_sensor.vattensensor_fjarrvarme_water_leak`

### Blind Calibration (IKEA FYRTUR/TREDANSEN)
The blinds may lose calibration after battery replacement or power loss. When this happens, they report incorrect positions (e.g., 46% when fully closed).

**Symptoms:** Cover shows "open" at ~46% when physically closed.

**To recalibrate:**
1. Move blind to desired closed position: `cover.set_cover_position` with `position: 0` (or use HA UI)
2. **Double-press the down button** on the physical blind hardware
3. The blind will register this as the new 0% (closed) position

**Automations to update after recalibration:**
- `automations.yaml`: Update `down_position` in button blueprints (Ida, Moa, Gästrum)

**Current calibrated positions:**
| Cover | Closed | Open |
|-------|--------|------|
| Idas rullgardin | 0% | 100% |
| Moas rullgardin | 0% | 100% |
| Gästrum gardiner | 0% | 100% |

### Zigbee Troubleshooting

**Sleepy device configure failures:**
IKEA battery devices (buttons, blinds) sleep aggressively. Z2M configure/bind operations time out if the device is asleep. Error: `Bind ... genOnOff ... failed (waiting for response TIMEOUT)`.

**Fix:** Run `ha z2m reconfigure <friendly_name>` and **press the device button repeatedly** for ~30s to keep it awake until the bind completes.

**NwkRouteDiscoveryFailed (0xd0):**
The coordinator cannot find a route to the device. Usually caused by a nearby repeater/router being offline.

**Fix:**
1. Check router status: `ha z2m devices` - look for STALE/OFFLINE routers
2. Power-cycle the relevant repeater
3. Once router is back, enable permit join: `ha z2m permit-join`
4. Wake the device (press button / move blind) to force a rejoin
5. Reconfigure: `ha z2m reconfigure <friendly_name>` while pressing the button

**Device offline (last seen >24h):**
Battery devices that lose their route may not recover on their own. Check the nearest repeater first, then wake the device after the repeater is back online.

## Plejd Lights
Plejd mesh lighting system (custom integration `plejd`). Lights are named by location:
- **Köket**: `light.kok_taklampa`, `light.koksspottar_1`, `light.koksspottar_2`, `light.lampa_over_kokso`, `light.bordslampa_tak_kok`, `light.fonsterlampor`
- **Vardagsrum**: `light.lampa_over_matbord`
- **Gästrum**: `light.takspottar_3`, `light.fonsterlampor_2`
- **Garage**: `light.takbelysning`, `light.kallare`
- **Partyrummet**: `light.takspottar`, `light.taklampa`
- **Utomhus**: `light.belysning_staket`, `light.takfot`, `light.takfotbelysning_baksida`, `light.gangbelysning`, `light.belysning_grasmatta_baksida`, `light.ledlist_garageport`, `light.garge_yttervagg`

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

**NVR Storage**: `sensor.zeus_anvandning_av_lagringsutrymme` shows ~99% - this is normal! The NVR continuously records and rolls over old footage, so storage is always near capacity.

### Birdhouse Camera (Frigate)
Separate DIY camera, **not** UniFi Protect. A Raspberry Pi 3B (`192.168.4.152`, hostname `birdhouse`, IoT VLAN) runs `v4l2rtspserver` exposing `rtsp://192.168.4.152:8554/unicast` (H264 1024×768, bitrate capped to 2 Mbit/s).
- `camera.birdhouse` is owned by the **Frigate** integration (HACS) — the old `generic` RTSP camera was removed so Frigate could take the entity_id.
- Motion-only recording, 2-day retention (no 24/7). Clips: **Media → Frigate → birdhouse**. Motion: `binary_sensor.birdhouse_motion`.
- **Object detection (person) is OFF** (`detect.enabled: false` + `switch.birdhouse_detect` off) — pointless on a top-down IR nest cam. Motion detection + the custom `holk` classification run independently (verified: `detection_fps: 0`, `process_fps: 5`). NOTE: Frigate 0.17 has a runtime-override store that wins over `config.yml` on restart, so toggling the switch is what actually takes effect — set both to keep it off.
- **Motion clips (MotionEye-style):** automation `Fågelholk - Spela in klipp vid rörelse` opens a Frigate manual event on motion (`rest_command.birdhouse_clip_start` → `POST /api/events/birdhouse/motion/create`) and ends it 5 s after motion stops (`birdhouse_clip_end` → `PUT /api/events/<id>/end`). Clip = actual motion duration; pulled from recordings, stored on NAS, shows in Media → Frigate → birdhouse. Orphan-safe: an un-ended open event auto-closes at ~30 s. `rest_command` response shape: `start.content.event_id`.
- Frigate config lives in `/addon_configs/ccab4aaf_frigate/config.yml` (not reachable from the Claude addon — edit via the Frigate API on the internal container: `curl http://ccab4aaf-frigate:5000/api/config/save?save_option=saverestart -H "Content-Type: text/plain" --data-binary @file`).
- Recordings store on the **Atlas NAS** via an HA network-storage NFS mount named `frigate` → `192.168.1.9:/volume2/homeassistant/frigate` (mounted at `/media/frigate`, where the Frigate addon writes). The SQLite DB stays local in addon-configs (`/config/frigate.db`) — never on NFS. Frigate auto-prunes oldest at the disk threshold. SSH to the Pi only works from the HA host (IoT VLAN; a corp-VPN laptop can't reach it).
- To move/restore the NFS mount: use the Supervisor mounts API (`curl -X POST http://supervisor/mounts ... '{"name":"frigate","usage":"media","type":"nfs","server":"192.168.1.9","path":"..."}'`). The mount NAME must be `frigate` so it lands at `/media/frigate`. Claude addon cannot reach `/media` — local-disk cleanup needs the Advanced SSH addon (`a0d7b954_ssh`).
- **ÅTERKOMMANDE FEL — "holk-klasserna är borta" (2026-07-17, 2026-08-04):** dataset-API:t
  (`/api/classification/holk/dataset`) returnerar `{}` fast konfigen är oförändrad.
  **Grundorsaken är INTE att NFS-monteringen tappats** — `GET /mounts` visar `state: active`
  och NAS:en är nåbar hela tiden. Supervisor gör två steg: (1) NFS-montering mot Atlas, som
  lyckas, och (2) en **bind-montering** av den in i `/media/frigate`. Steg 2 vägrar med
  `MountTargetNotEmptyError: Cannot mount bind_frigate because there is existing data at
  /data/media/frigate` så fort det ligger lokal data i katalogen. Frigate (boot: auto)
  startar då ändå och skriver på HA:s lokala disk — vilket lägger dit *mer* data och gör
  felet självförstärkande vid varje omstart. Datasetet ligger kvar orört på NAS:en.
  - **Diagnos (ingen SSH behövs):** `GET /api/stats` → `service.storage["/media/frigate/clips"].mount_type`.
    `ext4` + total ≈ 125 GB (= `GET /host/info` disk_total) betyder lokal disk = trasigt.
    Friskt är `nfs4` + total ≈ 32,9 TB. Grundorsaken syns ordagrant i `GET /supervisor/logs`.
  - **Fix:** stoppa Frigate → flytta undan `/media/frigate` via SSH-addonen → `POST /mounts/frigate/reload`
    → starta Frigate → verifiera `mount_type: nfs4` och att datasetet har 3 klasser.
    Enbart addon-omstart hjälper INTE (bekräftat) — katalogen måste tömmas först.
  - **SSH-addonen:** port **22222**, user `hassio` (uid 1000, *inte* root), lösenord i addonens
    options via `GET /addons/a0d7b954_ssh/info`. Lösenordsfri `sudo` fungerar och behövs —
    `/media` är root-ägd 755. Ingen `sshpass`/`paramiko` i Claude-addonen som standard
    (`pip install paramiko`). Addonen ser `/media`, men inte värdens `/mnt/data/supervisor`.

## MeshCore (LoRa-mesh)
Basnod **SE-Ullstamma-Base** = Seeed Wio Tracker L1 Pro med MeshCore Companion USB-firmware
(v1.17.1), ansluten med USB till Proxmox-värden och passthrough:ad till HA-VM:en (`usb2`).
Integration `meshcore` v2.10.0 via HACS (custom repo `meshcore-dev/meshcore-ha`), installerad 2026-09-25.

| Inställning | Värde |
|-------------|-------|
| Serieport | `/dev/serial/by-id/usb-Seeed_Studio_Seeed_Wio_Tracker_L1_5D83C909DFE7FBE5-if00` (by-id, **aldrig** `ttyACMx` — `ttyACM0` är ConBee/Z2M), 115200 baud |
| Radio | 869.618 MHz, 62.5 kHz, SF8, CR 8, 22 dBm — **ändra inte** radioinställningarna |
| Kontaktläge | Manual contact mode (integrationen slår på det) — noden lägger inte till kontakter själv, HA håller upptäckta. Rekommenderat, låt vara |
| MQTT Broker 1 | `meshcore-mqtt.meshat.se:443`, websockets, TLS + verify, inget user/lösen, Auth Token på (audience `meshcore-mqtt.meshat.se`), Payload Mode `packet` (LetsMesh), IATA `LPI`. Topics `meshcore/{IATA}/{PUBLIC_KEY}/packets` + `/status` |
| Övervakad repeater | **SE0580-Ullstamma** (`1cb817f5567d`, ~20 m bort) — status, telemetri & grannar var 7200 s (lösenord i config entry) |
| Kontakter på noden | **SE-SM5XBV** (`4242d01aa7a1`, Petters privata companion-nod) — tillagd 2026-09-25 för DM från HA. Även *tracked client* (status/telemetri var 7200 s → basnoden sänder förfrågningar) |
| Basnodens publika nyckel | `505500c8885f10f604aad6889b6c9715e1c1cb6cf2598f0929cb3117be3b9a93` (inte hemlig; behövs när en annan nod ska lägga till basnoden utan att basnoden advertar) |

| Entitet | Syfte |
|---------|-------|
| `sensor.meshcore_505500_node_status_se_ullstamma_base` | Basnodens USB-anslutning (`online`/`offline`) |
| `binary_sensor.meshcore_505500_mqtt_broker_1_connection` | MQTT-anslutningen till meshat.se |
| `binary_sensor.meshcore_1cb817f556_online_se0580_ullstamma` | Repeatern svarar (off först efter 2,5 × pollintervallet = 5 h vid 2 h) |
| `sensor.meshcore_1cb817f556_bat_se0580_ullstamma` | Repeaterns batterispänning (V) |
| `sensor.meshcore_1cb817f556_uptime_se0580_ullstamma` | Repeaterns uptime (**dygn**) |
| `automation.meshcore_larm_repeater_se0580_ullstamma` | Notis: repeater offline/tillbaka, batteri < 3,6 V, basnod offline 10 min |
| `automation.meshcore_internet_nere_tillbaka` | DM till SE-SM5XBV när `binary_sensor.internet` går off/on (push fungerar inte utan internet) |
| `automation.meshcore_svara_pa_status_fran_se_sm5xbv` | DM `status` från SE-SM5XBV → svarar med statusrapport (~100 byte: tid, internet, nät/sol kW, läcka, olåsta lås, hemma, repeater-V) |
| `binary_sensor.internet` | Template (`template_sensors.yaml`): on om `binary_sensor.internet_ping_cloudflare` (1.1.1.1) **eller** `binary_sensor.internet_ping_google` (8.8.8.8) svarar. `delay_off` 3 min, `delay_on` 1 min |

- **Privat nyckel:** auth token-läget läser ut nodens privata nyckel (`export_private_key`) vid
  varje start/omladdning. Den hålls bara i minnet — aldrig i config entry eller loggar. Skriv
  aldrig ut den. `meshcore-decoder` saknas → integrationen signerar token i Python (varning
  "meshcore-decoder not found" är förväntad och ofarlig).
- **Sänd inget från noden** utan att fråga (meddelanden, adverts). Repeaterövervakningen skickar
  statusförfrågningar över radio (och login vid upprepade fel, max 1/h) — det är godkänt.
- **Repeaterns online-sensor** returnerar `off` direkt om basnoden tappar USB — därför kräver
  larm-automationen att basnoden är `online`.
- **Loggar:** integrationen loggar på INFO (anslutning, `[MQTT1] Connected`) — med `default: warning`
  syns inget. Tillfälligt: `ha call logger.set_level '{"custom_components.meshcore":"info"}'`
  (inte persistent). Paketpubliceringar loggas bara på DEBUG. Återställ till `warning` efteråt.
- **Skicka DM från HA:** `meshcore.send_message` med `node_id: SE-SM5XBV` (eller `pubkey_prefix`)
  och `message` (~140 tecken max). Mottagaren måste finnas i **basnodens** kontaktlista, och
  mottagaren måste ha basnoden som kontakt (DM krypteras med nycklar från båda noderna; paketet
  bär bara en avsändar-hash). Leverans syns i `sensor.meshcore_505500_last_message_delivery_se_ullstamma_base`.
- **Agera på inkommande DM:** event `meshcore_message` med `message_type: direct`, `message`,
  `sender_name`, `pubkey_prefix`, `hop_count`. **Utgående DM skickar samma event** med
  `outgoing: true` och `pubkey_prefix` = *mottagarens* → filtrera alltid bort `outgoing` (annars
  loop). Filtrera på `pubkey_prefix`, inte namn — namn kan spoofas, DM kan bara dekrypteras från
  rätt nyckel. MeshCore-text max ~160 **byte** (å/ä/ö = 2 byte). Nya kommandon läggs som
  `choose`-grenar/villkor i stil med `meshcore_status_kommando`.
- **Internet-detektering:** UniFi-integrationen exponerar **inte** WAN-status för Zeus (bara
  state/uptime/CPU/minne). Därför Ping-integrationen (2 config entries, entity_ids omdöpta från
  `binary_sensor.1_1_1_1`/`8_8_8_8`). Dual-WAN-failover ger inget larm eftersom pingen fortsätter.
- **Lägga till en kontakt** (lokalt över USB, ingen radio): låt noden skicka advert → den dyker upp i
  `select.meshcore_discovered_contact` → `select.select_option` + `meshcore.add_selected_contact`
  (kör `add_contact <pubkey>`). Kontrollera `added_to_node: true` på kontaktens binary_sensor.
- **Adverts (bara på Petters begäran):** basnoden flood-advert = `meshcore.execute_command`
  `{"command":"send_advert true"}`. Få repeatern att flood-adverta via fjärr-CLI:
  `{"command":"send_cmd 1cb817f5567d advert"}` → repeatern svarar "OK - Advert sent" (syns i
  logbooken). Fjärr-CLI kräver admin-login (integrationen är inloggad via repeater-lösenordet).
  Resultat av `execute_command` loggas bara på INFO ("Command result").
- **Varje ändring av config entry** (options-flödet: repeater, tracked client, broker …) laddar om
  hela integrationen → USB-återanslutning, MQTT-återanslutning och ny export av privata nyckeln.
  Alla MeshCore-entiteter byter tillstånd i logbooken samtidigt — det är normalt.
- **Dashboard `/lovelace-meshcore`** (`dashboards/meshcore.yaml`). Nodkorten är ett eget kort
  `custom:meshcore-node-card` (`www/meshcore-node-card.js`, vanilla JS, inga beroenden) med
  `kind: base|repeater`; config-nycklarna är entity_ids (`online`, `battery`, `voltage`, `rssi`,
  `snr`, `noise`, `sent`, `received`, `tx_air`, `rx_air`, `uptime`, `temperature`, `path_len`,
  `neighbor_prefix` …). Trendlinjerna hämtas via `history/history_during_period` (24 h). Advert-
  knapparna på baskortet sänder (bekräftelsedialog). Resursen är registrerad i Lovelace-resurserna
  (storage) som `/local/meshcore-node-card.js?v=N` — **höj `v` vid varje ändring** av JS-filen
  (`lovelace/resources/update` via websocket), annars cachar webbläsarna gammal kod.
  Vyn tvingar temat `MeshCore Dark` (`themes/meshcore/meshcore.yaml`) så standardkort matchar.
  `ha-select` ignorerar temats fyllnadsfärger → använd `mushroom-select-card` för selects.
  Förhandsgranska utan omstart: skapa en tillfällig storage-dashboard (`lovelace/dashboards/create`
  + `lovelace/config/save` med samma config), screenshot, ta bort den.
- Repeatern tillagd via Configure → Add Repeater Station. Första login i config-flödet kan
  timea ut ("Login to repeater failed or timed out") — lyckas efter omladdning.
- `custom_components/` är gitignorerad och konfigurationen ligger i `.storage` → ominstallation
  kräver HACS + config-flödet igen (USB → sökvägen ovan, sedan Manage MQTT Brokers → Add Broker).

## RFXtrx (433 MHz)
RFXCOM RFXtrx433 via USB (`usb1`), core-integrationen `rfxtrx` tillagd 2026-09-25.
- Port: `/dev/serial/by-id/usb-RFXCOM_RFXtrx433_A118TRAH-if00-port0` (by-id, inte `ttyUSB0`).
- Status vid start: 433.92 MHz, firmware 43, output power 31.
- Protokoll satta i integrationens alternativ 2026-09-26 (HA skickar dem vid varje anslutning,
  inte sparat i pinnens flash): `ac`, `arc`, `lighting4`, `oregon`, `x10`, `fineoffset`,
  `lacrosse`, `rubicson`, `hideki`, `homeeasy`, `byronsx`. Med bara de fem första (pinnens
  default) hördes noll paket på 10 min.
- `automatic_add: false`, inga enheter tillagda än. Hörda sändare (11 min lyssning 2026-09-26):
  **Viking 02035/02038** temp+fukt, `id 87:00`, var ~60 s, utomhus (15,1 °C = utegivaren).
  Oklart om den är vår eller grannens.
- **Gotcha:** en traceback `TypeError: 'NoneType' object cannot be interpreted as an integer`
  (`serialposix.py read`) betyder att mottagartråden dog när porten stängdes vid omladdning.
  Integrationen visar ändå `loaded` men tar inte emot något. Fix: ladda om config entryn.
- Paket från okända enheter syns bara på DEBUG (`logger.set_level
  '{"homeassistant.components.rfxtrx":"debug","RFXtrx":"debug"}'`, rad `Recv:`), inte som
  `rfxtrx_event` när `automatic_add` är av. Återställ till `warning` efteråt.

## Music Assistant
Addon ID: `d5369777_music_assistant`

Music library manager with multi-room audio. Uses native Sonos provider (not HA Sonos integration).

### Music Providers
| Provider | Source |
|----------|--------|
| Plex | Music library on Atlas NAS |
| Squeezebox | Logitech Squeezebox devices (squeezelite) |
| Chromecast | Google Cast devices |

### Media Players
| Entity | Room | Device | Provider |
|--------|------|--------|----------|
| `media_player.koket` | Köket | Sonos One | Sonos |
| `media_player.vardagsrum_ljud` | Vardagsrum | Sonos Playbar | Sonos |
| `media_player.garage` | Garage | Sonos One | Sonos |
| `media_player.partyrummet` | Partyrummet | Sonos system (sub + surrounds) | Sonos |
| `media_player.sonos_move` | Portabel | Sonos Move | Sonos |
| `media_player.idas_rum_clock` | Idas rum | Logitech Squeezebox | Squeezebox |
| `media_player.alla_inne` | Group | All indoor speakers | MA Group |

Other speakers (not in MA):
- `media_player.ringklocka_hogtalare` - UniFi Protect doorbell speaker

### Favorite Buttons
Each player has a `button.*_favorite_current_song` entity to save current track.

### Playing Media
```yaml
# Play via MA service
service: mass.play_media
data:
  media_id: "Artist or Album Name"
  media_type: artist  # or album, track, playlist, radio
target:
  entity_id: media_player.koket

# Or standard HA service
service: media_player.play_media
target:
  entity_id: media_player.koket
data:
  media_content_type: playlist
  media_content_id: "Playlist Name"
```

### TTS Announcements
MA supports announcements that pause music and resume after:
```yaml
service: tts.speak
target:
  entity_id: media_player.koket
data:
  message: "Någon vid dörren"
```

## LG Appliances (SmartThinQ)
| Appliance | Entities |
|-----------|----------|
| Torktumlare | `sensor.torktumlare_*` - status, energy, job state |
| Höger kyl | `climate.hoger_kyl_*`, `sensor.hoger_kyl_*` |
| Vänster kyl | `climate.vanster_kyl_*`, `sensor.vanster_kyl_*` |

Refrigerators have climate controls for fridge and freezer compartments.

## Vacuum (Xiaomi Home)
| Entity | Purpose |
|--------|---------|
| `vacuum.roborock_de_118057288_s5` | Roborock S5 "Gun Gun" - main control |
| `sensor.roborock_de_118057288_s5_battery_level_p_3_1` | Battery level |
| `sensor.roborock_de_118057288_s5_charging_state_p_3_2` | Charging state |
| `select.roborock_de_118057288_s5_mode_p_2_2` | Suction mode (Silent/Basic/Strong/Full Speed) |

States: `docked`, `cleaning`, `returning`, `paused`, `idle`, `error`

Automations:
- `dammsugare_schema_vardagar` - Cleans weekdays at 10:00 when nobody home
- `dammsugare_klar_notis` - Notifies when cleaning complete
- `dammsugare_fel_notis` - Notifies on error or stuck
- `dammsugare_lagt_batteri_notis` - Notifies on low battery

Room cleaning: Use Roborock app to set up room IDs, then call `vacuum.send_command` with room IDs.

## External Switches
| Switch | Purpose |
|--------|---------|
| `switch.uttag_brevlada` | Outdoor outlet at mailbox |
| `switch.uttag_dammbelysning` | Pond lighting outlet (Plejd) |

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
3. **Update CLAUDE.md** so it describes the change (see the rule at the top) and stage it in the same commit
4. Stage specific files: `git add <files>`
5. Commit with descriptive message: `git commit -m "Update automations and template sensors"`
6. Push using PAT from secrets.yaml:
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

## Backups
- **Proxmox Backup Server (PBS)** - Primary backup for all VMs/LXCs (HA, MariaDB, InfluxDB)
- HA built-in snapshots (3 copies, local)
- Git (this repo) for config - public repo at github.com/petterl/Home-Assistant-Configuration

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
- Check device health regularly: `ha z2m devices` (STALE >6h, OFFLINE >24h)
- Repeater outage cascades: if a repeater goes offline, all battery devices routing through it lose connectivity and may not recover until the repeater is back + devices are woken up
- Buttons/blinds have both direct Zigbee bindings AND HA automations for redundancy

### Energy Dashboard
- Fronius Smart Meter: provides all solar and grid data via Solarnet integration
- Exclude high-frequency energy sensors from recorder if causing bloat

### Automations
- Keep it simple, one trigger/action to start
- Use scripts for reusable logic
- Blueprints for common patterns (motion lights, etc.)
- **NEVER use `!secret` in automations.yaml** - prevents UI editing. Use hardcoded values or move secret-dependent automations to configuration.yaml

## Quick Reference

### Claude Code Addon Configuration
The addon requires these persistent packages (set in addon Configuration tab):

```json
"persistent_apk_packages": ["chromium", "chromium-chromedriver"],
"persistent_pip_packages": ["selenium", "websocket-client", "pyyaml"]
```

- `chromium` + `chromium-chromedriver`: Headless browser for dashboard screenshots (`ha_screenshot.py`)
- `selenium`: Python Selenium bindings for screenshot automation
- `websocket-client`: WebSocket client for Jupyter kernel code execution (`jupyter.py`)
- `pyyaml`: YAML parsing for `ha_screenshot.py` (missing this broke the screenshot script until installed persistently)

Also enable `tmux_mouse_mode: true` for scroll wheel support in the web terminal.

### HA CLI Wrapper (for Claude)
The `ha` command is available via `/config/scripts/ha`.

**IMPORTANT: Always prefer `scripts/ha` over raw `curl` commands for HA operations.** If a needed command is missing from the script, add it to `scripts/ha` rather than using one-off curl calls. This keeps operations consistent and reusable.

**WARNING:** NEVER run `ha core stop` - Claude runs in a HA addon, so stopping HA will kill the addon and you won't be able to restart it.

**Grepping logs:** `ha core logs` output contains ANSI colour codes and bytes that make `grep` treat it as binary and silently print nothing. Always use `grep -a` (and strip colours with `sed 's/\x1b\[[0-9;]*m//g'`).

```bash
/config/scripts/ha core check       # validate config - RUN AFTER EVERY YAML CHANGE
/config/scripts/ha core restart     # apply changes (restarts HA)
/config/scripts/ha core logs        # show recent logs (default 100 lines)
/config/scripts/ha core logs 2000   # show last 2000 lines
/config/scripts/ha core logs -f     # follow logs
/config/scripts/ha core logs -f 200 # follow last 200 lines
/config/scripts/ha core info        # show HA version and status
/config/scripts/ha addons           # list all addons
/config/scripts/ha addons info <slug>     # show addon info
/config/scripts/ha addons logs <slug>     # show addon logs (default 100 lines)
/config/scripts/ha addons logs <slug> 30  # show last 30 lines
/config/scripts/ha addons logs <slug> -f  # follow addon logs
/config/scripts/ha addons restart <slug>  # restart addon
/config/scripts/ha addons start <slug>    # start addon
/config/scripts/ha addons stop <slug>     # stop addon

# Entity & service commands
/config/scripts/ha state <entity_id>                  # get state, attributes, last_changed
/config/scripts/ha search <pattern>                   # find entities matching regex pattern
/config/scripts/ha template "<jinja2>"                # render any Jinja2 template
/config/scripts/ha call <domain.service> '<json>'     # call a service with JSON data

# Zigbee2MQTT commands
/config/scripts/ha z2m devices                        # list all Z2M devices with last-seen status
/config/scripts/ha z2m permit-join [sec]              # allow new devices to join (default 120s)
/config/scripts/ha z2m reconfigure <name>             # reconfigure device (press button to keep awake!)
/config/scripts/ha z2m logs [N]                       # show Z2M logs (default 100 lines)
/config/scripts/ha z2m logs -f                        # follow Z2M logs
```

**Entity examples:**
```bash
/config/scripts/ha state cover.moas_rullgardin
/config/scripts/ha search "moa.*rullgardin"
/config/scripts/ha template "{{ area_entities('kok') | join('\n') }}"
/config/scripts/ha call cover.set_cover_position '{"entity_id":"cover.moas_rullgardin","position":50}'
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

### JupyterLab (for Claude)
Claude Code can access JupyterLab's API directly (nginx patched via addon `init_commands`).

**Connection:**
- Base URL: `http://172.30.33.4:8099`
- WebSocket: `ws://172.30.33.4:8099`
- XSRF: use `-H "X-XSRFToken: dummy" -b "_xsrf=dummy"` for POST/DELETE/PUT
- Notebooks root: `/config/notebooks/` (shared filesystem)
- Addon slug: `a0d7b954_jupyterlablite`

**Helper script:** `/config/scripts/jupyter.py` - wraps all Jupyter API operations.

```bash
# Execute code on a Jupyter kernel
python3 /config/scripts/jupyter.py execute "print('hello')"

# Start a persistent kernel (returns kernel ID)
python3 /config/scripts/jupyter.py kernel-start

# Execute on existing kernel
python3 /config/scripts/jupyter.py execute --kernel-id <ID> "import pandas as pd; print(pd.__version__)"

# Stop a kernel
python3 /config/scripts/jupyter.py kernel-stop <ID>

# List running kernels
python3 /config/scripts/jupyter.py kernel-list

# List notebooks
python3 /config/scripts/jupyter.py list

# Create a notebook
python3 /config/scripts/jupyter.py create "my_analysis.ipynb" "print('hello')" "# Markdown cell"
```

**Nginx patch mechanism:** The addon's `init_commands` patches nginx to allow the addon subnet (`172.30.33.0/24`). This runs on every addon restart. If JupyterLab addon is updated and access breaks, restart the addon to re-apply the patch.

### Validating Lovelace Dashboards
**IMPORTANT: Always validate dashboards after any edit.** Run all three checks:
1. YAML syntax validation
2. `ha core check`
3. Entity reference verification (check all referenced entities exist and have valid states)

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

## Review Prompts

**A bare "review" / "gör en review" means a setup health review → use the `ha-review` skill**
(`.claude/skills/ha-review/`, data collector `collect.sh`), not `code-review` on the diff.

**IMPORTANT:** All reviews MUST include checking logs:
1. **Core logs**: `/config/scripts/ha core logs` - filter for errors/warnings
2. **Addon status**: `/config/scripts/ha addons` - check all addons are running
3. **Addon info**: `/config/scripts/ha addons info <slug>` - check for updates
4. **Addon logs**: `/config/scripts/ha addons logs <slug>` - check for addon-specific errors

### Full Setup Review
Run periodically to analyze configuration and suggest improvements:

```
Review the current HA setup: automations, template sensors, dashboards, and Zigbee config.
Check core logs and addon status for errors. Identify duplication, anti-patterns, and suggest best practices.
Look for opportunities to use blueprints, consolidate sensors, or improve efficiency.
```

### Quick Health Check
Fast check for errors and issues:

```
Check HA core logs for errors/warnings (exclude custom integration warnings).
Check all addons are running and look for available updates.
Verify all automations are enabled and confirm key sensors are working.
```

### Energy Dashboard Review
Review energy monitoring setup:

```
Review the energy monitoring setup: Nordpool integration, peak power tracking,
solar production, and consumption sensors. Check logs for energy-related errors.
Suggest improvements for cost optimization.
```

### Zigbee Network Review
Check Zigbee mesh health:

```
Review Zigbee2MQTT configuration, device bindings, and mesh topology.
Check Z2M addon status and logs for pairing/communication errors.
Check for devices with poor link quality or missing router coverage.
```

## Known Issues & Technical Notes

### SQL Sensor 255-Character Limit
HA entity states cannot exceed 255 characters. SQL sensors returning JSON must:
- Return the primary value as state (short)
- Put detailed data in attributes
- Example: `sensor.peak_power_data` returns `2.235` as state, peaks array in `peaks_json` attribute

### Orphaned Entities
The following entities exist but devices are not paired to Zigbee2MQTT:
- `binary_sensor.ida_smartplug_aktiv` - referenced in button descriptions but no Z2M device
- `binary_sensor.moa_smartplug_aktiv` - same issue
Action: Either re-pair physical devices or remove orphaned entities via HA UI

### Solar Export Control
Enabled with 0 SEK/kWh threshold (only limits when price goes negative).
- `input_boolean.export_begransning_aktiv`: ON
- `input_number.export_begransning_pris`: 0
- Uses Fronius Modbus registers 40236/40246

### Energy Tracking Gap
~70% of energy consumption is untracked ("Okänd"). Tracked devices:
- FTX, CASA, Frys, Network (Zigbee smart plugs)
- Torktumlare (SmartThinQ)
Missing: Refrigerators, oven/hob, water heater, lighting

### ESPHome Production Settings
- Use `level: INFO` for logging (not DEBUG)
- Always set OTA password via `!secret ota_password`
- Water meter (t-display) cannot run Bluetooth proxy due to hardware conflicts

### Security Notes
- **HTTP-inställningarna bor i GUI:t, inte i YAML.** HA har migrerat `http:` till
  Inställningar → System → Nätverk (`/config/.storage/http`, `yaml_migration_done: true`).
  `http`-blocket i `configuration.yaml` är medvetet borttaget (commit `0ebfda6`) — lägg
  inte tillbaka det. Aktiva värden: `ip_ban_enabled: true`, `login_attempts_threshold: 10`,
  `use_x_forwarded_for: true`, trusted proxies = 192.168.1.70/32 + 172.30.32.0/23 +
  172.30.33.0/24 + 127.0.0.1/32. Verifiera med `cat /config/.storage/http`.
- GitHub repo is public - webhook ID in automations.yaml is visible but low risk (only triggers git pull)
- Secrets.yaml properly excluded from git
