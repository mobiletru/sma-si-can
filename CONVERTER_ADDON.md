## SMA SI CAN - EVTV BMS Converter (HAOS Add-on)

**Architecture**: 
```
VM (PCAN) → Relay Server (9001) → HAOS Add-on → Parse+Convert → Home Assistant REST API
```

---

## Two-Part Setup

### Part 1: Relay Server on VM (with PCAN)

The relay server reads EVTV frames from PCAN and streams them to HAOS over TCP.

**On the VM:**

```bash
cd /path/to/sma-si-can

# Install dependencies
pip install -r requirements.txt

# Run relay server
python3 relay_server.py \
    --host 0.0.0.0 \
    --port 9001 \
    --channel PCAN_USBCH1
```

**Or as systemd service:**

```bash
sudo tee /etc/systemd/system/sma-si-relay.service > /dev/null <<EOF
[Unit]
Description=SMA SI CAN Relay Server
After=network.target

[Service]
Type=simple
User=<your-user>
WorkingDirectory=/path/to/sma-si-can
ExecStart=/usr/bin/python3 relay_server.py
Environment="PYTHONUNBUFFERED=1"
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable sma-si-relay
sudo systemctl start sma-si-relay
systemctl status sma-si-relay
```

**Verify relay is running:**

```bash
# Should show port 9001 listening
netstat -an | grep 9001

# Or connect and see welcome message
nc -zv nas.local 9001
```

---

### Part 2: Deploy HAOS Add-on (on NAS)

Once relay is running, deploy the converter as a HAOS add-on.

#### Option A: Install from Folder (for development)

```bash
# Copy to HAOS add-ons directory
scp -r /home/claude/sma-si-can \
  root@nas.local:/usr/share/hassio/addons/sma-si-evtv-converter

# Or if you have HAOS SSH access:
scp -r sma-si-can/ root@<nas-ip>:/addons/local/sma-si-converter
```

Then in HA UI:
1. Settings → Add-ons → **Create Add-on**
2. Select folder → choose **sma-si-evtv-converter**
3. Click **Install**

#### Option B: Install from Repository (production)

Create a custom add-on repository:

```bash
# Create repo structure
mkdir ~/ha-addons-repo
cd ~/ha-addons-repo

# Copy add-on
cp -r /path/to/sma-si-can ./sma-si-evtv-converter

# Create repository.json
cat > repository.json <<EOF
{
  "name": "Mobile CCS Add-ons",
  "url": "https://github.com/mobiletru/ha-addons",
  "maintainer": "Ben (Mobile CCS)"
}
EOF

# Push to GitHub
git add .
git commit -m "Add EVTV→SI converter"
git push
```

Then add repository to HA:
1. Settings → Add-ons → **Repositories**
2. Add URL: `https://github.com/mobiletru/ha-addons`
3. Browse → **SMA SI EVTV Converter** → Install

---

## Configure Add-on

After installation, click the add-on and configure:

```yaml
relay_host: nas.local          # Where VM relay server runs
relay_port: 9001               # Relay TCP port
ha_host: localhost             # HA host (usually localhost in HAOS)
ha_port: 8123                  # HA port
log_level: info                # debug/info/warning/error
```

**Start the add-on:**
- Click **Start**
- Check **Show in sidebar** (optional)
- View logs to verify it's working

---

## What Gets Created in HA

Once running, these entities appear:

**Converted SI Data:**
- `sensor.sma_si_evtv_pack_voltage_v` — Pack voltage (V)
- `sensor.sma_si_evtv_pack_current_a` — Pack current (A)
- `sensor.sma_si_evtv_temperature_c` — BMS temperature (°C)
- `sensor.sma_si_evtv_soc_pct` — State of Charge (%)
- `sensor.sma_si_evtv_soh_pct` — State of Health (%)
- `sensor.sma_si_evtv_cell_1_v` through `cell_4_v` — Cell voltages
- `sensor.sma_si_evtv_temp_1_c` through `temp_4_c` — Temperature sensors

All update in near real-time (~50ms) as frames arrive from relay.

---

## Troubleshooting

### Relay Server Won't Start

