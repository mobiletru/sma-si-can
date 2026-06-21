"""Read BMS data over Modbus TCP/RTU with a configurable register map."""

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from bms_state import BMSState

logger = logging.getLogger(__name__)

try:
    from pymodbus.client import ModbusSerialClient, ModbusTcpClient
    from pymodbus.exceptions import ModbusException
except ImportError:
    ModbusSerialClient = None
    ModbusTcpClient = None
    ModbusException = Exception


@dataclass
class RegisterDef:
    """Single Modbus register definition."""

    address: int
    reg_type: str = "holding"
    dtype: str = "uint16"
    scale: float = 1.0
    offset: float = 0.0
    count: int = 1

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RegisterDef":
        return cls(
            address=int(data["address"]),
            reg_type=data.get("type", data.get("reg_type", "holding")),
            dtype=data.get("dtype", "uint16"),
            scale=float(data.get("scale", 1.0)),
            offset=float(data.get("offset", 0.0)),
            count=int(data.get("count", 1)),
        )


def _decode_register(raw: int, dtype: str) -> int:
    if dtype == "int16" and raw >= 0x8000:
        return raw - 0x10000
    if dtype == "uint16":
        return raw & 0xFFFF
    return raw


def _read_block(client, reg_def: RegisterDef, unit_id: int) -> Optional[List[int]]:
    if reg_def.reg_type == "input":
        result = client.read_input_registers(
            address=reg_def.address,
            count=reg_def.count,
            slave=unit_id,
        )
    else:
        result = client.read_holding_registers(
            address=reg_def.address,
            count=reg_def.count,
            slave=unit_id,
        )

    if result is None or getattr(result, "isError", lambda: True)():
        return None
    return list(result.registers)


