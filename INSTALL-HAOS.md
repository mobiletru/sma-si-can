# Install — HAOS app (GitHub repository)

## Repository URL

Add this in **Settings → Apps → ⋮ → Repositories**:

```text
https://github.com/mobiletru/sma-si-can-addons
```

| Add here | Do **not** add here |
|----------|---------------------|
| `sma-si-can-addons` | `sma-sunny-island` (HACS integration only) |
| | `sma-si-can` (dev/meta repo — not an app repository) |

## App

- **Name:** SMA Sunny Island CAN
- **Slug:** `local_sunny_island_can`
- **UI:** Settings → Apps → SMA Sunny Island CAN → **Open Web UI**
- **Ingress URL (HA 2026):** `/app/local_sunny_island_can`

Bare `/local_sunny_island_can` returns 404 — use **Open Web UI** or the `/app/` path.

## Install steps

1. **Settings → Apps → ⋮ → Repositories**
2. Remove `sma-sunny-island` or `sma-si-can` if listed (wrong repos)
3. Add `https://github.com/mobiletru/sma-si-can-addons`
4. **⋮ → Check for updates** + hard refresh (Ctrl+F5)
5. Install **SMA Sunny Island CAN** from **SMA Sunny Island Add-ons**
6. Configure `modbus_host` to your WebBox/inverter IP (not `127.0.0.1`), then **Start**

## Configuration example

```yaml
modbus_mode: tcp
modbus_host: 192.168.1.50
modbus_port: 502
modbus_unit: 3
grid_code: AS4777.3
write_grid_on_start: true
publish_ha: true
enable_can: false
```

Set `grid_code: none` to skip grid preset on startup.

## Troubleshooting

### Repo listed but no app in store

1. Confirm URL is **`sma-si-can-addons`**, not `sma-sunny-island` or `sma-si-can`
2. Remove repo → **Check for updates** → re-add → **Check for updates** again
3. Hard refresh (Ctrl+F5)
4. **Settings → System → Logs → Supervisor** — look for `Invalid Add-on config`

### "not a valid app repository"

You added the HACS integration or meta repo. Use only:

```text
https://github.com/mobiletru/sma-si-can-addons
```

## Local zip (dev fallback)

For offline or dev testing only — production installs should use the GitHub repo above.

See [INSTALL-ZIP.md](INSTALL-ZIP.md).
