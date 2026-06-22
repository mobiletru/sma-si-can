"""
SMA SI 6048 - EVTV BMS Bridge (HAOS Add-on)
Direct PCAN access on NAS
- Read EVTV frames from CAN bus
- Publish to Home Assistant
- Listen for HA service calls
- Send SI control frames back to CAN bus
"""

import json
import logging
import time
import threading
from typing import Dict, Optional
from dataclasses import dataclass

import requests

# Try importing CAN libraries
try:
    from can_interface import (
        CANBusInterface,
        create_pcan_interface,
        create_socketcan_interface,
        create_virtual_interface,
    )
    from protocol import FrameID, decode_frame
except ImportError as e:
    logging.error(f"Failed to import can_interface: {e}")

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class EVTVState:
    """Current EVTV BMS state (decoded from EVTV ESP32 CAN broadcast)"""
    voltage_v: float = 0.0
    # Pack current is signed. Per the EVTV ESP32 spec (0x150) positive values
    # are charging and negative values are discharging.
    current_a: float = 0.0
    amp_hours: float = 0.0      # amp-hours used from pack (usually negative)
    soc_pct: float = 0.0
    soh_pct: int = 100          # not reported by EVTV; kept at default
    temp_c: float = 20.0        # max cell-terminal temperature
    temp_min_c: float = 20.0
    cell_high_v: float = 0.0
    cell_low_v: float = 0.0
    cell_avg_v: float = 0.0
    cell_voltages: list = None
    temps: list = None
    
    def __post_init__(self):
        if self.cell_voltages is None:
            self.cell_voltages = [0.0] * 48
        if self.temps is None:
            self.temps = [20.0] * 4


class EVTVReader:
    """Read EVTV ESP32 BMS frames from CAN.

    Frame layout follows the EVTV ESP32 BMS Controller spec (CAN 2.0A, 11-bit
    IDs, little-endian / LSB:MSB). Note the signed fields: pack current and
    pack amp-hours are 16-bit *signed* integers.
    """

    EVTV_STATUS = 0x150       # current(signed), voltage(x10), Ah(signed x10), max/min temp
    EVTV_SOC = 0x650          # SOC * 2 (single byte)
    EVTV_CELL_SUMMARY = 0x651  # low/high/avg cell voltage (x1000)
    EVTV_CELLS = 0x68F        # sequenced individual cell voltages

    def __init__(self, can_interface: CANBusInterface):
        self.can = can_interface
        self.state = EVTVState()
    
    def read_and_update(self, timeout: float = 0.1) -> bool:
        """Read frames and update state. Returns True if any frame received."""
        messages = self.can.receive_all(timeout=timeout)
        
        if not messages:
            return False
        
        for msg in messages:
            self._parse_frame(msg.frame_id, msg.data)
        
        return True
    
    def _parse_frame(self, frame_id: int, data: bytes) -> None:
        """Parse an EVTV ESP32 BMS frame and update state"""
        if frame_id == self.EVTV_STATUS and len(data) >= 8:
            # Byte 0/1: pack current, 16-bit SIGNED, amps (>0 charge, <0 discharge)
            self.state.current_a = float(int.from_bytes(data[0:2], 'little', signed=True))
            # Byte 2/3: pack voltage, 16-bit unsigned, x10
            self.state.voltage_v = int.from_bytes(data[2:4], 'little') / 10.0
            # Byte 4/5: pack amp-hours used, 16-bit SIGNED, x10 (usually negative)
            self.state.amp_hours = int.from_bytes(data[4:6], 'little', signed=True) / 10.0
            # Byte 6: max battery temp, Byte 7: min battery temp (whole deg C)
            self.state.temp_c = float(data[6])
            self.state.temp_min_c = float(data[7])
            self.state.temps = [float(data[6]), float(data[7])]
        
        elif frame_id == self.EVTV_SOC and len(data) >= 1:
            # Byte 0: SOC * 2 -> half-percent resolution
            self.state.soc_pct = data[0] / 2.0
        
        elif frame_id == self.EVTV_CELL_SUMMARY and len(data) >= 6:
            self.state.cell_low_v = int.from_bytes(data[0:2], 'little') / 1000.0
            self.state.cell_high_v = int.from_bytes(data[2:4], 'little') / 1000.0
            self.state.cell_avg_v = int.from_bytes(data[4:6], 'little') / 1000.0
        
        elif frame_id == self.EVTV_CELLS and len(data) >= 8:
            # Byte 0: sequence number, Byte 1: total 6-cell messages,
            # Bytes 2-7: six cell voltages encoded as (cellV - 2.00) * 100.
            seq = data[0]
            for i in range(6):
                idx = seq * 6 + i
                if 0 <= idx < len(self.state.cell_voltages):
                    self.state.cell_voltages[idx] = (data[2 + i] + 200) / 100.0


