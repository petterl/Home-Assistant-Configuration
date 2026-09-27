/*
 * meshcore-node-card — Lovelace-kort för MeshCore-noder (dashboard "MeshCore").
 *
 * Mörk, kortbaserad layout: statusbadge, uptime/temp, batteristapel, halvcirkel-
 * mätare för RSSI/SNR/brus med 24 h trendlinje (HA-historik), paketräknare och
 * grannlista. Två lägen:
 *   kind: repeater  — fjärrnod som pollas av integrationen
 *   kind: base      — den egna companion-noden (radio, MQTT, advert-knappar)
 *   kind: companion — bärbar companion-nod som telemetri-pollas (batteri från
 *                     spänning, senast hörd, telemetri OK/fel)
 *
 * Ingen extern beroende; resursen registreras som /local/meshcore-node-card.js.
 */

const C = {
  green: "#3ddc84",
  cyan: "#22c3ee",
  purple: "#8b5cf6",
  orange: "#f5a524",
  red: "#ef4444",
  grey: "#8a8f98",
};

const esc = (s) =>
  String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

class MeshcoreNodeCard extends HTMLElement {
  setConfig(config) {
    if (!config.name) throw new Error("name krävs");
    this._config = { kind: "repeater", hours: 24, ...config };
    this._history = {};
    this._historyFetched = 0;
    this._neighborsOpen = false;
    if (!this.shadowRoot) this.attachShadow({ mode: "open" });
  }

  set hass(hass) {
    this._hass = hass;
    const key = this._watched().map((e) => hass.states[e]?.last_updated).join("|");
    if (key !== this._lastKey) {
      this._lastKey = key;
      this._render();
    }
    if (Date.now() - this._historyFetched > 5 * 60 * 1000) this._fetchHistory();
  }

  getCardSize() {
    return { base: 7, companion: 5 }[this._config.kind] ?? 9;
  }

  _watched() {
    const c = this._config;
    const list = [c.online, c.uptime, c.temperature, c.battery, c.voltage, c.rssi, c.snr, c.noise,
      c.sent, c.received, c.tx_air, c.rx_air, c.neighbor_count, c.mqtt, c.internet, c.node_count,
      c.frequency, c.bandwidth, c.sf, c.tx_power, c.path_len, c.delivery, c.last_seen,
      c.requests_ok, c.requests_fail];
    if (c.neighbor_prefix && this._hass) {
      list.push(...Object.keys(this._hass.states).filter((e) => this._isNeighbor(e)));
    }
    return list.filter(Boolean);
  }

  _isNeighbor(e) {
    const p = this._config.neighbor_prefix;
    return p && e.startsWith(p) && !e.endsWith("_count") && !e.endsWith("_seen");
  }

  _s(e) {
    return e ? this._hass.states[e] : undefined;
  }

  _num(e) {
    const st = this._s(e);
    if (!st) return null;
    const v = parseFloat(st.state);
    return Number.isFinite(v) ? v : null;
  }

  async _fetchHistory() {
    const c = this._config;
    const ents = [c.rssi, c.snr, c.noise].filter(Boolean);
    if (!ents.length || !this._hass) return;
    this._historyFetched = Date.now();
    try {
      const start = new Date(Date.now() - c.hours * 3600 * 1000).toISOString();
      const res = await this._hass.callWS({
        type: "history/history_during_period",
        start_time: start,
        entity_ids: ents,
        minimal_response: true,
        no_attributes: true,
        significant_changes_only: false,
      });
      for (const e of ents) {
        this._history[e] = (res[e] || [])
          .map((p) => parseFloat(p.s))
          .filter((v) => Number.isFinite(v));
      }
      this._render();
    } catch (err) {
      // Historik är bara dekoration — kortet fungerar utan.
      console.warn("meshcore-node-card: history", err);
    }
  }

  // Ungefärlig LiPo-kurva (vila) — companions rapporterar bara spänning.
  static lipoPct(v) {
    const pts = [[4.2, 100], [4.1, 90], [4.0, 80], [3.9, 65], [3.8, 50], [3.7, 35], [3.6, 20], [3.5, 10], [3.4, 5], [3.3, 0]];
    if (v >= pts[0][0]) return 100;
    for (let i = 1; i < pts.length; i++) {
      const [v1, p1] = pts[i - 1], [v0, p0] = pts[i];
      if (v >= v0) return p0 + ((v - v0) / (v1 - v0)) * (p1 - p0);
    }
    return 0;
  }

