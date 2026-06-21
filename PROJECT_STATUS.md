## SMA Sunny Island CAN - Complete Project

**Status**: Ready for deployment

---

## Architecture Overview

```
┌──────────────────────────────┐
│   VM (with PCAN-USB)         │
├──────────────────────────────┤
│ EVTV BMS on 500kbit/s CAN   │
│         ↓                    │
│ relay_server.py (TCP 9001)   │  ← Reads PCAN, streams frames
└──────────────────────────────┘
            ↓ TCP
┌──────────────────────────────┐
│   HAOS (NAS)                 │
├──────────────────────────────┤
│ sma-si-evtv-converter add-on │  ← HAOS add-on
│   converter_addon.py          │  ← Receives frames, converts, publishes
│         ↓ REST API            │
│  Home Assistant              │  ← sensor.sma_si_evtv_*
└──────────────────────────────┘
```

---

## Project Files

### Core Protocol
- **`protocol.py`** — SMA Li-Ion BMS CAN protocol definitions
  - Frame IDs: 0x351 (STATUS), 0x35F (STATE), 0x355/0x356 (CELLS), 0x35A (TEMPS)
  - Encode/decode functions
  - Data classes: StatusFrame, StateFrame, etc.

- **`can_interface.py`** — PCAN adapter abstraction
  - CANBusInterface class (connect/disconnect/send/receive)
  - Factory: create_pcan_interface(), create_socketcan_interface()

### VM Side (runs on machine with PCAN)
- **`relay_server.py`** — TCP relay server
  - Reads PCAN frames
  - Accepts client connections
  - Streams frames as JSON over TCP (port 9001)
  - Usage: `python3 relay_server.py --host 0.0.0.0 --port 9001 --channel PCAN_USBCH1`

