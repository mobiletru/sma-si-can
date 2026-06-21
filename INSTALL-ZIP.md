# Install — local zip (dev fallback)

> **Recommended:** Install from the GitHub repository instead — [INSTALL-HAOS.md](INSTALL-HAOS.md)

Use a zip only when you cannot add the app repository (offline lab, pre-release testing).

## Build

From this workspace (requires `haos-addon-modbus/` cloned):

```powershell
.\clone-repos.ps1   # if needed
.\build-zips.ps1
```

Output: `dist/local_sunny_island_can.zip`

## Install

1. Copy the zip to your Home Assistant host
2. Extract into the **`addons`** Samba share:

```text
addons/local_sunny_island_can/config.yaml
```

**Wrong (not detected):** `addons/local/local_sunny_island_can/`

3. Profile → **Advanced mode ON**
4. **Settings → Apps → Check for updates**
5. Install from **Local apps** → configure → start

App UI: Settings → Apps → SMA Sunny Island CAN → **Open Web UI**