  // Senast hörd = senaste advert (kontaktens last_advert) eller lyckat telemetrisvar.
  _lastHeard() {
    const c = this._config;
    const ts = [];
    const adv = parseFloat(this._s(c.last_seen)?.attributes?.last_advert);
    if (Number.isFinite(adv) && adv > 0) ts.push(adv * 1000);
    const ok = this._s(c.online)?.attributes?.last_successful_request;
    if (ok) ts.push(Date.parse(ok));
    const t = ts.filter(Number.isFinite);
    return t.length ? Math.max(...t) : null;
  }

  static ago(ms) {
    const s = Math.max(0, (Date.now() - ms) / 1000);
    if (s < 90) return "nyss";
    if (s < 3600) return `${Math.round(s / 60)} min`;
    if (s < 48 * 3600) return `${Math.round(s / 3600)} h`;
    return `${Math.round(s / 86400)} d`;
  }

  _moreInfo(entityId) {
    if (!entityId) return;
    const ev = new Event("hass-more-info", { bubbles: true, composed: true });
    ev.detail = { entityId };
    this.dispatchEvent(ev);
  }

  async _advert(flood) {
    const what = flood ? "ett FLOOD-advert (sprids över hela meshen)" : "ett zero-hop-advert (bara närmaste grannar)";
    if (!window.confirm(`Skicka ${what} från ${this._config.name}?`)) return;
    try {
      await this._hass.callService("meshcore", "execute_command", {
        command: flood ? "send_advert true" : "send_advert",
      });
      this._toast(flood ? "Flood-advert skickat" : "Advert skickat");
    } catch (err) {
      this._toast(`Misslyckades: ${err.message || err}`);
    }
  }

  _toast(message) {
    const ev = new Event("hass-notification", { bubbles: true, composed: true });
    ev.detail = { message };
    this.dispatchEvent(ev);
  }

  // ---------- byggstenar ----------

  _fmtUptime(days) {
    if (days === null) return "–";
    const d = Math.floor(days);
    const h = Math.floor((days - d) * 24);
    return d > 0 ? `${d}d ${h}h` : `${h}h ${Math.floor(((days - d) * 24 - h) * 60)}m`;
  }

  _badge(online) {
    const txt = online === true ? "Online" : online === false ? "Offline" : this._config.kind === "companion" ? "Ej nådd" : "Okänd";
    const col = online === true ? C.green : online === false ? C.red : C.grey;
    return `<span class="badge" style="--c:${col}"><i></i>${txt}</span>`;
  }

  _gauge({ label, icon, value, unit, min, max, color, quality, entity, hist }) {
    const r = 34, cx = 50, cy = 48, sweep = 240, startA = 150;
    const pt = (a) => [cx + r * Math.cos((a * Math.PI) / 180), cy + r * Math.sin((a * Math.PI) / 180)];
    const arc = (a0, a1) => {
      const [x0, y0] = pt(a0), [x1, y1] = pt(a1);
      return `M${x0.toFixed(2)} ${y0.toFixed(2)} A${r} ${r} 0 ${a1 - a0 > 180 ? 1 : 0} 1 ${x1.toFixed(2)} ${y1.toFixed(2)}`;
    };
    const frac = value === null ? 0 : Math.min(1, Math.max(0, (value - min) / (max - min)));
    const valArc = frac > 0.005 ? `<path d="${arc(startA, startA + sweep * frac)}" stroke="${color}" />` : "";
    return `
      <div class="gauge" data-entity="${esc(entity)}">
        <div class="ghead"><span>${label}</span><ha-icon icon="${icon}" style="color:${color}"></ha-icon></div>
        <svg viewBox="0 0 100 70" class="garc">
          <path d="${arc(startA, startA + sweep)}" stroke="rgba(255,255,255,.12)" />
          ${valArc}
          <text x="50" y="50" text-anchor="middle" class="gv">${value === null ? "–" : esc(value)}</text>
          <text x="50" y="60" text-anchor="middle" class="gu">${unit}</text>
        </svg>
        ${this._spark(hist, color, min, max)}
        <div class="gq" style="color:${color}">${quality}</div>
      </div>`;
  }

