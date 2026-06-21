"""
PCAN Reader: EVTV BMS → SMA Sunny Island CAN Protocol
Reads EVTV BMS frames, converts to SI Li-Ion external BMS format, sends back on CAN
"""

import logging
import time
from typing import Dict, Optional
from dataclasses import dataclass

from can_interface import CANBusInterface, create_pcan_interface
from protocol import (
    StatusFrame, StateFrame, CellVoltagesFrame1, CellVoltagesFrame2,
    TemperatureFrame, encode_frame, FrameID
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class EVTVBMSData:
    """Parsed EVTV BMS state"""
    voltage_v: float = 0.0
    current_a: float = 0.0
    soc_pct: int = 0
    soh_pct: int = 100
    temp_c: float = 20.0
    cell_voltages: list = None  # [v1, v2, v3, v4, ...]
    temps: list = None  # [t1, t2, t3, t4]
    error_flags: int = 0
    
    def __post_init__(self):
        if self.cell_voltages is None:
            self.cell_voltages = [0.0] * 48  # 48-cell SI pack
        if self.temps is None:
            self.temps = [20.0] * 4


class EVTVBMSReader:
    """Read EVTV BMS frames from PCAN"""
    
    # EVTV BMS uses standard Tesla BMS CAN IDs (11-bit)
    # Common IDs on EVTV systems:
    EVTV_VOLTAGE = 0x100  # Pack voltage (example, adjust based on your setup)
    EVTV_CURRENT = 0x101  # Pack current
    EVTV_STATE = 0x102    # SOC/SOH
    EVTV_CELLS_1 = 0x103  # Cell voltages 1-8
    EVTV_CELLS_2 = 0x104  # Cell voltages 9-16
    EVTV_TEMPS = 0x105    # Temperatures
    
    def __init__(self, can_interface: CANBusInterface):
        self.can = can_interface
        self.bms_data = EVTVBMSData()
        self.last_update = 0
    
    def read_frames(self, timeout: float = 0.1) -> None:
        """Read and parse EVTV BMS frames"""
        messages = self.can.receive_all(timeout=timeout)
        
        for msg in messages:
            if msg.frame_id == self.EVTV_VOLTAGE:
                self._parse_voltage(msg.data)
            elif msg.frame_id == self.EVTV_CURRENT:
                self._parse_current(msg.data)
            elif msg.frame_id == self.EVTV_STATE:
                self._parse_state(msg.data)
            elif msg.frame_id == self.EVTV_CELLS_1:
                self._parse_cells_1(msg.data)
            elif msg.frame_id == self.EVTV_CELLS_2:
                self._parse_cells_2(msg.data)
            elif msg.frame_id == self.EVTV_TEMPS:
                self._parse_temps(msg.data)
    
    def _parse_voltage(self, data: bytes) -> None:
        """Parse pack voltage (example: 2 bytes, 0.01V LSB)"""
        if len(data) >= 2:
            raw = int.from_bytes(data[0:2], 'little', signed=False)
            self.bms_data.voltage_v = raw * 0.01
            logger.debug(f"Voltage: {self.bms_data.voltage_v:.2f}V")
    
    def _parse_current(self, data: bytes) -> None:
        """Parse pack current (example: 2 bytes, 0.1A LSB, offset 3200A)"""
        if len(data) >= 2:
            raw = int.from_bytes(data[0:2], 'little', signed=True)
            self.bms_data.current_a = (raw * 0.1) - 3200
            logger.debug(f"Current: {self.bms_data.current_a:.1f}A")
    
    def _parse_state(self, data: bytes) -> None:
        """Parse SOC/SOH"""
        if len(data) >= 2:
            self.bms_data.soc_pct = data[0]
            self.bms_data.soh_pct = data[1]
            logger.debug(f"SOC: {self.bms_data.soc_pct}% SOH: {self.bms_data.soh_pct}%")
    
    def _parse_cells_1(self, data: bytes) -> None:
        """Parse cell voltages 1-8 (2 bytes each, 0.001V LSB)"""
        for i in range(8):
            offset = i * 2
            if offset + 1 < len(data):
                raw = int.from_bytes(data[offset:offset+2], 'little', signed=False)
                voltage = raw * 0.001
                if i < len(self.bms_data.cell_voltages):
                    self.bms_data.cell_voltages[i] = voltage
    
    def _parse_cells_2(self, data: bytes) -> None:
        """Parse cell voltages 9-16"""
        for i in range(8):
            offset = i * 2
            if offset + 1 < len(data):
                raw = int.from_bytes(data[offset:offset+2], 'little', signed=False)
                voltage = raw * 0.001
                cell_idx = 8 + i
                if cell_idx < len(self.bms_data.cell_voltages):
                    self.bms_data.cell_voltages[cell_idx] = voltage
    
    def _parse_temps(self, data: bytes) -> None:
        """Parse temperatures (4 sensors, 1 byte each, 0.1°C LSB, -40°C offset)"""
        for i in range(4):
            if i < len(data):
                raw = data[i]
                temp = (raw * 0.1) - 40
                self.bms_data.temps[i] = temp
                logger.debug(f"Temp {i+1}: {temp:.1f}°C")


class SIProtocolEncoder:
    """Encode SMA Sunny Island CAN frames from EVTV BMS data"""
    
    @staticmethod
    def encode_status(bms_data: EVTVBMSData) -> bytes:
        """
        0x351: Pack voltage, current, temp, error flags
        [0-1] voltage (0.01V/LSB)
        [2-3] current (0.1A/LSB, offset 3200A)
        [4] temperature (-40°C offset, 0.1°C/LSB)
        [5] error flags
        [6-7] reserved
        """
        frame = bytearray(8)
        
        # Voltage: 0.01V/LSB
        voltage_raw = int(bms_data.voltage_v / 0.01)
        frame[0:2] = voltage_raw.to_bytes(2, 'little', signed=False)
        
        # Current: 0.1A/LSB, offset 3200A
        current_raw = int((bms_data.current_a + 3200) / 0.1)
        frame[2:4] = current_raw.to_bytes(2, 'little', signed=True)
        
        # Temperature: 0.1°C/LSB, -40°C offset
        temp_raw = int((bms_data.temp_c + 40) / 0.1)
        frame[4] = temp_raw & 0xFF
        
        # Error flags
        frame[5] = bms_data.error_flags & 0xFF
        
        return bytes(frame)
    
    @staticmethod
    def encode_state(bms_data: EVTVBMSData) -> bytes:
        """
        0x35F: SOC, SOH, error code
        [0] SOC (1%/LSB)
        [1] SOH (1%/LSB)
        [2-3] error code
        [4-7] reserved
        """
        frame = bytearray(8)
        frame[0] = bms_data.soc_pct & 0xFF
        frame[1] = bms_data.soh_pct & 0xFF
        # Error code at [2:4] (if needed)
        return bytes(frame)
    
    @staticmethod
    def encode_cell_voltages_1(bms_data: EVTVBMSData) -> bytes:
        """
        0x355: Cell voltages 1-4
        Each cell: 11-bit value, 0.001V/LSB
        """
        frame = bytearray(8)
        
        for i in range(4):
            if i < len(bms_data.cell_voltages):
                # 11-bit value (0-2047 → 0-2.047V)
                cell_v = bms_data.cell_voltages[i]
                cell_raw = int(cell_v / 0.001)
                
                # Pack into bytes (3 cells = 11 bits each in first 4.125 bytes)
                if i == 0:
                    frame[0] = (cell_raw & 0xFF)
                    frame[1] = ((cell_raw >> 8) & 0x07)
                elif i == 1:
                    frame[1] |= ((cell_raw & 0x0F) << 3)
                    frame[2] = ((cell_raw >> 4) & 0xFF)
                elif i == 2:
                    frame[3] = (cell_raw & 0xFF)
                    frame[4] = ((cell_raw >> 8) & 0x07)
                elif i == 3:
                    frame[4] |= ((cell_raw & 0x0F) << 3)
                    frame[5] = ((cell_raw >> 4) & 0xFF)
        
        return bytes(frame)
    
    @staticmethod
    def encode_temps(bms_data: EVTVBMSData) -> bytes:
        """
        0x35A: Temperature sensors 1-4
        Each temp: 8-bit, 0.1°C/LSB, -40°C offset
        """
        frame = bytearray(8)
        
        for i in range(4):
            if i < len(bms_data.temps):
                temp = bms_data.temps[i]
                temp_raw = int((temp + 40) / 0.1)
                frame[i] = temp_raw & 0xFF
        
        return bytes(frame)


class EVTVtoSIBridge:
    """Convert EVTV BMS → SI CAN protocol"""
    
    def __init__(self, can_interface: CANBusInterface):
        self.can = can_interface
        self.reader = EVTVBMSReader(can_interface)
        self.encoder = SIProtocolEncoder()
        self.frame_count = 0
        self.send_interval = 0.05  # 50ms (20 Hz)
        self.last_send = 0
    
    def process(self) -> None:
        """Read EVTV frames, convert, send SI protocol"""
        # Read incoming EVTV frames
        self.reader.read_frames(timeout=0.05)
        
        # Send SI frames periodically
        now = time.time()
        if now - self.last_send >= self.send_interval:
            self._send_si_frames()
            self.last_send = now
    
    def _send_si_frames(self) -> None:
        """Encode and send all SI protocol frames"""
        try:
            # 0x351 STATUS
            status_data = self.encoder.encode_status(self.reader.bms_data)
            self.can.send(0x351, status_data)
            
            # 0x35F STATE
            state_data = self.encoder.encode_state(self.reader.bms_data)
            self.can.send(0x35F, state_data)
            
            # 0x355 CELL_VOLTAGES_1
            cells_data = self.encoder.encode_cell_voltages_1(self.reader.bms_data)
            self.can.send(0x355, cells_data)
            
            # 0x35A TEMPS
            temps_data = self.encoder.encode_temps(self.reader.bms_data)
            self.can.send(0x35A, temps_data)
            
            self.frame_count += 4
            
            if self.frame_count % 100 == 0:
                logger.info(
                    f"Sent {self.frame_count} frames | "
                    f"V: {self.reader.bms_data.voltage_v:.1f}V "
                    f"I: {self.reader.bms_data.current_a:.1f}A "
                    f"SOC: {self.reader.bms_data.soc_pct}% "
                    f"T: {self.reader.bms_data.temps[0]:.1f}°C"
                )
        
        except Exception as e:
            logger.error(f"Send error: {e}")
    
    def run(self) -> None:
        """Main loop"""
        logger.info("Starting EVTV→SI converter")
        logger.info("Reading EVTV BMS frames, sending SI protocol frames")
        
        try:
            while True:
                self.process()
                time.sleep(0.01)  # 100 Hz polling
        
        except KeyboardInterrupt:
            logger.info("Stopped")
        except Exception as e:
            logger.error(f"Bridge error: {e}")
        finally:
            self.can.disconnect()


def main():
    """Run converter"""
    import argparse
    import os
    
    parser = argparse.ArgumentParser(
        description='EVTV BMS → SMA SI CAN Protocol Converter'
    )
    parser.add_argument('--can-channel',
                       default=os.getenv('CAN_CHANNEL', 'PCAN_USBCH1'),
                       help='PCAN channel')
    parser.add_argument('--log-level',
                       default=os.getenv('LOG_LEVEL', 'INFO').upper(),
                       choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'])
    
    args = parser.parse_args()
    logging.getLogger().setLevel(getattr(logging, args.log_level))
    
    # Connect PCAN
    logger.info(f"Connecting to PCAN: {args.can_channel}")
    can = create_pcan_interface(channel=args.can_channel)
    
    if not can.connect():
        logger.error("PCAN connect failed")
        return 1
    
    logger.info("Connected to PCAN, starting converter")
    
    bridge = EVTVtoSIBridge(can)
    bridge.run()
    
    return 0


if __name__ == '__main__':
    exit(main())