class SIFrameBuilder:
    """Build SMA SI CAN frames from EVTV data"""
    
    @staticmethod
    def status_frame(state: EVTVState) -> tuple:
        """0x351: Pack voltage, current, temp"""
        frame = bytearray(8)
        
        # Voltage: 0.01V/LSB
        voltage_raw = int(state.voltage_v / 0.01)
        frame[0:2] = voltage_raw.to_bytes(2, 'little')
        
        # Current: 0.1A/LSB, offset 3200A
        current_raw = int((state.current_a + 3200) / 0.1)
        frame[2:4] = current_raw.to_bytes(2, 'little', signed=True)
        
        # Temperature: 0.1°C/LSB, -40°C offset
        temp_raw = int((state.temp_c + 40) / 0.1)
        frame[4] = temp_raw & 0xFF
        
        return (0x351, bytes(frame))
    
    @staticmethod
    def state_frame(state: EVTVState) -> tuple:
        """0x35F: SOC, SOH"""
        frame = bytearray(8)
        frame[0] = int(state.soc_pct) & 0xFF
        frame[1] = int(state.soh_pct) & 0xFF
        return (0x35F, bytes(frame))
    
    @staticmethod
    def cell_voltages_frame(state: EVTVState) -> tuple:
        """0x355: Cell voltages 1-4"""
        frame = bytearray(8)
        
        for i in range(4):
            if i < len(state.cell_voltages):
                cell_raw = int(state.cell_voltages[i] / 0.001)
                
                if i == 0:
                    frame[0] = cell_raw & 0xFF
                    frame[1] = (cell_raw >> 8) & 0x07
                elif i == 1:
                    frame[1] |= (cell_raw & 0x0F) << 3
                    frame[2] = (cell_raw >> 4) & 0xFF
                elif i == 2:
                    frame[3] = cell_raw & 0xFF
                    frame[4] = (cell_raw >> 8) & 0x07
                elif i == 3:
                    frame[4] |= (cell_raw & 0x0F) << 3
                    frame[5] = (cell_raw >> 4) & 0xFF
        
        return (0x355, bytes(frame))
    
    @staticmethod
    def temps_frame(state: EVTVState) -> tuple:
        """0x35A: Temperatures"""
        frame = bytearray(8)
        
        for i in range(4):
            if i < len(state.temps):
                temp_raw = int((state.temps[i] + 40) / 0.1)
                frame[i] = temp_raw & 0xFF
        
        return (0x35A, bytes(frame))


class HABridge:
    """Publish to Home Assistant and listen for commands"""
    
    def __init__(self, ha_host: str = 'localhost', ha_port: int = 8123):
        self.ha_url = f"http://{ha_host}:{ha_port}"
        self.session = requests.Session()
        self.connected = False
    
    def test_connection(self) -> bool:
        """Test HA connection"""
        try:
            resp = self.session.get(f"{self.ha_url}/api/", timeout=5)
            self.connected = resp.status_code == 200
            if self.connected:
                logger.info(f"Connected to HA: {self.ha_url}")
            return self.connected
        except Exception as e:
            logger.error(f"HA connection failed: {e}")
            return False
    
    def publish_sensor(self, entity_id: str, value, unit: str = '') -> None:
        """Publish sensor state to HA"""
        if not self.connected:
            return
        
        try:
            payload = {
                'entity_id': f'sensor.sma_si_evtv_{entity_id}',
                'state': str(value),
                'attributes': {
                    'unit_of_measurement': unit,
                    'friendly_name': entity_id.replace('_', ' ').title(),
                    'timestamp': time.time(),
                }
            }
            
            self.session.post(
                f"{self.ha_url}/api/states/sensor.sma_si_evtv_{entity_id}",
                json=payload,
                timeout=5
            )
        except Exception as e:
            logger.debug(f"Publish failed: {e}")
    
    def publish_all(self, state: EVTVState) -> None:
        """Publish all EVTV state to HA"""
        self.publish_sensor('pack_voltage_v', round(state.voltage_v, 2), 'V')
        self.publish_sensor('pack_current_a', round(state.current_a, 1), 'A')
        self.publish_sensor('pack_ah', round(state.amp_hours, 1), 'Ah')
        self.publish_sensor('soc_pct', round(state.soc_pct, 1), '%')
        self.publish_sensor('soh_pct', state.soh_pct, '%')
        self.publish_sensor('temperature_c', round(state.temp_c, 1), '°C')
        self.publish_sensor('temp_max_c', round(state.temp_c, 1), '°C')
        self.publish_sensor('temp_min_c', round(state.temp_min_c, 1), '°C')
        self.publish_sensor('cell_high_v', round(state.cell_high_v, 3), 'V')
        self.publish_sensor('cell_low_v', round(state.cell_low_v, 3), 'V')
        self.publish_sensor('cell_avg_v', round(state.cell_avg_v, 3), 'V')
        
        for i, cell_v in enumerate(state.cell_voltages[:4], 1):
            self.publish_sensor(f'cell_{i}_v', round(cell_v, 3), 'V')
        
        for i, temp in enumerate(state.temps, 1):
            self.publish_sensor(f'temp_{i}_c', round(temp, 1), '°C')