  _spark(values, color, min, max) {
    if (!values || values.length < 2) return `<svg class="spark" viewBox="0 0 100 16"></svg>`;
    const lo = Math.min(min, ...values), hi = Math.max(max, ...values);
    const pts = values.map((v, i) => {
      const x = (i / (values.length - 1)) * 100;
      const y = 14 - ((v - lo) / (hi - lo || 1)) * 12;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    });
    return `<svg class="spark" viewBox="0 0 100 16" preserveAspectRatio="none"><polyline points="${pts.join(" ")}" stroke="${color}" /></svg>`;
  }

  _section(title, extra = "") {
    return `<div class="sect"><span>${title}</span>${extra}<b></b></div>`;
  }

  _batteryBlock() {
    const c = this._config;
    const volt = this._num(c.voltage);
    let pct = this._num(c.battery);
    if (pct === null && volt !== null) pct = MeshcoreNodeCard.lipoPct(volt);
    const col = pct === null ? C.grey : pct >= 50 ? C.green : pct >= 20 ? C.orange : C.red;
    const warn = pct !== null && pct < 20 ? `<span class="bwarn">Ladda!</span>` : "";
    return `
      <div class="battery" data-entity="${esc(c.battery || c.voltage)}" style="--c:${col}">
        <div class="blabel"><ha-icon icon="mdi:battery-charging-high"></ha-icon>Batteri
          <div class="bpct">${pct === null ? "–" : Math.round(pct)}%${warn}</div></div>
        <div class="bbarwrap">
          <div class="bbar"><div class="bfill" style="width:${pct ?? 0}%"></div><div class="bnub"></div></div>
          <div class="bvolt">${volt === null ? "–" : volt.toFixed(3)}V</div>
        </div>
      </div>`;
  }

  _signalBlock() {
    const c = this._config;
    const rssi = this._num(c.rssi), snr = this._num(c.snr), noise = this._num(c.noise);
    const rq = rssi === null ? "–" : rssi > -70 ? "Stark" : rssi > -90 ? "Bra" : rssi > -105 ? "Svag" : "Mycket svag";
    const sq = snr === null ? "–" : snr >= 10 ? "Utmärkt" : snr >= 5 ? "Bra" : snr >= 0 ? "OK" : "Dålig";
    const nq = noise === null ? "–" : noise <= -110 ? "Låg" : noise <= -100 ? "Måttlig" : "Hög";
    // Visa bara mätare som är konfigurerade (companions har ingen brusnivå).
    const gauges = [
      c.rssi && this._gauge({ label: "RSSI", icon: "mdi:wifi", value: rssi, unit: "dBm", min: -120, max: -30, color: C.green, quality: rq, entity: c.rssi, hist: this._history[c.rssi] }),
      c.snr && this._gauge({ label: "SNR", icon: "mdi:signal-cellular-3", value: snr, unit: "dB", min: -20, max: 15, color: C.cyan, quality: sq, entity: c.snr, hist: this._history[c.snr] }),
      c.noise && this._gauge({ label: "Brus", icon: "mdi:volume-high", value: noise, unit: "dBm", min: -130, max: -80, color: C.purple, quality: nq, entity: c.noise, hist: this._history[c.noise] }),
    ].filter(Boolean);
    const measured = c.signal_note ? `<span class="snote">${esc(c.signal_note)}</span>` : "";
    return `
      ${this._section("SIGNAL", measured)}
      <div class="gauges" style="grid-template-columns:repeat(${gauges.length},1fr)">${gauges.join("")}</div>`;
  }

  _trafficBlock() {
    const c = this._config;
    const sent = this._num(c.sent), recv = this._num(c.received);
    const tx = this._num(c.tx_air), rx = this._num(c.rx_air);
    return `
      ${this._section("TRAFIK")}
      <div class="traffic">
        <div class="tbox sent" data-entity="${esc(c.sent)}"><div class="tl">SKICKAT <ha-icon icon="mdi:arrow-up-bold"></ha-icon></div><div class="tv">${sent ?? "–"}</div></div>
        <div class="tmid"><ha-icon icon="mdi:swap-vertical-bold"></ha-icon></div>
        <div class="tbox recv" data-entity="${esc(c.received)}"><div class="tl"><ha-icon icon="mdi:arrow-down-bold"></ha-icon> MOTTAGET</div><div class="tv">${recv ?? "–"}</div></div>
      </div>
      <div class="air"><span><ha-icon icon="mdi:arrow-down"></ha-icon>TX-tid: ${tx ?? "–"} min</span><span><ha-icon icon="mdi:arrow-up"></ha-icon>RX-tid: ${rx ?? "–"} min</span></div>`;
  }