class ModbusBMSReader:
    """Poll Modbus registers and populate BMSState."""

    DEFAULT_MAP = {
        "pack_voltage_v": {
            "address": 0,
            "type": "holding",
            "dtype": "uint16",
            "scale": 0.1,
        },
        "pack_current_a": {
            "address": 1,
            "type": "holding",
            "dtype": "int16",
            "scale": 0.1,
            "offset": 0.0,
        },
        "soc_pct": {
            "address": 2,
            "type": "holding",
            "dtype": "uint16",
            "scale": 1.0,
        },
        "soh_pct": {
            "address": 3,
            "type": "holding",
            "dtype": "uint16",
            "scale": 1.0,
        },
        "error_flags": {
            "address": 4,
            "type": "holding",
            "dtype": "uint16",
            "scale": 1.0,
        },
        "temps": {
            "address": 10,
            "type": "holding",
            "dtype": "int16",
            "scale": 0.1,
            "offset": 0.0,
            "count": 4,
        },
        "cell_voltages": {
            "address": 20,
            "type": "holding",
            "dtype": "uint16",
            "scale": 0.001,
            "count": 8,
        },
    }

    def __init__(
        self,
        mode: str = "tcp",
        host: str = "127.0.0.1",
        port: int = 502,
        unit_id: int = 1,
        serial_port: str = "/dev/ttyUSB0",
        baudrate: int = 9600,
        parity: str = "N",
        stopbits: int = 1,
        bytesize: int = 8,
        register_map: Optional[Dict[str, Dict[str, Any]]] = None,
        register_map_file: Optional[Union[str, Path]] = None,
    ):
        if ModbusTcpClient is None:
            raise ImportError("pymodbus is required: pip install pymodbus")

        self.mode = mode.lower()
        self.host = host
        self.port = port
        self.unit_id = unit_id
        self.serial_port = serial_port
        self.baudrate = baudrate
        self.parity = parity
        self.stopbits = stopbits
        self.bytesize = bytesize
        self.client = None
        self.connected = False
        self.poll_count = 0

        self.register_map = self._load_register_map(register_map, register_map_file)
        self.registers = {
            name: RegisterDef.from_dict(defn) for name, defn in self.register_map.items()
        }

    @classmethod
    def _load_register_map(
        cls,
        register_map: Optional[Dict[str, Dict[str, Any]]],
        register_map_file: Optional[Union[str, Path]],
    ) -> Dict[str, Dict[str, Any]]:
        if register_map is not None:
            return register_map

        if register_map_file:
            path = Path(register_map_file)
            with path.open(encoding="utf-8") as handle:
                data = json.load(handle)
            return data.get("registers", data)

        return cls.DEFAULT_MAP

    def connect(self) -> bool:
        try:
            if self.mode == "rtu":
                self.client = ModbusSerialClient(
                    port=self.serial_port,
                    baudrate=self.baudrate,
                    parity=self.parity,
                    stopbits=self.stopbits,
                    bytesize=self.bytesize,
                )
            else:
                self.client = ModbusTcpClient(host=self.host, port=self.port)

            self.connected = bool(self.client.connect())
            if self.connected:
                logger.info(
                    "Connected to Modbus %s (unit %d)",
                    f"RTU {self.serial_port}" if self.mode == "rtu" else f"TCP {self.host}:{self.port}",
                    self.unit_id,
                )
            return self.connected
        except Exception as exc:
            logger.error("Modbus connect failed: %s", exc)
            self.connected = False
            return False

    def disconnect(self) -> None:
        if self.client:
            self.client.close()
        self.client = None
        self.connected = False

    def _read_scalar(self, name: str) -> Optional[float]:
        reg_def = self.registers.get(name)
        if not reg_def:
            return None

        values = _read_block(self.client, reg_def, self.unit_id)
        if not values:
            logger.debug("No data for register %s @ %d", name, reg_def.address)
            return None

        raw = _decode_register(values[0], reg_def.dtype)
        return (raw * reg_def.scale) + reg_def.offset

    def _read_list(self, name: str) -> Optional[List[float]]:
        reg_def = self.registers.get(name)
        if not reg_def:
            return None

        values = _read_block(self.client, reg_def, self.unit_id)
        if not values:
            logger.debug("No data for register block %s @ %d", name, reg_def.address)
            return None

        result = []
        for raw in values:
            decoded = _decode_register(raw, reg_def.dtype)
            result.append((decoded * reg_def.scale) + reg_def.offset)
        return result

    def poll(self) -> Optional[BMSState]:
        """Read all configured registers and return updated BMS state."""
        if not self.connected or not self.client:
            return None

        try:
            state = BMSState()

            voltage = self._read_scalar("pack_voltage_v")
            if voltage is not None:
                state.voltage_v = voltage

            current = self._read_scalar("pack_current_a")
            if current is not None:
                state.current_a = current

            soc = self._read_scalar("soc_pct")
            if soc is not None:
                state.soc_pct = int(round(soc))

            soh = self._read_scalar("soh_pct")
            if soh is not None:
                state.soh_pct = int(round(soh))

            errors = self._read_scalar("error_flags")
            if errors is not None:
                state.error_flags = int(errors)

            temp = self._read_scalar("temperature_c")
            if temp is not None:
                state.temp_c = temp

            temps = self._read_list("temps")
            if temps:
                for i, value in enumerate(temps[:4]):
                    state.temps[i] = value

            cells = self._read_list("cell_voltages")
            if cells:
                for i, value in enumerate(cells):
                    if i < len(state.cell_voltages):
                        state.cell_voltages[i] = value

            state.update_status_temp()
            self.poll_count += 1

            if self.poll_count % 20 == 0:
                logger.info(
                    "Modbus poll %d | V=%.1fV I=%.1fA SOC=%d%%",
                    self.poll_count,
                    state.voltage_v,
                    state.current_a,
                    state.soc_pct,
                )

            return state

        except ModbusException as exc:
            logger.error("Modbus read error: %s", exc)
            return None
        except Exception as exc:
            logger.error("Unexpected Modbus error: %s", exc)
            return None