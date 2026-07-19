# Grocy bakom HTTPS som Docker-container — design

**Datum:** 2026-07-19
**Status:** Implementerad 2026-07-19 (se As-built längst ned). Kvar: LAN Local-DNS-post + släck LXC 104 + överför gamla inställningar.

## Mål

Kör Grocy som Docker-container på den delade app-hosten `192.168.1.66` (omdöpt
`maffia` → `docker`), fronted av befintlig nginx-reverse-proxy på `192.168.1.70`
med eget Let's Encrypt-cert på `grocy.sandholdt.se`. Ren installation (ingen
datamigrering). Gamla Grocy-VM:en på `192.168.1.146` avvecklas efteråt.

Drivkraft: enklare uppgradering (`docker compose pull && up -d`) än VM.

## Kartlagt nuläge

Reverse proxy `192.168.1.70` (SSH `root@` via `id_ed25519`, alias `nginx-proxy`):
- Plain **nginx 1.22.1** (Debian). Sites i `/etc/nginx/sites-enabled/`, en fil per tjänst.
- Mönster: subdomän + eget certbot-cert per tjänst.
  - `home.sandholdt.se` → SSL på port **8123** → `proxy_pass 192.168.1.60:8123`
  - `maffia.sandholdt.se` → SSL på port **8443** → `proxy_pass 192.168.1.66:80`
- HTTP på **8080**: 301→HTTPS + ACME-challenge (`/var/www/html/.well-known/acme-challenge/`).
- Certbot: `authenticator = standalone`, `key_type = ecdsa`, `renew_hook = nginx -s reload`.

Docker-host `192.168.1.66` (LXC 105 på Proxmox `ares`, SSH-alias `docker`/`maffia`):
- Ubuntu 24.04, Docker 29, Compose v5. 2 vCPU / 2 GB RAM / ~36 GB fri disk.
- Kör redan maffia-spel-stacken (nodesis + mongo + **caddy** som äger host-port 80/443).

Grocy-VM `192.168.1.146`:
- Svarar på HTTP port 80 (nginx, 302→`/stockoverview`). **SSH stängt** (port 22 closed).

Split-horizon DNS (internt):
- `home.sandholdt.se` → `192.168.1.70`
- `maffia.sandholdt.se` → `98.128.137.175` (publik IP, hairpin)
- `grocy.sandholdt.se` → `192.168.1.146` (befintlig post, ska flyttas till `.70`)

## Dataflöde (mål)

```
Klient (LAN/internet)
  → https://grocy.sandholdt.se
  → nginx reverse proxy .70  (TLS-terminering, LE-cert, certbot standalone)
  → http://192.168.1.66:9283
  → grocy-container (lscr.io/linuxserver/grocy) på docker-hosten .66
```

## Komponenter

### 1. Byt namn på hosten .66: maffia → docker
- `.66`: `hostnamectl set-hostname docker` + `/etc/hosts` — **KLART**
- Proxmox `ares`: `pct set 105 --hostname docker` — **KLART**
- `/data/home/.ssh/config`: `Host docker maffia` (IP oförändrad) — **KLART**
- Uppdatera `CLAUDE.md` + minnesfiler som nämner "maffia LXC" — kvar
- Spel-tjänsten `maffia.sandholdt.se` opåverkad (proxas via IP, inte värdnamn).

### 2. Grocy-container på docker-hosten
- Katalog `/opt/grocy/docker-compose.yml`, volym `./config:/config`.
- Image `lscr.io/linuxserver/grocy:latest`.
- Port `9283:80` (Caddy äger 80/443, därav egen port).
- Env `PUID=1000`, `PGID=1000`, `TZ=Europe/Stockholm`, `restart: unless-stopped`.
- Verifiera: `curl http://192.168.1.66:9283` → Grocy 302.

### 3. TLS-cert på .70
- `certbot certonly` för `grocy.sandholdt.se`, `--key-type ecdsa`.
- **Spegla exakt den standalone-metod home/maffia använder** — verifiera det
  fungerande kommandot mot certbot-logg/historik på `.70` innan utfärdning
  (så port-80-mekaniken inte gissas).
- `renew_hook = nginx -s reload`.

