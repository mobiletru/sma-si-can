## SMA SI 6048 - EVTV BMS Bridge (Direct PCAN on NAS)

**Architecture**: PCAN plugged into NAS → HAOS add-on → read EVTV + write SI → Home Assistant

---

## Setup (Simplified)

### 1. Install Add-on in HAOS

Copy to HAOS:
```bash
scp -r sma-si-can/ root@nas.local:/addons/local/sma-si-6048-bridge
```

Or via HAOS web UI:
- Settings → Add-ons → Create Add-on
- Select folder → sma-si-can
- Install

### 2. Configure Add-on

In HAOS add-on settings:
```yaml
can_channel: PCAN_USBCH1     # Your PCAN channel
ha_host: localhost            # HA host (localhost in HAOS)
ha_port: 8123                 # HA port
log_level: info               # debug/info/warning/error
```

### 3. Start Add-on

Click **Start** → check logs for "Processed N frames"

---

## What Gets Created

### HA Sensors (Bidirectional)

**Read from EVTV:**
- `sensor.sma_si_evtv_pack_voltage_v` — EVTV pack voltage
- `sensor.sma_si_evtv_pack_current_a` — EVTV pack current
- `sensor.sma_si_evtv_soc_pct` — EVTV SOC
- `sensor.sma_si_evtv_soh_pct` — EVTV SOH
- `sensor.sma_si_evtv_temperature_c` — EVTV BMS temp
- `sensor.sma_si_evtv_cell_1_v` ... `cell_4_v` — Cell voltages
- `sensor.sma_si_evtv_temp_1_c` ... `temp_4_c` — Temp sensors

**Write to SI 6048:**
Bridge automatically sends SI CAN protocol frames (0x351, 0x35F, 0x355, 0x35A) every 50ms with converted EVTV data.

SI 6048 receives these as if from a native external BMS.

---

## Data Flow

```
EVTV BMS (on PCAN)
        ↓ (CAN frames 0x100-0x105)
    PCAN-USB
        ↓
    NAS (HAOS)
        ↓
    bridge_direct.py
        ├→ Parse EVTV frames
        ├→ Publish to HA (sensor.sma_si_evtv_*)
        └→ Encode & send SI frames (0x351, 0x35F, 0x355, 0x35A)
             ↓
         Back to CAN bus
             ↓
        SI 6048 (receives as external BMS)
```

---

## Frame Mapping (Edit if Needed)

If your EVTV uses different frame IDs, edit `bridge_direct.py`:

```python
class EVTVReader:
    EVTV_VOLTAGE = 0x100    # ← Change these
    EVTV_CURRENT = 0x101
    EVTV_STATE = 0x102
    EVTV_CELLS_1 = 0x103
    EVTV_CELLS_2 = 0x104
    EVTV_TEMPS = 0x105
```

Find actual IDs:
```bash
# From HAOS terminal or VM with CAN analyzer
candump can0  # Linux
# or use Windows Peak software
```

---

## Troubleshooting

### PCAN Not Detected

```bash
# From HAOS terminal
ha addon exec sma-si-6048-bridge \
  python3 -c "import can; print(can.detect_available_configs(interfaces=['pcan']))"

# Check kernel module
ha addon exec sma-si-6048-bridge \
  lsmod | grep pcan
```

### No Data in HA

Check add-on logs:
1. Settings → Add-ons → SMA SI 6048 Bridge → Logs
2. Look for "Processed N frames" (should increment)
3. Look for errors

### SI Not Receiving Frames

1. Verify SI on same CAN bus as EVTV
2. Check SI `BatTyp` setting (should be `LiIon_Ext-BMS` for CAN to work)
3. Monitor CAN bus traffic with analyzer to confirm SI frames are sending
4. Check SI firmware version (some versions ignore external BMS)

---

## What's Next

### Create Automations in HA

Guard against overcharge:
```yaml
automation:
  - alias: "SI: Stop charge if SOC > 95%"
    trigger:
      platform: numeric_state
      entity_id: sensor.sma_si_evtv_soc_pct
      above: 95
    action:
      service: switch.turn_off
      target:
        entity_id: switch.charger
```

High temp alert:
```yaml
  - alias: "SI: Alert if BMS temp > 50°C"
    trigger:
      platform: numeric_state
      entity_id: sensor.sma_si_evtv_temperature_c
      above: 50
    action:
      service: notify.mobile_app
      data:
        message: "SI BMS temp {{ states(...) }}°C"
```

### Dashboard in HA

Create a dashboard card showing:
- Pack voltage, current, SOC
- Cell voltages (min/max)
- Temperature trend
- Status indicator (charging/discharging/idle)

---

## Files in This Setup

- `bridge_direct.py` — Main bidirectional bridge (read EVTV, write SI)
- `protocol.py` — SMA SI protocol frame definitions
- `can_interface.py` — PCAN wrapper
- `addon_direct.json` — HAOS add-on manifest
- `run_bridge_direct.sh` — Startup script
- `requirements.txt` — Python dependencies
- `Dockerfile` — HAOS container image

---

**Status**: Ready to deploy on NAS with PCAN plugged in
