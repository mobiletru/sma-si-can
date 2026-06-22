# AGENTS.md

## Cursor Cloud specific instructions

### What this repo is
A single, headless **Home Assistant (HAOS) add-on** that bridges a CAN bus:
it reads EVTV BMS frames from a PCAN-USB adapter, publishes them to Home
Assistant over the REST API, and sends SMA Sunny Island 6048 protocol frames
back onto the bus. There is no web UI of its own — it is a Python service.

- App code: `sma-si-6048-bridge/rootfs/app/` (`bridge_direct.py` entry point,
  `protocol.py` SI frame encode/decode, `can_interface.py` python-can wrapper).
- Add-on packaging: `sma-si-6048-bridge/{addon.json,Dockerfile,run.sh}`.

### Dependencies (installed by the startup update script)
Only `python-can` and `requests` are needed and are installed into the user
site. `requirements.txt` is the source of truth and is valid; the previously
listed `python-pcan>=1.3.0` (not a real PyPI package) has been removed. PCAN
support is built into `python-can` (the `pcan`/`socketcan` interfaces), so no
extra package is required. The startup update script installs `python-can` and
`requests` explicitly (rather than `-r requirements.txt`) so it keeps working
even on older checkouts that still contain the bad pin.

### CAN backend selection (important for HAOS)
On Home Assistant OS a PCAN-USB adapter is handled natively by the kernel via
**SocketCAN** and appears as **`can0`**, not as the PCAN-Basic `PCAN_USBCH1`
chardev (that proprietary driver cannot be installed on HAOS). The bridge
therefore supports a selectable backend via `--can-interface` /
`CAN_INTERFACE` / the `can_interface` add-on option:
- `socketcan` (default, channel `can0`) — for HAOS / native Linux CAN.
- `pcan` — only where the PCAN-Basic driver is installed.
- `virtual` — in-process bus for hardware-free dev/testing.
`run.sh` best-effort brings the SocketCAN link up (`ip link set <ch> up type
can bitrate 500000`); this needs `NET_ADMIN` and `iproute2` in the image.

### Lint / test / run
- **Lint** (no linter configured in repo): `python3 -m compileall sma-si-6048-bridge/rootfs/app`
- **Tests**: none exist in the repo.
- **Run the real service**: `python3 sma-si-6048-bridge/rootfs/app/bridge_direct.py --help`.
  Real CAN hardware and the `vcan` kernel module are **not available in the
  Cloud VM** (no kernel-module tooling, no `ip`), so `socketcan`/`pcan` cannot
  run here — use the `virtual` backend instead.

### Running the pipeline without hardware
Run the real code over the in-process `virtual` backend, e.g.
`bridge_direct.py --can-interface virtual --can-channel demo`, with `HABridge`
pointed at a mock HTTP server that answers `GET /api/` with 200 and accepts
`POST /api/states/...`. Note the `virtual` bus is in-process only, so the
frame simulator, the bridge, and any monitor must run in the **same process**
(threads) on the same channel; cross-process virtual buses do not share
traffic.

### Known remaining issue (not yet fixed)
`sma-si-6048-bridge/Dockerfile` is out of sync with the actual files: it
`COPY`s `converter_addon.py` / `run_converter.sh` (which do not exist; the real
files are `bridge_direct.py` and `run.sh`) and uses `apt-get` although the HA
base-python image is Alpine (`apk`). The HAOS add-on image will not build until
this is corrected (and `iproute2` added for the SocketCAN `ip link` step).
