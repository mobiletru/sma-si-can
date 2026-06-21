# SMA Sunny Island — project workspace

Development workspace for SMA Sunny Island Modbus, CAN bridging, HACS integration,
and cloud monitoring. **Deployable components live in separate GitHub repos.**

## Repositories

| Repo | Local folder | Install where |
|------|--------------|---------------|
| [**sma-si-can-addons**](https://github.com/mobiletru/sma-si-can-addons) | `haos-addon-modbus/` | HA **Settings → Apps → Repositories** |
| [**sma-sunny-island**](https://github.com/mobiletru/sma-sunny-island) | `hacs-sma-sunny-island/` | HACS → Custom repositories → **Integration** |
| [**sma-si-cloud-monitor**](https://github.com/mobiletru/sma-si-cloud-monitor) | `cloud-monitor/` | Cloudflare Workers (`wrangler deploy`) |
| [**sma-si-can**](https://github.com/mobiletru/sma-si-can) | *(this repo)* | Legacy CAN/EVTV scripts, docs, dev tools |

> **Do not** add `sma-sunny-island` to HA Apps — it is HACS-only.  
> **Do not** add `sma-si-can` to HA Apps — use `sma-si-can-addons` instead.

## Clone everything

```powershell
git clone https://github.com/mobiletru/sma-si-can.git
cd sma-si-can
.\clone-repos.ps1
```

Or clone each repo individually (see table above).

## Quick install (Home Assistant)

### HAOS app (Modbus + optional PCAN CAN)

1. **Settings → Apps → ⋮ → Repositories**
2. Add: `https://github.com/mobiletru/sma-si-can-addons`
3. **Check for updates** → install **SMA Sunny Island CAN** (`local_sunny_island_can`)

Full guide: [INSTALL-HAOS.md](INSTALL-HAOS.md)

### HACS integration (Modbus entities in Core)

1. HACS → **Integrations → ⋮ → Custom repositories**
2. Add `https://github.com/mobiletru/sma-sunny-island` as **Integration**
3. Install **SMA Sunny Island** → restart HA → add integration

See [`hacs-sma-sunny-island/README.md`](hacs-sma-sunny-island/README.md) after cloning.

## This repo (sma-si-can)

Shared Python modules and legacy EVTV/CAN bridge tooling:

- `protocol.py`, `can_interface.py`, `relay_server.py` — CAN protocol and relay
- `converter_addon.py`, `evtv_to_si_converter.py` — EVTV → SMA SI conversion
- `sma_modbus.py`, `grid_code.py` — Modbus register helpers (source for add-on)
- `build-zips.ps1` — local zip build from `haos-addon-modbus/` (dev fallback only)

Historical docs: `PROJECT_STATUS.md`, `CONVERTER_ADDON.md`, `QUICKSTART.md`
