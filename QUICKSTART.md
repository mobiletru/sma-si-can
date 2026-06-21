## SMA Sunny Island CAN - Direct to Home Assistant

**Architecture**: VM with PCAN → CAN frames → REST API → Home Assistant

---

## Quick Start

### On VM (with PCAN adapter)

```bash
# Clone/copy sma-si-can project
cd /path/to/sma-si-can

# Install Python dependencies
pip install -r requirements.txt

# Run the bridge
python ha_direct.py \
    --can-channel PCAN_USBCH1 \
    --ha-host nas.local \
    --ha-port 8123 \
    --ha-token <your-long-lived-token>
```

### Get HA Long-Lived Token

1. In Home Assistant UI: Settings → Developers Tools → Long-Lived Access Tokens
2. Create new token (name: "SMA SI CAN")
3. Copy token → use in `--ha-token` above

### Environment Variables (alternative to CLI args)

```bash
export CAN_CHANNEL=PCAN_USBCH1
export HA_HOST=nas.local
export HA_PORT=8123
export HA_TOKEN=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
export LOG_LEVEL=INFO

python ha_direct.py
```

### Run as Systemd Service (permanent)

```bash
sudo tee /etc/systemd/system/sma-si-can.service > /dev/null <<EOF
[Unit]
Description=SMA Sunny Island CAN Bridge
After=network.target home-assistant.service

[Service]
Type=simple
User=<your-user>
WorkingDirectory=/path/to/sma-si-can
ExecStart=/usr/bin/python3 ha_direct.py
Environment="HA_HOST=nas.local"
Environment="HA_PORT=8123"
Environment="HA_TOKEN=<token>"
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable sma-si-can
sudo systemctl start sma-si-can
sudo systemctl status sma-si-can
```

---

## What Gets Created in Home Assistant

Once running, these entities appear automatically:

- `sensor.sma_si_pack_voltage_v` — Pack voltage (V)
- `sensor.sma_si_pack_current_a` — Pack current (A)  
- `sensor.sma_si_temperature_c` — BMS temp (°C)
- `sensor.sma_si_soc_pct` — State of Charge (%)
- `sensor.sma_si_soh_pct` — State of Health (%)
- `sensor.sma_si_cell_1_v` through `cell_4_v` — Individual cell voltages
- `sensor.sma_si_temp_1_c` through `temp_4_c` — Temperature sensors

All entities:
- Update as frames arrive (~100 ms latency)
- Have correct units and device classes
- Show last update timestamp
- Group under "SMA Sunny Island BMS" device

---

## Troubleshooting

### Can't connect to PCAN

```bash
# Check if python-can detects PCAN adapter
python3 -c "import can; print(can.__version__)"
python3 -c "import can; print(can.detect_available_configs(interfaces=['pcan']))"

# Check if PCAN driver is loaded
lsmod | grep pcan

# Check USB device
lsusb | grep Peak
```

### Can't reach Home Assistant

```bash
# Test connectivity
curl -H "Authorization: Bearer $HA_TOKEN" \
  http://nas.local:8123/api/

# If using DNS name, verify it resolves
ping nas.local
ping home.mobileccs.com
```

### Not seeing frames

```bash
# Run with DEBUG log level
python ha_direct.py --log-level DEBUG

# Look for "Processed N frames" messages
# If frame count doesn't increment, PCAN isn't receiving
```

### Entities don't appear in HA

1. Check HA logs: Settings → Developers Tools → Logs
2. Verify token is valid (expires 1 year from creation)
3. Try accessing API with token:
   ```bash
   curl -H "Authorization: Bearer $HA_TOKEN" \
     http://nas.local:8123/api/states/sensor.sma_si_pack_voltage_v
   ```

---

## Files

- `ha_direct.py` — Main bridge script (run on VM)
- `can_interface.py` — PCAN adapter wrapper
- `protocol.py` — SMA Li-Ion BMS protocol definitions
- `requirements.txt` — Python dependencies
- `relay_client.py` — *Deprecated* (was MQTT version)
- `relay_server.py` — *Deprecated* (was relay server)

---

## Next Steps

### After BatTyp is Fixed on SI

Once Sunny Island's `BatTyp` is corrected from VRLA → `LiIon_Ext-BMS`:
- Voltage readings should normalize (51-53V @ 94% SOC)
- CAN BMS path will be fully active
- Real-time cell data + temps will flow in
- Use HA automations to guard setpoints and control loads

### Filtering & Decoding

To decode specific frame payloads:

```bash
# Add to ha_direct.py to see raw frame data
logger.info(f"Frame 0x{frame_id:03X}: {data.hex()}")
```

Then use `protocol.py` functions to parse manually.

---

**Status**: Ready for test run on VM with PCAN
