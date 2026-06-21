"""Shared BMS state used by Modbus and CAN converters."""

from dataclasses import dataclass, field
from typing import List


@dataclass
class BMSState:
    """Battery management system readings for SMA SI CAN encoding."""

    voltage_v: float = 0.0
    current_a: float = 0.0
    soc_pct: int = 0
    soh_pct: int = 100
    temp_c: float = 20.0
    cell_voltages: List[float] = field(default_factory=lambda: [0.0] * 48)
    temps: List[float] = field(default_factory=lambda: [20.0] * 4)
    error_flags: int = 0

    def update_status_temp(self) -> None:
        """Use the first valid temperature sensor for the status frame."""
        for temp in self.temps:
            if temp != 0.0:
                self.temp_c = temp
                return