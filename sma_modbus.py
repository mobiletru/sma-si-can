"""SMA Sunny Island Modbus read/write helpers (WebBox profile)."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

logger = logging.getLogger(__name__)

try:
    from pymodbus.client import ModbusSerialClient, ModbusTcpClient
    from pymodbus.exceptions import ModbusException
except ImportError:
    ModbusSerialClient = None
    ModbusTcpClient = None
    ModbusException = Exception


FORMAT_SCALE = {
    "FIX0": 1.0,
    "FIX1": 0.1,
    "FIX2": 0.01,
    "FIX3": 0.001,
}


def decode_u32(words: List[int]) -> int:
    return ((words[0] & 0xFFFF) << 16) | (words[1] & 0xFFFF)


def decode_s32(words: List[int]) -> int:
    value = decode_u32(words)
    if value >= 0x80000000:
        value -= 0x100000000
    return value


def encode_u32(value: int) -> List[int]:
    value &= 0xFFFFFFFF
    return [(value >> 16) & 0xFFFF, value & 0xFFFF]


def encode_s32(value: int) -> List[int]:
    if value < 0:
        value = (1 << 32) + value
    return encode_u32(value)


def apply_format(raw: int, fmt: str) -> float:
    scale = FORMAT_SCALE.get(fmt, 1.0)
    return raw * scale


def unapply_format(value: float, fmt: str) -> int:
    scale = FORMAT_SCALE.get(fmt, 1.0)
    return int(round(value / scale))


@dataclass
class SMARegister:
    name: str
    address: int
    count: int = 2
    dtype: str = "U32"
    format: str = "FIX0"
    access: str = "RO"
    description: str = ""

    @classmethod
    def from_dict(cls, name: str, data: Dict[str, Any]) -> "SMARegister":
        return cls(
            name=name,
            address=int(data["address"]),
            count=int(data.get("count", 2 if data.get("dtype", "U32") in {"U32", "S32"} else 1)),
            dtype=data.get("dtype", "U32"),
            format=data.get("format", "FIX0"),
            access=data.get("access", "RO"),
            description=data.get("description", ""),
        )

    @property
    def writable(self) -> bool:
        return self.access.upper() == "RW"


class SMAModbusClient:
    """Read and write SMA Modbus registers using the WebBox profile."""

    def __init__(
        self,
        mode: str = "tcp",
        host: str = "127.0.0.1",
        port: int = 502,
        unit_id: int = 3,
        serial_port: str = "/dev/ttyUSB0",
        baudrate: int = 9600,
        parity: str = "N",
        stopbits: int = 1,
        bytesize: int = 8,
        register_map_file: Optional[Union[str, Path]] = None,
        register_map: Optional[Dict[str, Dict[str, Any]]] = None,
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

        raw_map = register_map or self._load_map(register_map_file)
        self.registers = {
            name: SMARegister.from_dict(name, data) for name, data in raw_map.items()
        }

    @staticmethod
    def _load_map(path: Optional[Union[str, Path]]) -> Dict[str, Dict[str, Any]]:
        if not path:
            raise ValueError("register_map_file is required")
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return data.get("registers", data)

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
                    "Connected to SMA Modbus %s unit=%d",
                    f"RTU {self.serial_port}" if self.mode == "rtu" else f"TCP {self.host}:{self.port}",
                    self.unit_id,
                )
            return self.connected
        except Exception as exc:
            logger.error("SMA Modbus connect failed: %s", exc)
            self.connected = False
            return False

    def disconnect(self) -> None:
        if self.client:
            self.client.close()
        self.client = None
        self.connected = False

    def _unit_param(self) -> dict:
        """pymodbus 3.x uses device_id; older versions used slave."""
        return {"device_id": self.unit_id}

    def _read_words(self, reg: SMARegister) -> Optional[List[int]]:
        if not self.client:
            return None
        kwargs = dict(
            address=reg.address,
            count=reg.count,
            **self._unit_param(),
        )
        try:
            result = self.client.read_holding_registers(**kwargs)
        except TypeError:
            kwargs.pop("device_id", None)
            kwargs["slave"] = self.unit_id
            result = self.client.read_holding_registers(**kwargs)
        if result is None or getattr(result, "isError", lambda: True)():
            return None
        return list(result.registers)

    def _write_words(self, reg: SMARegister, words: List[int]) -> bool:
        if not reg.writable:
            logger.error("Register %s is read-only", reg.name)
            return False
        if not self.client:
            return False
        unit = self._unit_param()
        if len(words) == 1:
            try:
                result = self.client.write_register(
                    address=reg.address,
                    value=words[0],
                    **unit,
                )
            except TypeError:
                result = self.client.write_register(
                    address=reg.address,
                    value=words[0],
                    slave=self.unit_id,
                )
        else:
            try:
                result = self.client.write_registers(
                    address=reg.address,
                    values=words,
                    **unit,
                )
            except TypeError:
                result = self.client.write_registers(
                    address=reg.address,
                    values=words,
                    slave=self.unit_id,
                )
        ok = result is not None and not getattr(result, "isError", lambda: True)()
        if not ok:
            logger.error("Write failed for %s @ %d", reg.name, reg.address)
        return ok

    def decode_words(self, reg: SMARegister, words: List[int]) -> Union[int, float]:
        if reg.dtype == "U16":
            raw = words[0] & 0xFFFF
        elif reg.dtype == "S16":
            raw = words[0]
            if raw >= 0x8000:
                raw -= 0x10000
        elif reg.dtype == "S32":
            raw = decode_s32(words)
        else:
            raw = decode_u32(words)

        if reg.format in FORMAT_SCALE and reg.dtype in {"U32", "S32", "U16", "S16"}:
            return apply_format(raw, reg.format)
        return raw

    def encode_value(self, reg: SMARegister, value: Union[int, float]) -> List[int]:
        if reg.format in FORMAT_SCALE and isinstance(value, float):
            raw = unapply_format(value, reg.format)
        else:
            raw = int(value)

        if reg.dtype == "U16":
            return [raw & 0xFFFF]
        if reg.dtype == "S16":
            return [raw & 0xFFFF]
        if reg.dtype == "S32":
            return encode_s32(raw)
        return encode_u32(raw)

    def read(self, name: str) -> Optional[Union[int, float]]:
        reg = self.registers.get(name)
        if not reg:
            logger.error("Unknown register: %s", name)
            return None
        words = self._read_words(reg)
        if not words:
            logger.debug("No data for %s @ %d", name, reg.address)
            return None
        return self.decode_words(reg, words)

    def write(self, name: str, value: Union[int, float]) -> bool:
        reg = self.registers.get(name)
        if not reg:
            logger.error("Unknown register: %s", name)
            return False
        words = self.encode_value(reg, value)
        ok = self._write_words(reg, words)
        if ok:
            logger.info("Wrote %s=%s to address %d", name, value, reg.address)
        return ok

    def read_many(self, names: Optional[List[str]] = None) -> Dict[str, Union[int, float]]:
        targets = names or list(self.registers.keys())
        values: Dict[str, Union[int, float]] = {}
        for name in targets:
            value = self.read(name)
            if value is not None:
                values[name] = value
        return values

    def write_many(self, values: Dict[str, Union[int, float]]) -> Dict[str, bool]:
        results: Dict[str, bool] = {}
        for name, value in values.items():
            results[name] = self.write(name, value)
        return results