```bash
# Check PCAN is working
python3 -c "import can; print(can.detect_available_configs(interfaces=['pcan']))"

# Check port 9001 isn't already in use
sudo lsof -i :9001

# Run with DEBUG output
python3 relay_server.py --log-level DEBUG
```

### Add-on Won't Connect to Relay

```bash
# From HAOS, test relay connectivity
# (exec into the add-on container)
ha addon exec sma-si-evtv-converter nc -zv nas.local 9001

# Check relay host resolves
ha addon exec sma-si-evtv-converter nslookup nas.local
```

**If using IP address instead of hostname:**
- Relay config: `relay_host: 192.168.x.x` (IP of VM running relay)

### No Data Appearing in HA

1. Check add-on logs:
   ```
   Settings → Add-ons → SMA SI EVTV Converter → Logs
   ```

2. Look for errors or "Processed N frames"

3. Verify relay is sending data:
   ```bash
   # On VM, monitor relay connections
   tail -f /var/log/syslog | grep "relay"
   
   # Or check frame count increasing
   python3 relay_server.py --log-level DEBUG
   ```

4. Test HA API directly:
   ```bash
   curl http://nas.local:8123/api/
   # Should return {"message": "API running"}
   ```

---

## Files

- `relay_server.py` — TCP relay (runs on VM with PCAN)
- `converter_addon.py` — HAOS add-on (connects to relay, publishes HA)
- `protocol.py` — SMA SI CAN protocol definitions
- `addon.json` — HAOS add-on manifest
- `Dockerfile` — HAOS container image
- `run_converter.sh` — Add-on entry point
- `requirements.txt` — Python dependencies

---

## What the Converter Does

```
┌─────────────────────────────────────────────────────────────────┐
│ EVTV BMS on PCAN                                                │
├─────────────────────────────────────────────────────────────────┤
│ Frame 0x100: Pack voltage (2 bytes, 0.01V/LSB)                  │
│ Frame 0x101: Pack current (2 bytes, 0.1A/LSB, offset -3200A)    │
│ Frame 0x102: SOC/SOH (2 bytes)                                  │
│ Frame 0x103-0x104: Cell voltages 1-16 (2 bytes each, 0.001V)    │
│ Frame 0x105: Temperatures (4 bytes, 0.1°C, -40°C offset)        │
└─────────────────────────────────────────────────────────────────┘
                             ↓
              Relay Server reads & streams frames
                             ↓
┌─────────────────────────────────────────────────────────────────┐
│ HAOS Add-on (Parser + Encoder)                                  │
├─────────────────────────────────────────────────────────────────┤
│ Extract: voltage, current, SOC, temps, cell voltages             │
│ Encode as SMA SI CAN protocol frames (0x351, 0x35F, 0x355, etc) │
│ Publish to HA REST API                                          │
└─────────────────────────────────────────────────────────────────┘
                             ↓
┌─────────────────────────────────────────────────────────────────┐
│ Home Assistant Sensors                                          │
├─────────────────────────────────────────────────────────────────┤
│ sensor.sma_si_evtv_pack_voltage_v                               │
│ sensor.sma_si_evtv_pack_current_a                               │
│ sensor.sma_si_evtv_soc_pct                                      │
│ ... (and cell voltages, temps, SOH)                             │
└─────────────────────────────────────────────────────────────────┘
```

---

## Next: Use in Automations

Once data is in HA, create automations to guard the SI:

```yaml
automation:
  - alias: "SI: Warn if overcharge"
    trigger:
      platform: numeric_state
      entity_id: sensor.sma_si_evtv_soc_pct
      above: 95
    action:
      service: notify.mobile_app
      data:
        message: "SOC {{ states('sensor.sma_si_evtv_soc_pct') }}% - approaching limit"

  - alias: "SI: High temp alert"
    trigger:
      platform: numeric_state
      entity_id: sensor.sma_si_evtv_temperature_c
      above: 50
    action:
      service: climate.set_preset_mode
      target:
        entity_id: climate.si_load_control
      data:
        preset_mode: eco
```

---

**Status**: Ready for deployment