  _neighborsBlock() {
    const c = this._config;
    if (!c.neighbor_prefix) return "";
    const ns = Object.keys(this._hass.states)
      .filter((e) => this._isNeighbor(e))
      .map((e) => this._hass.states[e])
      .sort((a, b) => (a.attributes.secs_ago ?? 1e12) - (b.attributes.secs_ago ?? 1e12));
    const rows = ns.map((st) => {
      const snr = parseFloat(st.state);
      const col = !Number.isFinite(snr) ? C.grey : snr >= 5 ? C.green : snr >= -5 ? C.cyan : C.orange;
      return `<div class="nrow" data-entity="${esc(st.entity_id)}">
        <span class="nname">${esc(st.attributes.resolved_name || st.attributes.pubkey_prefix)}</span>
        <span class="nseen">${esc(st.attributes.last_seen || "")}</span>
        <span class="nsnr" style="color:${col}">${Number.isFinite(snr) ? snr.toFixed(1) : "–"} dB</span></div>`;
    }).join("");
    return `
      <div class="sect toggle" id="ntoggle"><span><ha-icon class="chev" icon="${this._neighborsOpen ? "mdi:chevron-down" : "mdi:chevron-right"}"></ha-icon>GRANNAR</span><em>${ns.length}</em><b></b></div>
      ${this._neighborsOpen ? `<div class="nlist">${rows || '<div class="nrow">Inga grannar rapporterade</div>'}</div>` : ""}`;
  }

  _statRow(label, value, entity, color) {
    return `<div class="stat" data-entity="${esc(entity || "")}"><span>${esc(label)}</span><strong ${color ? `style="color:${color}"` : ""}>${esc(value)}</strong></div>`;
  }

  _baseBlock() {
    const c = this._config;
    const st = (e) => this._s(e)?.state;
    const on = (e) => st(e) === "on";
    const mqttOn = on(c.mqtt), netOn = on(c.internet);
    const delivery = st(c.delivery);
    const dcol = delivery === "Delivered" ? C.green : delivery === "Idle" ? C.grey : C.orange;
    return `
      ${this._section("RADIO")}
      <div class="stats">
        ${this._statRow("Frekvens", `${st(c.frequency) ?? "–"} MHz`, c.frequency)}
        ${this._statRow("Bandbredd", `${st(c.bandwidth) ?? "–"} kHz`, c.bandwidth)}
        ${this._statRow("Spreading factor", `SF${st(c.sf) ?? "–"}`, c.sf)}
        ${this._statRow("TX-effekt", `${st(c.tx_power) ?? "–"} dBm`, c.tx_power)}
      </div>
      ${this._section("ANSLUTNINGAR")}
      <div class="stats">
        ${this._statRow("MQTT meshat.se", mqttOn ? "Ansluten" : "Nere", c.mqtt, mqttOn ? C.green : C.red)}
        ${this._statRow("Internet", netOn ? "Uppe" : "Nere", c.internet, netOn ? C.green : C.red)}
        ${this._statRow("Kända noder", st(c.node_count) ?? "–", c.node_count, C.cyan)}
        ${this._statRow("Senaste DM", delivery ?? "–", c.delivery, dcol)}
      </div>
      <div class="actions">
        <button class="act adv"><ha-icon icon="mdi:radio-tower"></ha-icon>Advert</button>
        <button class="act flood"><ha-icon icon="mdi:access-point"></ha-icon>Advert Flood</button>
      </div>`;
  }

  _companionBlock() {
    const c = this._config;
    const ok = this._num(c.requests_ok), fail = this._num(c.requests_fail);
    const hops = this._num(c.path_len);
    const temp = this._num(c.temperature);
    const noTelemetry = (ok ?? 0) === 0;
    return `
      ${this._section("STATUS")}
      <div class="stats">
        ${this._statRow("Telemetri OK / fel", `${ok ?? "–"} / ${fail ?? "–"}`, c.requests_ok, noTelemetry ? C.orange : C.green)}
        ${this._statRow("Väg", hops === null ? "okänd (flood)" : hops === 0 ? "direkt" : `${hops} hopp`, c.path_len, C.cyan)}
        ${temp !== null ? this._statRow("Temperatur", `${temp.toFixed(1)} °C`, c.temperature) : ""}
      </div>
      ${noTelemetry ? `<div class="hint"><ha-icon icon="mdi:information-outline"></ha-icon>Inget telemetrisvar än. Tillåt telemetri för SE-Ullstamma-Base i MeshCore-appen, och noden måste vara inom räckhåll för meshen.</div>` : ""}`;
  }

