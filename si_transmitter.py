"""Encode BMS state as SMA Sunny Island CAN frames and transmit on PCAN."""

import logging
import time
from typing import Optional

from bms_state import BMSState
from can_interface import CANBusInterface
from protocol import (
    CellVoltagesFrame1,
    CellVoltagesFrame2,
    FrameID,
    StateFrame,
    StatusFrame,
    TemperatureFrame,
)

logger = logging.getLogger(__name__)


class SITransmitter:
    """Send SMA Li-Ion external BMS CAN frames from BMS state."""

    def __init__(self, can_interface: CANBusInterface, send_interval: float = 0.05):
        self.can = can_interface
        self.send_interval = send_interval
        self.last_send = 0.0
        self.frame_count = 0

    def should_send(self) -> bool:
        return (time.time() - self.last_send) >= self.send_interval

    def send_all(self, state: BMSState) -> int:
        """Encode and send all required SI protocol frames. Returns frames sent."""
        state.update_status_temp()
        sent = 0

        if self.can.send(
            FrameID.STATUS,
            StatusFrame.pack(
                pack_voltage_v=state.voltage_v,
                pack_current_a=state.current_a,
                temp_c=state.temp_c,
                error_flags=state.error_flags,
            ),
        ):
            sent += 1

        if self.can.send(
            FrameID.STATE,
            StateFrame.pack(
                soc_pct=state.soc_pct,
                soh_pct=state.soh_pct,
            ),
        ):
            sent += 1

        cells_1 = tuple(state.cell_voltages[0:4])
        if self.can.send(FrameID.CELL_VOLTAGES_1, CellVoltagesFrame1.pack(cells_1)):
            sent += 1

        cells_2 = tuple(state.cell_voltages[4:8])
        if self.can.send(FrameID.CELL_VOLTAGES_2, CellVoltagesFrame2.pack(cells_2)):
            sent += 1

        temps = tuple(state.temps[0:4])
        if self.can.send(FrameID.TEMPS, TemperatureFrame.pack(temps)):
            sent += 1

        self.frame_count += sent
        self.last_send = time.time()

        if self.frame_count % 100 == 0:
            logger.info(
                "Sent %d CAN frames | V=%.1fV I=%.1fA SOC=%d%% T=%.1fC",
                self.frame_count,
                state.voltage_v,
                state.current_a,
                state.soc_pct,
                state.temp_c,
            )

        return sent