### 4. Reverse-proxy-site på .70
- `/etc/nginx/sites-available/grocy` (kopia av `maffia`-mallen) + symlänk.
- Egen SSL-port **8444**, `server_name grocy.sandholdt.se`,
  `proxy_pass http://192.168.1.66:9283`.
- HTTP-block på 8080 för ACME + 301→HTTPS.
- `nginx -t` före `nginx -s reload`.

### 5. Extern routning + DNS
- Flytta intern DNS-post `grocy.sandholdt.se`: `.146` → `.70` (som `home`).
- UniFi-gateway: lägg till port-forward/NAT mot nya SSL-porten, speglat mot
  maffias exponering. Verifiera befintlig forward-tabell via UniFi-MCP först.

### 6. Avveckling
- När HTTPS verifierats: stäng av `.146`-VM:en via Proxmox. Behåll ett tag
  innan radering.

## Öppna beroenden (löses i implementations-steg 1, inte gissningar)
- Exakt certbot-standalone-flöde på `.70` (hur port 80 frigörs vid utfärdning).
- UniFi:s befintliga extern-routning (så grocys SSL-port mappas rätt).

## Beslut / avgränsningar
- Placering: dela befintliga docker-hosten `.66` (alt. B, egen LXC, valdes bort — Grocy för lätt).
- Ren start, ingen datamigrering från `.146`.
- TLS termineras på `.70` (inte i `.66`-Caddyn) för konsekvens med home/maffia.

## As-built (2026-07-19)

Ändringar mot ursprunglig design, upptäckta under implementation:

- **Port: INTE ny 8444.** Grocy delar maffias `8443`-lyssnare via **SNI** (eget
  `server`-block, eget cert). Ingen gateway-ändring behövs — rider på befintlig
  WAN:8443→`.70:8443`-forward. Extern URL: **`https://grocy.sandholdt.se:8443`**.
- **Extern routning bekräftad:** WAN:443 → gatewayens egen UI (self-signed).
  Tjänster nås externt på sin SSL-port: home `:8123`, maffia+grocy `:8443`.
  Hairpin NAT funkar → samma URL på LAN.
- **DNS:** publik A-post `grocy.sandholdt.se` → `98.128.137.175` (WAN, ändrat på
  one.com). one.com pushar långsamt till NS trots låg TTL — verifiera via DoH.
- **UniFi fångar all utgående `:53`** och svarar från lokala poster → `nslookup`
  ger LAN-värdet, inte one.coms. Använd DoH (`https://1.1.1.1/dns-query`) för sanning.
- **LAN Local-DNS-post `grocy → .146`** finns i UniFi (Settings→Routing→DNS),
  går EJ via MCP:n → måste tas bort/ändras i UI:t (KVAR).
- `openssl` saknas på Claude-addonen → TLS-test kördes från `.70` + `WebFetch`.

**Verifierat:** container 302 (PHP 8.5.6); LE-cert t.o.m. 2026-10-17; nginx `-t` ok,
maffia opåverkad; full väg grocy via WAN:8443-hairpin → `302 /stockoverview`.

## Klart
- Steg 1 (rename maffia→docker): hostname `.66`, Proxmox LXC 105, SSH-config — KLART.
- Steg 2 (container): KLART.
- Steg 3 (cert): KLART.
- Steg 4 (nginx SNI-site): KLART.

## Kvar
- Steg 6: släck LXC 104 i Proxmox (behövs ej längre; manuell DNS-post gör det glappfritt).

## Klart (forts. 2)
- Steg 5 (LAN-DNS): KLART. Fynd: UniFi auto-registrerar klient-hostnamn under
  `sandholdt.se` → `grocy → .146` fanns automatiskt (LXC 104-klienten heter "grocy"),
  ingen manuell post att radera. Löst med manuell UniFi Local DNS-post
  `grocy.sandholdt.se → 192.168.1.70` (direkt till proxyn, som home). Verifierat `nslookup → .70`.

## Klart (forts.)
- Överför gamla Grocy-inställningar från LXC 104: KLART via `settingoverrides/*.txt`
  (sv_SE, SEK, feature-flags av m.m.) — verifierat login `lang="sv_SE"` + konstanter.
  OBS: `Setting()` är first-wins → override sist i config.php funkar ej; använd
  `/config/data/settingoverrides/<NAME>.txt`.
- CLAUDE.md + minne — KLART.