  // ---------- render ----------

  _render() {
    if (!this._hass || !this._config) return;
    const c = this._config;
    const onSt = this._s(c.online)?.state;
    const online = onSt === "on" || onSt === "online" ? true : onSt === "off" || onSt === "offline" ? false : null;
    const temp = this._num(c.temperature);
    const kindLabel = { base: "BASNOD", companion: "COMPANION" }[c.kind] ?? "REPEATER";
    const kindCol = { base: C.cyan, companion: C.purple }[c.kind] ?? C.orange;
    const heard = c.kind === "companion" ? this._lastHeard() : null;
    const hops = this._num(c.path_len);

    this.shadowRoot.innerHTML = `
      <style>${MeshcoreNodeCard.styles}</style>
      <ha-card>
        <div class="head">
          <div data-entity="${esc(c.online)}">${this._badge(online)}</div>
          <span class="meta" data-entity="${esc(c.uptime || c.last_seen)}">${c.uptime ? this._fmtUptime(this._num(c.uptime)) : heard ? `<ha-icon icon="mdi:ear-hearing"></ha-icon>${MeshcoreNodeCard.ago(heard)}` : ""}</span>
          <span class="meta right" data-entity="${esc(c.temperature)}">${temp === null ? "" : `${temp.toFixed(1)}°C`}</span>
          <span class="kind" style="--c:${kindCol}">${kindLabel}</span>
        </div>
        <div class="title"><span class="tname">${esc(c.name)}</span>${c.id ? `<small class="nid">(${esc(c.id)})</small>` : ""}${hops !== null ? `<small class="hops">${hops === 0 ? "direkt" : `${hops} hopp`}</small>` : ""}${temp === null ? "" : `<small class="hops tchip">${temp.toFixed(1)}°C</small>`}</div>
        ${c.battery || c.voltage ? this._batteryBlock() : ""}
        ${c.kind === "base" ? this._baseBlock() : ""}
        ${c.kind === "companion" ? this._companionBlock() : ""}
        ${c.rssi || c.snr || c.noise ? this._signalBlock() : ""}
        ${c.sent || c.received ? this._trafficBlock() : ""}
        ${this._neighborsBlock()}
      </ha-card>`;

    this.shadowRoot.querySelectorAll("[data-entity]").forEach((el) => {
      const e = el.getAttribute("data-entity");
      if (e) el.addEventListener("click", () => this._moreInfo(e));
    });
    this.shadowRoot.getElementById("ntoggle")?.addEventListener("click", () => {
      this._neighborsOpen = !this._neighborsOpen;
      this._render();
    });
    this.shadowRoot.querySelector(".act.adv")?.addEventListener("click", () => this._advert(false));
    this.shadowRoot.querySelector(".act.flood")?.addEventListener("click", () => this._advert(true));
  }