class SIController:
    """Send SI control frames to CAN bus"""
    
    def __init__(self, can_interface: CANBusInterface):
        self.can = can_interface
        self.builder = SIFrameBuilder()
    
    def send_state_frames(self, state: EVTVState) -> None:
        """Send SI protocol frames for EVTV state"""
        try:
            # Send all frames periodically
            frame_id, data = self.builder.status_frame(state)
            self.can.send(frame_id, data)
            
            frame_id, data = self.builder.state_frame(state)
            self.can.send(frame_id, data)
            
            frame_id, data = self.builder.cell_voltages_frame(state)
            self.can.send(frame_id, data)
            
            frame_id, data = self.builder.temps_frame(state)
            self.can.send(frame_id, data)
        
        except Exception as e:
            logger.error(f"Send frames failed: {e}")
    
    def send_raw(self, frame_id: int, data: bytes) -> bool:
        """Send raw CAN frame"""
        try:
            self.can.send(frame_id, data)
            logger.info(f"Sent 0x{frame_id:03X}: {data.hex()}")
            return True
        except Exception as e:
            logger.error(f"Send failed: {e}")
            return False


class EVTVtoSIBridge:
    """Main bridge: read EVTV, publish HA, send SI frames"""
    
    def __init__(self, can_interface: CANBusInterface, 
                 ha_host: str = 'localhost', ha_port: int = 8123):
        self.reader = EVTVReader(can_interface)
        self.bridge = HABridge(ha_host, ha_port)
        self.controller = SIController(can_interface)
        
        self.frame_count = 0
        self.send_interval = 0.05  # 50ms
        self.last_send = 0
    
    def run(self) -> None:
        """Main loop"""
        logger.info("Starting EVTV→SI 6048 Bridge")
        
        if not self.bridge.test_connection():
            logger.error("Failed to connect to HA")
            return
        
        try:
            while True:
                # Read EVTV frames
                if self.reader.read_and_update(timeout=0.05):
                    self.frame_count += 1
                
                # Publish to HA every 100ms
                now = time.time()
                if now - self.last_send >= self.send_interval:
                    self.bridge.publish_all(self.reader.state)
                    self.controller.send_state_frames(self.reader.state)
                    self.last_send = now
                
                if self.frame_count % 100 == 0:
                    logger.info(
                        f"Processed {self.frame_count} frames | "
                        f"V={self.reader.state.voltage_v:.1f}V "
                        f"SOC={self.reader.state.soc_pct}%"
                    )
        
        except KeyboardInterrupt:
            logger.info("Stopped")
        except Exception as e:
            logger.error(f"Bridge error: {e}")


def main():
    import argparse
    import os
    
    parser = argparse.ArgumentParser('EVTV→SI 6048 Bridge (HAOS)')
    parser.add_argument('--can-interface',
                        default=os.getenv('CAN_INTERFACE', 'socketcan'),
                        choices=['socketcan', 'pcan', 'virtual'],
                        help='CAN backend. On HAOS PCAN-USB appears as SocketCAN (can0).')
    parser.add_argument('--can-channel', default=os.getenv('CAN_CHANNEL', 'can0'))
    parser.add_argument('--ha-host', default=os.getenv('HA_HOST', 'localhost'))
    parser.add_argument('--ha-port', type=int, default=int(os.getenv('HA_PORT', '8123')))
    parser.add_argument('--log-level', default=os.getenv('LOG_LEVEL', 'INFO').upper())
    
    args = parser.parse_args()
    logging.getLogger().setLevel(getattr(logging, args.log_level))
    
    logger.info(f"Connecting to CAN: {args.can_interface}:{args.can_channel}")
    if args.can_interface == 'pcan':
        can = create_pcan_interface(channel=args.can_channel)
    elif args.can_interface == 'virtual':
        can = create_virtual_interface(channel=args.can_channel)
    else:
        can = create_socketcan_interface(channel=args.can_channel)
    
    if not can.connect():
        logger.error(f"CAN connect failed ({args.can_interface}:{args.can_channel})")
        return 1
    
    logger.info(f"Connected to CAN ({args.can_interface}:{args.can_channel})")
    
    bridge = EVTVtoSIBridge(
        can,
        ha_host=args.ha_host,
        ha_port=args.ha_port
    )
    
    bridge.run()
    can.disconnect()
    
    return 0


if __name__ == '__main__':
    exit(main())
