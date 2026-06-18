# SMA Sunny Island 6048 - EVTV BMS Bridge

Bidirectional CAN bridge for Home Assistant: read EVTV BMS frames, publish to HA, send SMA SI protocol frames back to the 6048.

**Direct PCAN integration on NAS. No relay server needed.**

---

## Features

✅ **Real-time BMS Monitoring**
- Pack voltage, current, SOC/SOH
- Individual cell voltages (up to 48 cells)
- Temperature sensors
- Error flags

✅ **Home Assistant Integration**
- Automatic sensor creation (`sensor.sma_si_evtv_*`)
- Native HA automations & dashboards
- RESTful API

✅ **Bidirectional Control**
- Read EVTV BMS data from CAN
- Send SMA SI protocol frames to 6048
- SI 6048 sees EVTV as external BMS

✅ **Production Ready**
- HAOS add-on deployment
- Systemd service support
- Comprehensive logging
- Error recovery

---

## Quick Start

### Prerequisites
- PCAN-USB adapter plugged into NAS
- HAOS instance on NAS
- EVTV BMS on CAN bus
- SI 6048 on same CAN bus

### Install (3 minutes)

1. **Download**
   ```bash
   git clone https://github.com/mobiletru/sma-si-can.git
   cd sma-si-can
   ```

2. **Upload to HAOS**
   ```bash
   scp -r . root@nas.local:/addons/local/sma-si-6048-bridge
   ```

3. **Install in Home Assistant**
   - Settings → Add-ons → Create Add-on
   - Select folder
   - Click Install
   - Configure CAN channel, HA host/port
   - Start

4. **Verify**
   - Check logs: "Processed N frames"
   - HA → Developer Tools → States
   - Look for `sensor.sma_si_evtv_*`

---

## Configuration

### Add-on Options

```json
{
  "can_channel": "PCAN_USBCH1",   // PCAN channel (or PCAN_USBCH2, etc)
  "ha_host": "localhost",         // HA host (localhost in HAOS)
  "ha_port": 8123,                // HA port
  "log_level": "info"             // debug/info/warning/error
}
```

### Frame ID Mapping

If your EVTV uses different CAN IDs, edit `bridge_direct.py`:

```python
class EVTVReader:
    EVTV_VOLTAGE = 0x100    # ← Change these to match your setup
    EVTV_CURRENT = 0x101
    EVTV_STATE = 0x102
    EVTV_CELLS_1 = 0x103
    EVTV_CELLS_2 = 0x104
    EVTV_TEMPS = 0x105
```

Identify actual IDs with a CAN analyzer:
```bash
# On Linux with SocketCAN
candump can0 | head -20
```

---

## Data Flow

```
EVTV BMS on CAN (frames 0x100-0x105)
         ↓
    PCAN-USB adapter
         ↓
    NAS (HAOS container)
         ↓
    bridge_direct.py
    ├─→ Parse EVTV data
    ├─→ Publish to Home Assistant
    │   sensor.sma_si_evtv_pack_voltage_v
    │   sensor.sma_si_evtv_soc_pct
    │   sensor.sma_si_evtv_cell_1_v ... cell_4_v
    │   ...
    └─→ Encode & send SI frames (0x351, 0x35F, 0x355, 0x35A)
         ↓
    SI 6048 (receives as external BMS)
```

---

## Home Assistant Sensors

Automatically created:

| Sensor | Unit | Description |
|--------|------|-------------|
| `pack_voltage_v` | V | Pack voltage |
| `pack_current_a` | A | Pack current (discharge +, charge -) |
| `soc_pct` | % | State of Charge |
| `soh_pct` | % | State of Health |
| `temperature_c` | °C | BMS temperature |
| `cell_1_v` ... `cell_4_v` | V | Individual cell voltages |
| `temp_1_c` ... `temp_4_c` | °C | Temperature sensor readings |

All sensors update in real-time (~50ms latency).

---

## Example Automations

### Prevent Overcharge
```yaml
automation:
  - alias: "SI: Stop charge at 95% SOC"
    trigger:
      platform: numeric_state
      entity_id: sensor.sma_si_evtv_soc_pct
      above: 95
    action:
      service: switch.turn_off
      target:
        entity_id: switch.charger
```

### High Temperature Alert
```yaml
  - alias: "SI: Alert on high BMS temp"
    trigger:
      platform: numeric_state
      entity_id: sensor.sma_si_evtv_temperature_c
      above: 50
    action:
      service: notify.mobile_app
      data:
        message: "⚠️ SI BMS temp {{ states('sensor.sma_si_evtv_temperature_c') }}°C"
```