  static get styles() {
    return `
      :host { --bg:#1b1c1f; --bg2:#222428; --line:rgba(255,255,255,.08); --txt:#e8e9ec; --dim:#9aa0a8; }
      ha-card { container-type: inline-size; background: var(--bg); color: var(--txt); border: 1px solid var(--line);
        border-radius: 28px; padding: 18px 16px 14px; box-shadow: none; }
      [data-entity] { cursor: pointer; }
      .head { display:flex; align-items:center; gap:10px; min-width:0; }
      .head > * { flex:none; }
      .meta { color: var(--dim); font-variant-numeric: tabular-nums; font-size: 14px; white-space:nowrap; }
      .meta ha-icon { --mdc-icon-size:15px; margin-right:3px; vertical-align:-2px; }
      .meta.right { margin-left:auto; }
      .meta.right + .kind { margin-left:0; }
      .badge { display:inline-flex; align-items:center; gap:8px; padding:6px 16px; border-radius:999px;
        white-space:nowrap; font-weight:600; font-size:16px; color:var(--c); background: color-mix(in srgb, var(--c) 14%, transparent);
        border:1px solid color-mix(in srgb, var(--c) 45%, transparent); }
      .badge i { width:11px; height:11px; border-radius:50%; background:var(--c); box-shadow:0 0 8px var(--c); }
      .kind { margin-left:auto; white-space:nowrap; padding:5px 14px; border-radius:999px; font-weight:700; letter-spacing:.06em; font-size:14px;
        color:var(--c); border:1.5px solid color-mix(in srgb, var(--c) 70%, transparent); }
      .title { display:flex; align-items:baseline; gap:8px; min-width:0; font-size:21px; font-weight:600; margin:14px 4px 14px; }
      .tname { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; min-width:0; }
      .title small { flex:none; white-space:nowrap; color:var(--dim); font-weight:400; font-size:13px; font-family:monospace; }
      .title .hops { font-family:inherit; border:1px solid var(--line); border-radius:8px; padding:1px 6px; }
      .title .tchip { display:none; }
      .battery { display:flex; align-items:center; gap:14px; padding:12px 16px; border-radius:18px;
        background: color-mix(in srgb, var(--c) 7%, var(--bg2)); border:1px solid color-mix(in srgb, var(--c) 35%, transparent); }
      .blabel { color:var(--dim); font-size:14px; min-width:84px; }
      .blabel ha-icon { --mdc-icon-size:18px; color:var(--c); margin-right:4px; }
      .bpct { color:var(--c); font-size:32px; font-weight:800; line-height:1.1; }
      .bbarwrap { flex:1; }
      .bbar { position:relative; height:22px; border-radius:11px; background:rgba(255,255,255,.07); }
      .bfill { height:100%; border-radius:11px; background:
        repeating-linear-gradient(90deg, color-mix(in srgb,var(--c) 70%, #000) 0 6px, var(--c) 6px 12px);
        box-shadow: 0 0 10px color-mix(in srgb, var(--c) 50%, transparent); }
      .bnub { position:absolute; right:-8px; top:6px; width:4px; height:10px; border-radius:0 3px 3px 0; background:rgba(255,255,255,.25); }
      .bwarn { display:inline-block; margin-left:8px; font-size:13px; font-weight:700; letter-spacing:.04em;
        color:#fff; background:${C.red}; border-radius:999px; padding:1px 8px; vertical-align:6px; }
      .hint { display:flex; gap:8px; align-items:flex-start; margin-top:10px; padding:10px 12px; border-radius:14px;
        font-size:13px; color:var(--dim); background:color-mix(in srgb, ${C.orange} 8%, var(--bg2));
        border:1px solid color-mix(in srgb, ${C.orange} 30%, transparent); }
      .hint ha-icon { --mdc-icon-size:18px; color:${C.orange}; flex:none; }
      .bvolt { text-align:center; font-family:monospace; color:var(--txt); margin-top:4px; font-size:14px; }
      .sect { display:flex; align-items:center; gap:10px; margin:16px 4px 10px; color:var(--dim);
        font-weight:700; letter-spacing:.18em; font-size:13px; }
      .sect b { flex:1; height:1px; background:var(--line); }
      .snote { font-weight:400; letter-spacing:0; font-size:11px; color:var(--dim); text-transform:none; }
      .sect em { font-style:normal; letter-spacing:0; border:1px solid var(--line); border-radius:999px; padding:1px 10px; }
      .sect.toggle { cursor:pointer; }
      .gauges { display:grid; grid-template-columns:repeat(3,1fr); gap:8px; }
      .gauge { background:var(--bg2); border:1px solid var(--line); border-radius:16px; padding:8px 8px 6px; }
      .ghead { display:flex; justify-content:space-between; color:var(--dim); font-size:11px; }
      .ghead ha-icon { --mdc-icon-size:18px; }
      .garc { width:100%; max-width:120px; display:block; margin:0 auto; }
      .garc path { fill:none; stroke-width:7; stroke-linecap:round; }
      .garc text { fill:var(--txt); }
      .gv { font-size:15px; font-weight:700; }
      .gu { font-size:7px; fill:var(--dim) !important; }
      .spark { width:100%; height:16px; display:block; }
      .gauge { min-width:0; }
      .spark polyline { fill:none; stroke-width:2; stroke-linejoin:round; vector-effect:non-scaling-stroke; }
      .spark { opacity:.9; }
      .gq { text-align:center; font-weight:600; font-size:13px; margin-top:2px; }
      .traffic { display:grid; grid-template-columns:minmax(0,1fr) auto minmax(0,1fr); gap:8px; align-items:center; }
      .tbox { min-width:0; overflow:hidden; background:var(--bg2); border:1px solid var(--line); border-radius:16px; padding:10px 14px; }
      .tl { color:var(--dim); font-size:13px; letter-spacing:.08em; display:flex; align-items:center; gap:6px; white-space:nowrap; }
      .tl ha-icon { --mdc-icon-size:18px; }
      .sent .tl { justify-content:flex-end; }
      .tv { font-size:30px; font-weight:800; font-variant-numeric:tabular-nums; }
      .sent .tv { color:${C.green}; } .recv .tv { color:${C.cyan}; }
      .tmid { width:48px; height:48px; border-radius:50%; display:grid; place-items:center;
        border:3px solid transparent; background: linear-gradient(var(--bg),var(--bg)) padding-box,
        conic-gradient(${C.cyan}, ${C.green}, ${C.cyan}) border-box; }
      .tmid ha-icon { color:${C.green}; }
      .air { display:flex; flex-wrap:wrap; justify-content:center; gap:4px 22px; white-space:nowrap; color:var(--txt); margin-top:10px; font-size:14px; }
      .air ha-icon { --mdc-icon-size:16px; margin-right:4px; vertical-align:-2px; }
      .chev { --mdc-icon-size:20px; vertical-align:-5px; }
      .nlist { display:flex; flex-direction:column; gap:6px; }
      .nrow { display:grid; grid-template-columns:1fr auto auto; gap:10px; background:var(--bg2);
        border:1px solid var(--line); border-radius:12px; padding:8px 12px; font-size:14px; }
      .nseen { color:var(--dim); } .nsnr { font-weight:700; font-variant-numeric:tabular-nums; }
      .stats { display:grid; grid-template-columns:1fr 1fr; gap:8px; }
      .stat { background:var(--bg2); border:1px solid var(--line); border-radius:14px; padding:8px 12px;
        display:flex; flex-direction:column; gap:2px; }
      .stat { min-width:0; }
      .stat span, .stat strong { white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
      .stat span { color:var(--dim); font-size:12px; } .stat strong { font-size:17px; }
      .actions { display:grid; grid-template-columns:1fr 1fr; gap:10px; margin-top:14px; }
      .act { white-space:nowrap; display:flex; justify-content:center; align-items:center; gap:10px; padding:12px; border-radius:999px;
        font-size:15px; color:var(--txt); cursor:pointer; font-family:inherit; }
      .act ha-icon { --mdc-icon-size:22px; }
      .adv { background:color-mix(in srgb, ${C.cyan} 10%, var(--bg)); border:1px solid color-mix(in srgb, ${C.cyan} 45%, transparent); }
      .adv ha-icon { color:${C.cyan}; }
      .flood { background:color-mix(in srgb, ${C.orange} 10%, var(--bg)); border:1px solid color-mix(in srgb, ${C.orange} 45%, transparent); }
      .flood ha-icon { color:${C.orange}; }
      @container (max-width: 470px) {
        ha-card { padding:16px 12px 12px; }
        .head { gap:8px; }
        .badge { padding:5px 11px; font-size:14px; gap:6px; }
        .badge i { width:9px; height:9px; }
        .kind { padding:4px 10px; font-size:12px; }
        .meta { font-size:13px; }
        .title { font-size:18px; }
        .bpct { font-size:28px; }
        .tbox { padding:8px 10px; }
        .tv { font-size:24px; }
        .tl { font-size:11px; letter-spacing:.04em; }
        .tmid { width:38px; height:38px; }
        .act { font-size:14px; padding:10px 8px; gap:6px; }
      }
      @container (max-width: 380px) {
        .meta.right { display:none; }
        .title .tchip { display:inline; }
        .title .nid { display:none; }
        .tl ha-icon { display:none; }
        .blabel { min-width:70px; }
      }
    `;
  }
}

customElements.define("meshcore-node-card", MeshcoreNodeCard);
window.customCards = window.customCards || [];
window.customCards.push({ type: "meshcore-node-card", name: "MeshCore node", description: "Statuskort för MeshCore-noder" });
