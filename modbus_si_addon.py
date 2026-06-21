"""
SMA Sunny Island Modbus bridge for Home Assistant OS.

Reads and writes SMA Modbus registers, applies grid code presets on startup,
optionally publishes Home Assistant sensors, and optionally forwards battery
data to the Sunny Island CAN bus.
"""

from __future__ import annotations

import argparse
import logging
import os
import time
from typing import Dict, Optional

import requests

from bms_state import BMSState
from can_interface import create_pcan_interface, create_socketcan_interface
from grid_code import apply_grid_code
from si_transmitter import SITransmitter
from sma_modbus import SMAModbusClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


HA_SENSOR_MAP = {
    "battery_voltage_v": ("battery_voltage_v", "V"),
    "battery_current_a": ("battery_current_a", "A"),
    "battery_soc_pct": ("battery_soc_pct", "%"),
    "battery_soh_pct": ("battery_soh_pct", "%"),
    "battery_temp_c": ("battery_temp_c", "°C"),
    "grid_nominal_voltage_v": ("grid_nominal_voltage_v", "V"),
    "grid_nominal_frequency_hz": ("grid_nominal_frequency_hz", "Hz"),
    "country_standard": ("country_standard", ""),
    "grid_import_power_w": ("grid_import_power_w", "W"),
    "grid_export_power_w": ("grid_export_power_w", "W"),
    "pv_power_w": ("pv_power_w", "W"),
}


class HAPublisher:
    def __init__(self, ha_host: str, ha_port: int = 8123, enabled: bool = True):
        self.enabled = enabled
        self.ha_url = f"http://{ha_host}:{ha_port}"
        self.session = requests.Session()
        self.connected = False

    def connect(self) -> bool:
        if not self.enabled:
            return True
        try:
            resp = self.session.get(f"{self.ha_url}/api/", timeout=5)
            self.connected = resp.status_code == 200
            if self.connected:
                logger.info("Connected to Home Assistant at %s", self.ha_url)
            return self.connected
        except Exception as exc:
            logger.error("Home Assistant connect failed: %s", exc)
            return False

    def publish(self, entity_suffix: str, value, unit: str = "") -> None:
        if not self.enabled or not self.connected:
            return
        payload = {
            "state": str(value),
            "attributes": {
                "unit_of_measurement": unit,
                "friendly_name": entity_suffix.replace("_", " ").title(),
            },
        }
        try:
            self.session.post(
                f"{self.ha_url}/api/states/sensor.sma_si_modbus_{entity_suffix}",
                json=payload,
                timeout=5,
            )
        except Exception as exc:
            logger.debug("HA publish failed for %s: %s", entity_suffix, exc)