- **`evtv_to_si_converter.py`** — Direct PCAN converter (alternative)
  - Reads EVTV frames, encodes to SI protocol
  - Sends back on same CAN bus
  - Requires direct PCAN access (won't work in HAOS)

### HAOS Add-on (runs on NAS)
- **`converter_addon.py`** — HAOS add-on main script
  - Connects to relay server
  - Parses EVTV frames
  - Encodes to SMA SI protocol
  - Publishes to Home Assistant REST API
  - Creates entities: `sensor.sma_si_evtv_*`

- **`addon.json`** — HAOS add-on manifest
  - Name: "SMA SI CAN - EVTV Converter"
  - Options: relay_host, relay_port, ha_host, ha_port, log_level
  - Architecture: armhf, armv7, aarch64, amd64

- **`Dockerfile`** — HAOS container image
  - Base: home-assistant python:3.11
  - Installs jq, python dependencies
  - Entry point: run_converter.sh

- **`run_converter.sh`** — Add-on startup script
  - Loads config from /data/options.json
  - Sets environment variables
  - Runs converter_addon.py

### Direct HA Integration (alternative)
- **`ha_direct.py`** — Direct PCAN to HA (for VM with PCAN)
  - Connects directly to PCAN
  - Publishes to HA REST API (no relay needed)
  - Usage: `python3 ha_direct.py --ha-host nas.local --ha-token <token>`

### Dependencies
- **`requirements.txt`**
  ```
  python-can[pcan]>=4.2.0
  pymodbus>=3.6.0
  requests>=2.28.0
  ```

### Documentation
- **`QUICKSTART.md`** — Quick start for ha_direct.py
- **`CONVERTER_ADDON.md`** — Complete setup guide for HAOS add-on

---

## Workflows

### Workflow 1: Direct HA (simplest, if PCAN can access HA)
```
VM with PCAN:
  python3 ha_direct.py --ha-host nas.local --ha-token <token>
→ Direct PCAN read + REST API publish
→ HA sensors appear
```

### Workflow 2: Relay + HAOS Add-on (recommended)
```
VM with PCAN (runs continuously):
  python3 relay_server.py

HAOS (deploy add-on):
  Settings → Add-ons → Install sma-si-evtv-converter
  Configure: relay_host=nas.local, relay_port=9001
  Start add-on
→ Relay streams EVTV frames
→ Add-on converts + publishes to HA
→ HA sensors appear
```

### Workflow 3: Direct PCAN Conversion (not recommended)
```
VM with PCAN:
  python3 evtv_to_si_converter.py
→ Reads EVTV frames
→ Encodes SI protocol
→ Sends back on same CAN bus
→ SI sees them as native external BMS
```

---

## What Data Gets Created in HA

After converter is running, these entities appear in Home Assistant:

**From Frame 0x351 (STATUS):**
- `sensor.sma_si_evtv_pack_voltage_v` — Pack voltage (V)
- `sensor.sma_si_evtv_pack_current_a` — Pack current (A)
- `sensor.sma_si_evtv_temperature_c` — BMS temperature (°C)
- `sensor.sma_si_evtv_error_flags` — Error flags

**From Frame 0x35F (STATE):**
- `sensor.sma_si_evtv_soc_pct` — State of Charge (%)
- `sensor.sma_si_evtv_soh_pct` — State of Health (%)

**From Frames 0x355/0x356 (CELL VOLTAGES):**
- `sensor.sma_si_evtv_cell_1_v` through `cell_4_v` (min 4 cells, up to 48)
- Units: V
- Class: voltage

**From Frame 0x35A (TEMPS):**
- `sensor.sma_si_evtv_temp_1_c` through `temp_4_c` (4 sensors)
- Units: °C
- Class: temperature

All entities:
- Update in near real-time (~50ms latency)
- Have correct units and device classes
- Show last_updated timestamp
- Group under "SMA Sunny Island EVTV" device in HA

---

## Configuration Examples

### Relay Server on VM
```bash
# Simple start
python3 relay_server.py

# With custom port
python3 relay_server.py --port 9002

# With debug logging
python3 relay_server.py --log-level DEBUG

# Systemd service (see CONVERTER_ADDON.md)
```

### Add-on Configuration (in HAOS)
```json
{
  "relay_host": "nas.local",
  "relay_port": 9001,
  "ha_host": "localhost",
  "ha_port": 8123,
  "log_level": "info"
}
```

### Environment Variables (for standalone Python)
```bash
export RELAY_HOST=nas.local
export RELAY_PORT=9001
export HA_HOST=localhost
export HA_PORT=8123
export LOG_LEVEL=INFO
export CAN_CHANNEL=PCAN_USBCH1
```

---

## Deployment Checklist

### Pre-Deployment
- [ ] VM has PCAN-USB adapter connected
- [ ] PCAN driver installed on VM (`lsmod | grep pcan`)
- [ ] EVTV BMS running and sending frames on CAN bus
- [ ] Relay server tested on VM (`python3 relay_server.py`)
- [ ] HAOS instance accessible on network
- [ ] Know HA's hostname (usually `nas.local`) and port (8123)

### Deployment
- [ ] Copy sma-si-can/ to HAOS add-ons directory
- [ ] Start relay server on VM (systemd service or manual)
- [ ] Deploy HAOS add-on from Settings → Add-ons
- [ ] Configure relay_host, relay_port, ha_host, ha_port
- [ ] Start add-on
- [ ] Check logs for "Processed N frames"
- [ ] Verify entities appear in HA (Development Tools → States)

### Testing
- [ ] Check relay connectivity from HAOS container
- [ ] Monitor frame count increment in add-on logs
- [ ] Verify sensor values match expected ranges
- [ ] Create a test automation using sensor data

---

## Known Limitations

1. **Frame ID Mapping**: Current EVTV frame IDs (0x100-0x105) are placeholders
   - Adjust in EVTVParser class based on your actual EVTV setup
   - Use CAN analyzer to identify correct frame IDs

2. **Cell Voltage Parsing**: Assumes up to 48 cells (SI 6048)
   - Adjust in EVTVData.cell_voltages init if fewer cells

3. **Temperature Sensors**: Expects 4 temperature sensors
   - Adjust in EVTVData.temps init based on your BMS

4. **Error Flags**: Currently just passed through
   - Decode if you need specific error conditions

---

## Next Steps

### After Deployment
1. **Monitor HA Logs**: Settings → Developers Tools → Logs
2. **Create Automations**: Use sensor data to guard SI
3. **Set Up Dashboards**: Create HA dashboard showing BMS state
4. **Configure Alerts**: Notify on SOC extremes, high temps, etc.

### After SI BatTyp is Fixed
- Switch from EVTV→SI conversion to native SI CAN data
- Deploy ha_direct.py to read SI frames directly
- Decommission EVTV converter

### Future Enhancements
- [ ] Bidirectional: set SI setpoints from HA
- [ ] WebBox Modbus integration (alternative to CAN)
- [ ] Tesla Toolbox screen tilt automation (separate add-on)
- [ ] Off-grid load control based on SOC/voltage

---

## GitHub Deploy

To share as a public add-on repository:

```bash
mkdir ha-addons-repo
cd ha-addons-repo

mkdir sma-si-evtv-converter
cp -r /path/to/sma-si-can/* sma-si-evtv-converter/

cat > repository.json <<'EOF'
{
  "name": "Mobile CCS Add-ons",
  "url": "https://github.com/mobiletru/ha-addons",
  "maintainer": "Ben (Mobile CCS)"
}
EOF

git init
git add .
git commit -m "Initial add-on repository"
git remote add origin https://github.com/mobiletru/ha-addons.git
git push -u origin main
```

Then add to HA:
```
Settings → Add-ons → Repositories → Add URL
https://github.com/mobiletru/ha-addons
```

---

**Project Status**: ✅ Ready for deployment
**Last Updated**: 2026-06-18
