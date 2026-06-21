"""
Modbus BMS → SMA Sunny Island CAN (PCAN)
Reads battery data over Modbus TCP/RTU, encodes SMA SI protocol frames, transmits on PCAN.
"""

import logging
import os
import time

from bms_state import BMSState
from can_interface import create_pcan_interface, create_socketcan_interface
from modbus_bms import ModbusBMSReader
from si_transmitter import SITransmitter

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


class ModbusToSIBridge:
    """Poll Modbus BMS and transmit SMA SI CAN frames on PCAN."""

    def __init__(
        self,
        modbus_reader: ModbusBMSReader,
        transmitter: SITransmitter,
        poll_interval: float = 0.5,
    ):
        self.modbus = modbus_reader
        self.transmitter = transmitter
        self.poll_interval = poll_interval
        self.last_state = BMSState()

    def run(self) -> None:
        logger.info("Starting Modbus → SMA SI CAN bridge")

        if not self.modbus.connect():
            logger.error("Modbus connect failed")
            return

        try:
            while True:
                state = self.modbus.poll()
                if state is not None:
                    self.last_state = state

                if self.transmitter.should_send():
                    self.transmitter.send_all(self.last_state)

                time.sleep(self.poll_interval)

        except KeyboardInterrupt:
            logger.info("Stopped")
        finally:
            self.modbus.disconnect()


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description="Modbus BMS → SMA Sunny Island CAN (PCAN) converter",
    )
    parser.add_argument(
        "--modbus-mode",
        default=os.getenv("MODBUS_MODE", "tcp"),
        choices=["tcp", "rtu"],
        help="Modbus transport (tcp or rtu)",
    )
    parser.add_argument(
        "--modbus-host",
        default=os.getenv("MODBUS_HOST", "127.0.0.1"),
        help="Modbus TCP host",
    )
    parser.add_argument(
        "--modbus-port",
        type=int,
        default=int(os.getenv("MODBUS_PORT", "502")),
        help="Modbus TCP port",
    )
    parser.add_argument(
        "--modbus-unit",
        type=int,
        default=int(os.getenv("MODBUS_UNIT", "1")),
        help="Modbus slave/unit ID",
    )
    parser.add_argument(
        "--modbus-serial",
        default=os.getenv("MODBUS_SERIAL", "/dev/ttyUSB0"),
        help="Modbus RTU serial port",
    )
    parser.add_argument(
        "--modbus-baud",
        type=int,
        default=int(os.getenv("MODBUS_BAUD", "9600")),
        help="Modbus RTU baud rate",
    )
    parser.add_argument(
        "--register-map",
        default=os.getenv("MODBUS_REGISTER_MAP", "modbus_register_map.json"),
        help="JSON file with Modbus register definitions",
    )
    parser.add_argument(
        "--can-interface",
        default=os.getenv("CAN_INTERFACE", "pcan"),
        choices=["pcan", "socketcan"],
        help="CAN adapter type",
    )
    parser.add_argument(
        "--can-channel",
        default=os.getenv("CAN_CHANNEL", "PCAN_USBCH1"),
        help="PCAN channel or SocketCAN interface (e.g. can0)",
    )
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=float(os.getenv("MODBUS_POLL_INTERVAL", "0.5")),
        help="Seconds between Modbus polls",
    )
    parser.add_argument(
        "--send-interval",
        type=float,
        default=float(os.getenv("CAN_SEND_INTERVAL", "0.05")),
        help="Seconds between CAN frame bursts (20 Hz default)",
    )
    parser.add_argument(
        "--log-level",
        default=os.getenv("LOG_LEVEL", "INFO").upper(),
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
    )

    args = parser.parse_args()
    logging.getLogger().setLevel(getattr(logging, args.log_level))

    modbus = ModbusBMSReader(
        mode=args.modbus_mode,
        host=args.modbus_host,
        port=args.modbus_port,
        unit_id=args.modbus_unit,
        serial_port=args.modbus_serial,
        baudrate=args.modbus_baud,
        register_map_file=args.register_map,
    )

    logger.info("Connecting to CAN: %s %s", args.can_interface, args.can_channel)
    if args.can_interface == "socketcan":
        can = create_socketcan_interface(channel=args.can_channel)
    else:
        can = create_pcan_interface(channel=args.can_channel)

    if not can.connect():
        logger.error("CAN connect failed")
        return 1

    bridge = ModbusToSIBridge(
        modbus_reader=modbus,
        transmitter=SITransmitter(can, send_interval=args.send_interval),
        poll_interval=args.poll_interval,
    )
    bridge.run()
    can.disconnect()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())