class ModbusSIService:
    def __init__(
        self,
        modbus: SMAModbusClient,
        poll_interval: float = 2.0,
        ha: Optional[HAPublisher] = None,
        transmitter: Optional[SITransmitter] = None,
        read_registers: Optional[list[str]] = None,
    ):
        self.modbus = modbus
        self.poll_interval = poll_interval
        self.ha = ha
        self.transmitter = transmitter
        self.read_registers = read_registers
        self.last_state = BMSState()
        self.poll_count = 0

    def _state_from_reads(self, values: Dict) -> BMSState:
        state = BMSState()
        if "battery_voltage_v" in values:
            state.voltage_v = float(values["battery_voltage_v"])
        if "battery_current_a" in values:
            state.current_a = float(values["battery_current_a"])
        if "battery_soc_pct" in values:
            state.soc_pct = int(round(float(values["battery_soc_pct"])))
        if "battery_soh_pct" in values:
            state.soh_pct = int(round(float(values["battery_soh_pct"])))
        if "battery_temp_c" in values:
            state.temp_c = float(values["battery_temp_c"])
        state.update_status_temp()
        return state

    def poll_once(self) -> Dict:
        values = self.modbus.read_many(self.read_registers)
        self.poll_count += 1

        if self.ha:
            for register_name, value in values.items():
                mapping = HA_SENSOR_MAP.get(register_name)
                if mapping:
                    suffix, unit = mapping
                    self.ha.publish(suffix, value, unit)

        if values:
            self.last_state = self._state_from_reads(values)

        if self.transmitter and self.transmitter.should_send():
            self.transmitter.send_all(self.last_state)

        if self.poll_count % 10 == 0:
            logger.info(
                "Modbus poll %d | V=%.1fV I=%.1fA SOC=%d%% country=%s",
                self.poll_count,
                self.last_state.voltage_v,
                self.last_state.current_a,
                self.last_state.soc_pct,
                values.get("country_standard", "?"),
            )

        return values

    def run(self) -> None:
        logger.info("Starting SMA Modbus read/write service")
        while True:
            self.poll_once()
            time.sleep(self.poll_interval)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="SMA Sunny Island Modbus HAOS service")
    parser.add_argument("--modbus-mode", default=os.getenv("MODBUS_MODE", "tcp"), choices=["tcp", "rtu"])
    parser.add_argument("--modbus-host", default=os.getenv("MODBUS_HOST", "127.0.0.1"))
    parser.add_argument("--modbus-port", type=int, default=int(os.getenv("MODBUS_PORT", "502")))
    parser.add_argument("--modbus-unit", type=int, default=int(os.getenv("MODBUS_UNIT", "3")))
    parser.add_argument("--modbus-serial", default=os.getenv("MODBUS_SERIAL", "/dev/ttyUSB0"))
    parser.add_argument("--modbus-baud", type=int, default=int(os.getenv("MODBUS_BAUD", "9600")))
    parser.add_argument(
        "--register-map",
        default=os.getenv("SMA_REGISTER_MAP", "/app/sma_si_register_map.json"),
    )
    parser.add_argument(
        "--grid-presets",
        default=os.getenv("GRID_PRESETS_PATH", "/app/grid_code_presets.json"),
    )
    parser.add_argument("--grid-code", default=os.getenv("GRID_CODE", ""))
    parser.add_argument(
        "--write-grid-on-start",
        default=os.getenv("WRITE_GRID_ON_START", "false").lower(),
        choices=["true", "false"],
    )
    parser.add_argument("--poll-interval", type=float, default=float(os.getenv("POLL_INTERVAL", "2.0")))
    parser.add_argument("--send-interval", type=float, default=float(os.getenv("CAN_SEND_INTERVAL", "0.05")))
    parser.add_argument("--enable-can", default=os.getenv("ENABLE_CAN", "false").lower(), choices=["true", "false"])
    parser.add_argument("--can-interface", default=os.getenv("CAN_INTERFACE", "pcan"), choices=["pcan", "socketcan"])
    parser.add_argument("--can-channel", default=os.getenv("CAN_CHANNEL", "PCAN_USBCH1"))
    parser.add_argument("--publish-ha", default=os.getenv("PUBLISH_HA", "true").lower(), choices=["true", "false"])
    parser.add_argument("--ha-host", default=os.getenv("HA_HOST", "localhost"))
    parser.add_argument("--ha-port", type=int, default=int(os.getenv("HA_PORT", "8123")))
    parser.add_argument("--log-level", default=os.getenv("LOG_LEVEL", "INFO").upper())
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    logging.getLogger().setLevel(getattr(logging, args.log_level))

    modbus = SMAModbusClient(
        mode=args.modbus_mode,
        host=args.modbus_host,
        port=args.modbus_port,
        unit_id=args.modbus_unit,
        serial_port=args.modbus_serial,
        baudrate=args.modbus_baud,
        register_map_file=args.register_map,
    )

    if not modbus.connect():
        logger.error("Modbus connect failed")
        return 1

    if args.write_grid_on_start == "true" and args.grid_code:
        results = apply_grid_code(modbus, args.grid_code, args.grid_presets)
        failed = [name for name, ok in results.items() if not ok]
        if failed:
            logger.warning("Some grid code writes failed: %s", ", ".join(failed))
        else:
            logger.info("Grid code %s applied", args.grid_code)

    transmitter = None
    if args.enable_can == "true":
        if args.can_interface == "socketcan":
            can = create_socketcan_interface(channel=args.can_channel)
        else:
            can = create_pcan_interface(channel=args.can_channel)
        if not can.connect():
            logger.error("CAN connect failed")
            modbus.disconnect()
            return 1
        transmitter = SITransmitter(can, send_interval=args.send_interval)
        logger.info("CAN enabled: %s %s", args.can_interface, args.can_channel)

    ha = HAPublisher(args.ha_host, args.ha_port, enabled=args.publish_ha == "true")
    ha.connect()

    service = ModbusSIService(
        modbus=modbus,
        poll_interval=args.poll_interval,
        ha=ha,
        transmitter=transmitter,
    )

    try:
        service.run()
    except KeyboardInterrupt:
        logger.info("Stopped")
    finally:
        modbus.disconnect()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
