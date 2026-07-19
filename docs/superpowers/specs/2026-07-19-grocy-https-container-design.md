# Grocy bakom HTTPS som Docker-container — design

**Datum:** 2026-07-19
**Status:** Godkänd, under implementation

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
