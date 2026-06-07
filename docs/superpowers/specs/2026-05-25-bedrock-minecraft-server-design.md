# Bedrock Minecraft Server på Proxmox - Design

**Datum:** 2026-05-25
**Status:** Approved, awaiting implementation plan

## Mål

Sätt upp en Minecraft Bedrock-server för familjebruk i en dedikerad LXC på Proxmox-hosten `ares`. Servern ska gå att ansluta till från Nintendo Switch både hemma på LAN och borta hemifrån, med en custom-värld som importeras vid senare tillfälle.

## Beslut & motivering

| Beslut | Värde | Varför |
|---|---|---|
| Hosting | Ny dedikerad LXC | Isolerad, lätt att backa upp via PBS, matchar projektets LXC-mönster |
| VMID | 106 | Nästa lediga efter 100-105/200-203 |
| Hostname | `minecraft` | Enkelt, tydligt |
| OS | Ubuntu 24.04 LTS | Matchar maffia (105), bra Docker-support |
| LXC-typ | Unprivileged, `nesting=1`, `keyctl=1` | Krav för Docker-in-LXC, säkrare än privileged |
| Resurser | 1 vCPU, 2 GB RAM, 512 MB swap, 10 GB disk | Räcker för 2-4 spelare, mindre kartor |
| IP | Static 192.168.1.64 | Ledig (60-63, 66, 70 i bruk). Stabil för port-forward |
| Auto-start | `onboot=1` | Servern kommer upp efter Proxmox-omstart |
| Bedrock-runtime | Docker + itzg/minecraft-bedrock-server | De facto standard, auto-uppgradering, enkel världsimport via bind-mount |
| Bedrock-version | `LATEST` (auto) | Microsoft släpper ofta - bekvämare än manuell pin |
| Åtkomstkontroll | Allowlist + Xbox-auth (online-mode) | Servern är internet-exponerad - måste vara strikt |
| Switch-anslutning | Publik BedrockConnect (104.238.130.180) | Inget self-host nu - sektion 7 beskriver fas 2 om vi vill äga DNS-kedjan |
| Port-forward | WAN UDP 19132 → 192.168.1.64:19132 (och 19133 för IPv6) | Standard Bedrock-port |
| Backup | PBS dagligen + RCON `save hold` före snapshot | Två lager, undviker korrupt världsfil |

## Arkitektur

```
Internet ──[router port-forward 19132/UDP]──┐
                                            ▼
ares (Proxmox 192.168.1.100)
└── LXC 106 "minecraft" (192.168.1.64, static)
    Ubuntu 24.04 LTS, unprivileged, nesting=1, keyctl=1
    1 vCPU · 2 GB RAM · 512 MB swap · 10 GB disk
    └── Docker CE
        └── itzg/minecraft-bedrock-server (compose, restart: unless-stopped)
            └── /opt/minecraft/data (bind-mount: worlds + config)

Switch:
  hemma → LAN auto-discovery (Friends-tab)
  borta → DNS 104.238.130.180 (publik BedrockConnect)
          → custom server-lista per Switch
          → din publika IP:19132
```

## Komponenter

### LXC 106 "minecraft"

Skapas via Proxmox API/CLI med:
- Template: `ubuntu-24.04-standard`
- Storage: `local-lvm` (eller den storage du använder för dina andra LXC:er)
- Features: `nesting=1,keyctl=1`
- Unprivileged: ja
- Network: `vmbr0`, static `192.168.1.64/24`, gateway `192.168.1.1`
- DNS: hemnätverkets resolver
- `onboot=1`

### Docker-stack

Filplats: `/opt/minecraft/docker-compose.yml`

```yaml
services:
  bedrock:
    image: itzg/minecraft-bedrock-server:latest
    container_name: bedrock
    restart: unless-stopped
    ports:
      - "19132:19132/udp"
      - "19133:19133/udp"
    environment:
      EULA: "TRUE"
      VERSION: LATEST
      SERVER_NAME: "Minecraft Bedrock"
      GAMEMODE: survival
      DIFFICULTY: normal
      ALLOW_CHEATS: "false"
      MAX_PLAYERS: 10
      ONLINE_MODE: "true"
      WHITE_LIST: "true"
      LEVEL_NAME: "Bedrock level"
      VIEW_DISTANCE: 10
      TICK_DISTANCE: 4
      PLAYER_IDLE_TIMEOUT: 30
      DEFAULT_PLAYER_PERMISSION_LEVEL: member
      TZ: "Europe/Stockholm"
    volumes:
      - /opt/minecraft/data:/data
```

### Datalayout

```
/opt/minecraft/
├── docker-compose.yml
├── backup-hooks/
│   ├── pre-backup.sh        # save hold + save query
│   └── post-backup.sh       # save resume
└── data/                    # bind-mount → /data i containern
    ├── server.properties    # speglas från env-vars
    ├── allowlist.json       # Xbox gamertag whitelist
    ├── permissions.json     # operator-XUID:er
    └── worlds/
        └── Bedrock level/   # eller importerad värld
```

## Dataflöde

1. **Spelaren startar Minecraft på Switch** (borta)
2. Switch frågar DNS (104.238.130.180) efter "Featured Server"-domäner
3. Publik BedrockConnect svarar med sin egen IP
4. Switch ansluter, BedrockConnect visar custom server-lista (per Switch-IP)
5. Spelaren väljer "Hemma-server" → din publika IP:19132
6. Switch ansluter via UDP till din publika IP
7. Router port-forwardar 19132/UDP → 192.168.1.64:19132
8. Docker tar emot, vidare till `bedrock`-containern
9. Bedrock-servern verifierar Xbox-auth + allowlist → spelaren ansluter

