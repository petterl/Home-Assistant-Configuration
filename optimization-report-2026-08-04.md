# HA Optimization — Phase 1 Findings Report
**Date:** 2026-08-04 · **Backup:** full snapshot `88573ac5` (`pre-optimization-2026-07-25`, 527 MB) · **Git rollback tag:** `pre-optimization-2026-07-25` @ `8071950`

## Baseline
| Metric | Value |
|--------|-------|
| Entities (states) | 1,689 |
| Entities (registry) | 2,525 (848 disabled) |
| Unavailable/unknown | 272 |
| Automations | 50 (+1 orphaned) |
| **MariaDB total** | **2,337 MB** |
| — states table | 1,224 MB / 4.19 M rows |
| — statistics table | 767 MB / 5.41 M rows |
| — state_attributes | 190 MB |
| — statistics_short_term | 152 MB |

---

## Finding 1 — Orphaned long-term statistics ★ biggest DB win
**537 statistic streams (3.88 M rows, ~72% of the statistics table, ≈550 MB) belong to entities that no longer exist.** Long-term statistics are *never* purged by `purge_keep_days`, so this has accumulated for years.

Sources: removed **Netatmo** weather station (`netatmo_fornvagen_*`), removed **CO2 Signal** (`co2_intensity`, `grid_fossil_fuel_percentage`), **renamed Synology/Atlas** sensors (`atlas_cpu_utilization_*`, `atlas_memory_*` — old names), and other removed sensors.

**Action (needs approval — deletes historical stats for gone entities):** purge orphaned statistics via `recorder.purge_entities` / Statistics panel. Reclaims ~550 MB and speeds up every history/statistics query. Safe: entities already gone; full backup exists.

## Finding 2 — High-frequency Fronius sub-sensors dominate the states table
Top state writers (~90k rows each / 10 days) are Fronius per-phase and DC sub-sensors **not shown on the energy dashboard**:
- `sensor.fronius_smart_meter_..._power_l1/l2/l3`, `..._ac_current`, `..._ac_current_l1/l2/l3`
- `sensor.fronius_symo_gen24_mppt_module_0/1_dc_voltage`, `..._reactive_power`
- `sensor.okand_effekt` (138k rows — top single writer; template "unknown power")
- `sensor.solarnet_belastning`, `sensor.solarnet_forbrukad_effekt`

The recorder already excludes Fronius AC voltage & line frequency; the per-phase current/power and MPPT DC voltages are the next tier.

**Action (safe, reversible config):** extend recorder `exclude` globs for these sub-sensors. Aggregate power/consumption sensors used by the energy dashboard stay recorded. Shrinks daily states growth substantially.

## Finding 3 — Flapping battery sensors (bug)
`binary_sensor.vardagsrum_outdoor_battery_plus_low` and `binary_sensor.vardagsrum_gastrum_smart_indoor_module_battery_plus_low` each wrote **~62k rows in 10 days** — a binary "battery low" should change a handful of times, not 62k. Indicates a flapping/bouncing source (Netatmo battery reporting).

**Action:** add to recorder exclude now (safe); optionally investigate the source device later.

## Finding 4 — Dead entities (17) — needs per-item approval
- **10 × Plejd orphan diagnostics:** `sensor.last_seen_20…24`, `sensor.rssi_20…24` (already excluded from recorder — registry clutter only)
- **4 × Plejd scenes (unavailable):** `scene.tand_inne`, `scene.slack_inne`, `scene.slack_partydel`, `scene.eld`
- **3 × misc:** `sensor.petter_s_ipad_last_update_trigger` (mobile_app), `update.ica_shopping_list_update` (HACS), `automation.markis_begransa_min_till_5_tradskydd` (orphaned automation entity)

## Finding 5 — Stale non-loaded integration config stubs (6)
Config entries with **0 entities left**, just dead stubs: `zha` (ConBee II — leftover from before Z2M), `ipp` (Canon printer), `ibeacon`, `cast` (Google Cast), `unifi_access`. Plus `bluetooth` in `setup_retry` (**leave** — adapter may recover).

**Action (needs approval):** remove the 5 clearly-stale stubs.

## Finding 6 — Config / log issues
- **LG SmartThinQ failing** — `UseOfficialAPIError` / "ThinQ platform not ready". LG deprecated the old API; upstream issue, not fixable by cleanup. Torktumlare/fridges may be intermittently unavailable. *(informational)*
- **Xiaomi map extractor** ('Fornvägen') — auth failing, needs your re-login. *(user action)*
- **`device_tracker.see` deprecated** (icloud3) — removed in HA 2027.5. *(future)*
- **`TypeError: 'bool' object is not subscriptable` ×2** — worth locating the source; low priority.
- Robonect timeouts / UniFi 503s — transient, expected.

## Non-issues (verified healthy — no action)
- **848 disabled entities**: 774 are `disabled_by: integration` (UniFi 257, Proxmox 125, systemmonitor 82, hassio 78, Sonos 68…) — normal auto-disabled diagnostics, correctly off. Only 15 user-disabled.
- **Most unavailable entities are temporarily offline** (battery/network devices with recent data) — not deletion candidates.
- **Dashboards**: no dead entity references.
- **Recorder** already has a solid exclude list and 10-day purge.

---

## Proposed execution
**Phase 2 — safe & reversible (apply as one batch after you approve):**
1. Extend recorder excludes (Findings 2 + 3): Fronius per-phase/MPPT sub-sensors + 2 flapping battery sensors.
2. Validate (`ha core check`) → restart → confirm no new errors.

**Phase 3 — deletions (each needs your yes):**
- A. Purge 537 orphaned statistics (Finding 1) — ~550 MB.
- B. Remove 17 dead entities (Finding 4).
- C. Remove 5 stale integration stubs (Finding 5).

**Phase 4 — verify & before/after summary.**

---

## RESULTS (executed 2026-08-04)
| Item | Before | After |
|------|--------|-------|
| statistics rows | 5,406,056 | **1,521,364** (−72%) |
| statistics streams (meta) | 891 | **354** |
| Dead entities | — | 13 removed (4 Plejd scenes kept per user) |
| Stale integration stubs | 6 non-loaded | 5 removed (bluetooth kept) |
| Recorder excludes | — | Fronius per-phase/MPPT + battery-flap globs added ✓ working |
| Config valid | — | ✓ |
| Recorder health post-work | — | ✓ writing (1 s fresh), key sensors alive |

**Speed win delivered:** every history/statistics/logbook query now scans 72% fewer statistics rows, and the high-frequency Fronius/battery sub-sensors no longer bloat `states`.

**Note on disk:** total DB size stayed ~2.3 GB — InnoDB `DELETE` frees pages for reuse but doesn't return them to the OS. Run `OPTIMIZE TABLE statistics` (brief table lock) to reclaim ~550 MB of disk if desired; not required for the speed benefit.

**Not done (needs you):** Xiaomi map-extractor re-auth; LG SmartThinQ is an upstream API deprecation. `TypeError: 'bool' object is not subscriptable` ×2 source not yet located.
