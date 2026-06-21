"""CLI for SMA Sunny Island Modbus read/write."""

from __future__ import annotations

import argparse
import json
import os

from grid_code import apply_grid_code
from sma_modbus import SMAModbusClient


def main() -> int:
    parser = argparse.ArgumentParser(description="SMA Sunny Island Modbus tool")
    parser.add_argument("action", choices=["read", "write", "apply-grid"])
    parser.add_argument("--register", action="append", default=[])
    parser.add_argument("--value", type=float)
    parser.add_argument("--grid-code", default=os.getenv("GRID_CODE", ""))
    parser.add_argument("--modbus-host", default=os.getenv("MODBUS_HOST", "127.0.0.1"))
    parser.add_argument("--modbus-port", type=int, default=int(os.getenv("MODBUS_PORT", "502")))
    parser.add_argument("--modbus-unit", type=int, default=int(os.getenv("MODBUS_UNIT", "3")))
    parser.add_argument("--register-map", default="sma_si_register_map.json")
    parser.add_argument("--grid-presets", default="grid_code_presets.json")
    args = parser.parse_args()

    client = SMAModbusClient(
        host=args.modbus_host,
        port=args.modbus_port,
        unit_id=args.modbus_unit,
        register_map_file=args.register_map,
    )
    if not client.connect():
        return 1

    try:
        if args.action == "read":
            values = client.read_many(args.register or None)
            print(json.dumps(values, indent=2))
        elif args.action == "write":
            if not args.register or args.value is None:
                parser.error("write requires --register and --value")
            ok = client.write(args.register[0], args.value)
            return 0 if ok else 1
        else:
            results = apply_grid_code(client, args.grid_code, args.grid_presets)
            print(json.dumps(results, indent=2))
            return 0 if all(results.values()) else 1
    finally:
        client.disconnect()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