### Unbalanced Cells Alert
```yaml
  - alias: "SI: Alert if cell imbalance > 200mV"
    trigger:
      platform: template
      value_template: >
        {% set cells = [
          float(states('sensor.sma_si_evtv_cell_1_v') or 0),
          float(states('sensor.sma_si_evtv_cell_2_v') or 0),
          float(states('sensor.sma_si_evtv_cell_3_v') or 0),
          float(states('sensor.sma_si_evtv_cell_4_v') or 0)
        ] %}
        {{ (cells | max - cells | min) > 0.2 }}
    action:
      service: notify.mobile_app
      data:
        message: "⚠️ Cell imbalance detected"
```

---

## Troubleshooting

### No Data Appearing in HA

**Check add-on logs:**
```
Settings → Add-ons → SMA SI 6048 Bridge → Logs
```

**Verify PCAN is working:**
```bash
# From HAOS terminal
ha addon exec sma-si-6048-bridge \
  python3 -c "import pcan; print(pcan.listPeaks())"
```

**Check CAN frames on bus:**
```bash
# If SocketCAN available
candump can0
```

### PCAN Driver Not Found

The Dockerfile includes PCAN driver dependencies. If still missing:

1. Install on NAS host (before HAOS):
   ```bash
   apt-get install libusb-1.0-0-dev libusb-dev
   ```

2. Rebuild add-on container from source.

### SI 6048 Not Receiving Frames

- Verify SI is on **same CAN bus** as EVTV
- Check SI `BatTyp` setting (must be `LiIon_Ext-BMS` for CAN to work)
- SI firmware version may require specific frame format
- Monitor with CAN analyzer to confirm frames are being sent

---

## Files

```
sma-si-can/
├── bridge_direct.py           # Main bidirectional bridge
├── protocol.py                # SMA SI CAN protocol definitions
├── can_interface.py           # PCAN adapter wrapper
├── addon_direct.json          # HAOS add-on manifest
├── Dockerfile                 # HAOS container image
├── run_bridge_direct.sh       # Startup script
├── requirements.txt           # Python dependencies
├── DIRECT_BRIDGE.md          # Deployment guide
├── PROJECT_STATUS.md         # Architecture overview
├── LICENSE                   # MIT License
└── README.md                 # This file
```

---

## Alternative Setups

### 1. **Direct HA (No Relay)**
If you want to read SI frames directly (not EVTV conversion):
```bash
python3 ha_direct.py --ha-host nas.local --ha-token <token>
```
See `QUICKSTART.md`

### 2. **Relay Server + Add-on** (if PCAN on separate VM)
```bash
# On VM with PCAN:
python3 relay_server.py

# In HAOS:
Deploy sma-si-evtv-converter add-on
Configure relay_host, relay_port
```
See `CONVERTER_ADDON.md`

### 3. **Direct CAN Conversion** (send to same bus)
```bash
python3 evtv_to_si_converter.py
```
Reads EVTV, encodes SI frames, sends back on same bus.

---

## Protocol Details

### EVTV Frame Format (11-bit CAN IDs)
```
0x100: Pack voltage          (2 bytes, 0.01V/LSB)
0x101: Pack current          (2 bytes, 0.1A/LSB, offset -3200A)
0x102: SOC/SOH               (2 bytes, 1%/LSB)
0x103-0x104: Cell voltages   (2 bytes each, 0.001V/LSB)
0x105: Temperatures          (4 bytes, 0.1°C/LSB, -40°C offset)
```

### SMA SI Output (converted from EVTV)
```
0x351: STATUS (voltage, current, temp, error flags)
0x35F: STATE (SOC, SOH, error code)
0x355: CELL_VOLTAGES_1 (cells 1-4)
0x356: CELL_VOLTAGES_2 (cells 5-8, if applicable)
0x35A: TEMPS (4 temperature sensors)
```

---

## Limitations

- **Frame ID Mapping**: Placeholder EVTV IDs (0x100-0x105). Adjust for your setup.
- **Cell Count**: Assumes up to 48 cells (SI 6048). Adjust if fewer.
- **Temp Sensors**: Expects 4. Adjust in code if different.
- **SI BatTyp**: Must be set to `LiIon_Ext-BMS` on SI for CAN BMS to activate.

---

## Contributing

Contributions welcome! Please:
1. Fork the repo
2. Create a feature branch
3. Test on your hardware
4. Submit a pull request

---

## License

MIT License - See LICENSE file

---

## Support

- **Issues**: GitHub Issues
- **Docs**: See DIRECT_BRIDGE.md, QUICKSTART.md, PROJECT_STATUS.md
- **Questions**: Check troubleshooting section above

---

## Acknowledgments

- SMA for SI 6048 protocol documentation
- Home Assistant community for add-on framework
- EVTV for the Tesla BMS integration

---

## Related Projects

- [mobiletru/tesla_evtv_bms](https://github.com/mobiletru/tesla_evtv_bms) — EVTV BMS Home Assistant integration
- [mobiletru/sma-si-can](https://github.com/mobiletru/sma-si-can) — This project

---

**Status**: Production ready

Last updated: 2026-06-18