På LAN hoppas steg 1-6 över - Switchen ser servern direkt under "Friends".

## Säkerhet

- **Allowlist obligatoriskt** (`WHITE_LIST=true`) - bara namngivna Xbox-konton kan ansluta
- **Online-mode obligatoriskt** (`ONLINE_MODE=true`) - tvingar Xbox-auth, ingen offline-spoofing
- **Operator-rättigheter** läggs i `permissions.json` med XUID (inte gamertag)
- **Unprivileged LXC** - minskar attackytan om Bedrock-containern komprometteras
- **Bara port 19132/UDP exponerad** - ingen SSH/web/etc utåt
- **Inget root-lösenord från standard** - SSH-nyckel från claude@homeassistant används

## Backup-strategi

**Lager 1 - PBS daglig snapshot:**
- Hela LXC 106 inklusive Docker-volymer backas upp dagligen
- Återställning: en knapptryck via Proxmox UI

**Lager 2 - Konsistent världsdata via RCON hook:**
- `pre-backup.sh` kör `docker exec bedrock send-command "save hold"` + väntar på "Data saved"
- PBS tar snapshot
- `post-backup.sh` kör `save resume`
- Undviker korrupt världsfil mitt i en autosave

Itzg-imagen har inbyggt `PRE_BACKUP_HOOK`/`POST_BACKUP_HOOK` som vi kan koppla in senare för smidigare upplägg.

## Världsimport (fas 2, när användaren har filen)

Manuellt eller via litet wrapper-script:

```bash
ssh root@192.168.1.64
cd /opt/minecraft
docker compose stop bedrock

# Om .mcworld (ZIP):
mkdir -p data/worlds/MinKarta
unzip /tmp/din-karta.mcworld -d "data/worlds/MinKarta/"

# Om mapp:
cp -r /tmp/din-karta "data/worlds/MinKarta"

# Uppdatera LEVEL_NAME till "MinKarta" i docker-compose.yml
docker compose up -d
docker compose logs -f bedrock
```

## Uppgraderingar

- `VERSION: LATEST` → ny Bedrock-binär hämtas vid container-omstart
- Kontrollerad uppgradering: `docker compose pull && docker compose up -d`
- Recept: PBS-backup precis innan, så återställning är trivial

## Operations

| Vad | Hur |
|---|---|
| SSH | `ssh root@192.168.1.64` (alias `minecraft` läggs i `~/.ssh/config`) |
| Loggar | `docker compose logs -f bedrock` |
| Hitta XUID | `docker compose logs bedrock \| grep "Player connected"` |
| Skicka kommando | `docker exec bedrock send-command "say Hej alla"` |
| Lägg till spelare | Redigera `data/allowlist.json` → `send-command "allowlist reload"` |
| Op:a sig själv | Lägg XUID i `data/permissions.json` med `"permission": "operator"` |
| Uppgradera | `docker compose pull && docker compose up -d` |
| Stoppa snyggt | `docker compose stop` (autosparar) |

## Fas 2: Self-hosted BedrockConnect (framtida utbyggnad)

Inte i scope nu, men dokumenterat så vi vet vart vi är på väg:

För att äga hela DNS-kedjan kan vi senare addera två containers i samma compose-fil:

- `pugmatt/bedrock-connect` på UDP 19132
- `coredns/coredns` på UDP 53 med spoofing av Featured Server-domäner
- Flytta Bedrock-servern till extern UDP 19134 (intern 19132)
- Lägg till port-forwards för 53 och 19134
- Switch-DNS pekas till din publika IP istället för 104.238.130.180

Trade-offs (DNS-amplification-risk, mer komplext, allt internet på Switch går genom din CoreDNS) gör att vi väntar tills grundservern bevisats fungera.

## Out of scope

- Mods/addons (kräver mer RAM, andra image-tags)
- Java-server (separat projekt)
- Spelare-statistik / Grafana-dashboards
- DDNS (om publika IP byts byter spelarna manuellt i sin BedrockConnect-lista)
- Discord-integration

## Implementations-checklista (förhandsgranskning - detaljer i implementation plan)

1. Skapa LXC 106 via Proxmox API
2. Initiera Ubuntu (apt update, lägg till SSH-nyckel, ev. tidszon)
3. Installera Docker CE
4. Skapa `/opt/minecraft/` med `docker-compose.yml`
5. Starta stack, verifiera EULA-accept och första världsgenerering
6. Konfigurera router port-forward (WAN 19132/UDP → 192.168.1.64:19132, +19133 för IPv6)
7. Allowlist första spelaren (kräver att den försöker ansluta först för att fånga gamertag/XUID)
8. Sätt upp PBS-jobb för LXC 106
9. Lägg in pre/post-backup hooks
10. Lägg `~/.ssh/config` alias `minecraft`
11. Dokumentera Switch-DNS-setup för familjen
12. (Senare) Importera din egen karta

## Referenser

- itzg/minecraft-bedrock-server: https://hub.docker.com/r/itzg/minecraft-bedrock-server
- BedrockConnect (publik): DNS 104.238.130.180 (GamerSafer)
- Proxmox-konventioner: se memory `reference_proxmox.md`
