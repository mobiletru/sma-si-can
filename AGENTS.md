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
site. **Do not run `pip install -r sma-si-6048-bridge/requirements.txt`** — it
lists `python-pcan>=1.3.0`, which is **not a real PyPI package** and will fail.
PCAN support is built into `python-can` (the `pcan` interface), and no source
file imports a `python-pcan`/`pcan` module, so it is not required for
development.

### Lint / test / run
- **Lint** (no linter configured in repo): `python3 -m compileall sma-si-6048-bridge/rootfs/app`
- **Tests**: none exist in the repo.
- **Run the real service**: `python3 sma-si-6048-bridge/rootfs/app/bridge_direct.py --help`
  shows the CLI. Normal operation needs a PCAN-USB adapter (or SocketCAN
  `vcan`) plus a reachable Home Assistant. **Neither real CAN hardware nor a
  `vcan` kernel module is available in the Cloud VM** (no kernel-module
  tooling), so the literal hardware path cannot run here.

### Running the pipeline without hardware (non-obvious)
To exercise the bridge end-to-end in the VM, drive the real classes
(`EVTVReader`, `SIFrameBuilder`, `HABridge`, `SIController`, `EVTVtoSIBridge`)
over python-can's **in-process `virtual` interface** and point `HABridge` at a
small mock HTTP server that answers `GET /api/` with 200 and accepts
`POST /api/states/...`.

Caveat when wiring the CAN interface directly: `CANBusInterface.connect()`
calls `self.bus.add_reader(...)`, which **does not exist on `can.BusABC` in
python-can 4.x** (so `connect()` raises). Bypass `connect()` and attach the
`BufferedReader` via `can.Notifier(bus, [reader])` instead. Use
`receive_own_messages=False` and put the simulator, the app, and a monitor on
the same virtual channel.
