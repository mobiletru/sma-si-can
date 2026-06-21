"""
SMA SI CAN - EVTV Converter (HAOS Add-on)
Connects to relay server on VM, converts EVTV frames to SI protocol, publishes to HA
"""

import json
import logging
import socket
import time
from typing import Dict, Optional
import requests
from dataclasses import dataclass

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class EVTVData:
    """Parsed EVTV BMS state"""
    voltage_v: float = 0.0
    current_a: float = 0.0
    soc_pct: int = 0
    soh_pct: int = 100
    temp_c: float = 20.0
    cell_voltages: list = None
    temps: list = None
    error_flags: int = 0
    
    def __post_init__(self):
        if self.cell_voltages is None:
            self.cell_voltages = [0.0] * 48
        if self.temps is None:
            self.temps = [20.0] * 4


class RelayClient:
    """Connect to VM relay server, receive EVTV frames"""
    
    def __init__(self, relay_host: str, relay_port: int = 9001):
        self.relay_host = relay_host
        self.relay_port = relay_port
        self.socket: Optional[socket.socket] = None
        self.connected = False
    
    def connect(self) -> bool:
        """Connect to relay server"""
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.connect((self.relay_host, self.relay_port))
            self.socket.settimeout(5.0)
            self.connected = True
            logger.info(f"Connected to relay: {self.relay_host}:{self.relay_port}")
            return True
        except Exception as e:
            logger.error(f"Relay connect failed: {e}")
            return False
    
    def receive_frame(self) -> Optional[Dict]:
        """Receive frame from relay (blocking)"""
        if not self.connected:
            return None
        
        try:
            data = b''
            while b'\n' not in data:
                chunk = self.socket.recv(1024)
                if not chunk:
                    self.connected = False
                    return None
                data += chunk
            
            frame_json = data.split(b'\n')[0].decode('utf-8')
            return json.loads(frame_json)
        except Exception as e:
            logger.debug(f"Receive error: {e}")
            self.connected = False
            return None
    
    def disconnect(self) -> None:
        if self.socket:
            try:
                self.socket.close()
            except:
                pass
            self.connected = False


class EVTVParser:
    """Parse raw EVTV BMS frame data"""
    
    # Frame ID mapping
    EVTV_VOLTAGE = 0x100
    EVTV_CURRENT = 0x101
    EVTV_STATE = 0x102
    EVTV_CELLS_1 = 0x103
    EVTV_CELLS_2 = 0x104
    EVTV_TEMPS = 0x105
    
    def __init__(self):
        self.data = EVTVData()
    
    def parse_frame(self, frame_id: int, frame_data: bytes) -> None:
        """Parse frame and update internal state"""
        if frame_id == self.EVTV_VOLTAGE:
            self._parse_voltage(frame_data)
        elif frame_id == self.EVTV_CURRENT:
            self._parse_current(frame_data)
        elif frame_id == self.EVTV_STATE:
            self._parse_state(frame_data)
        elif frame_id == self.EVTV_CELLS_1:
            self._parse_cells_1(frame_data)
        elif frame_id == self.EVTV_CELLS_2:
            self._parse_cells_2(frame_data)
        elif frame_id == self.EVTV_TEMPS:
            self._parse_temps(frame_data)
    
    def _parse_voltage(self, data: bytes) -> None:
        if len(data) >= 2:
            raw = int.from_bytes(data[0:2], 'little', signed=False)
            self.data.voltage_v = raw * 0.01
    
    def _parse_current(self, data: bytes) -> None:
        if len(data) >= 2:
            raw = int.from_bytes(data[0:2], 'little', signed=True)
            self.data.current_a = (raw * 0.1) - 3200
    
    def _parse_state(self, data: bytes) -> None:
        if len(data) >= 2:
            self.data.soc_pct = data[0]
            self.data.soh_pct = data[1]
    
    def _parse_cells_1(self, data: bytes) -> None:
        for i in range(8):
            offset = i * 2
            if offset + 1 < len(data):
                raw = int.from_bytes(data[offset:offset+2], 'little', signed=False)
                self.data.cell_voltages[i] = raw * 0.001
    
    def _parse_cells_2(self, data: bytes) -> None:
        for i in range(8):
            offset = i * 2
            if offset + 1 < len(data):
                raw = int.from_bytes(data[offset:offset+2], 'little', signed=False)
                self.data.cell_voltages[8 + i] = raw * 0.001
    
    def _parse_temps(self, data: bytes) -> None:
        for i in range(4):
            if i < len(data):
                raw = data[i]
                self.data.temps[i] = (raw * 0.1) - 40


class SIEncoder:
    """Encode SMA SI CAN frames from EVTV data"""
    
    @staticmethod
    def encode_status(data: EVTVData) -> Dict:
        """Frame 0x351: voltage, current, temp, error"""
        return {
            'frame_id': '0x351',
            'pack_voltage_v': round(data.voltage_v, 2),
            'pack_current_a': round(data.current_a, 1),
            'temperature_c': round(data.temp_c, 1),
            'error_flags': data.error_flags
        }
    
    @staticmethod
    def encode_state(data: EVTVData) -> Dict:
        """Frame 0x35F: SOC, SOH"""
        return {
            'frame_id': '0x35F',
            'soc_pct': data.soc_pct,
            'soh_pct': data.soh_pct
        }
    
    @staticmethod
    def encode_cells(data: EVTVData) -> Dict:
        """Frame 0x355/0x356: cell voltages"""
        return {
            'frame_id': '0x355/0x356',
            'cell_1_v': round(data.cell_voltages[0], 3),
            'cell_2_v': round(data.cell_voltages[1], 3),
            'cell_3_v': round(data.cell_voltages[2], 3),
            'cell_4_v': round(data.cell_voltages[3], 3),
        }
    
    @staticmethod
    def encode_temps(data: EVTVData) -> Dict:
        """Frame 0x35A: temperatures"""
        return {
            'frame_id': '0x35A',
            'temp_1_c': round(data.temps[0], 1),
            'temp_2_c': round(data.temps[1], 1),
            'temp_3_c': round(data.temps[2], 1),
            'temp_4_c': round(data.temps[3], 1),
        }


class HAPublisher:
    """Publish converted data to Home Assistant REST API"""
    
    def __init__(self, ha_host: str, ha_port: int = 8123):
        self.ha_host = ha_host
        self.ha_port = ha_port
        self.ha_url = f"http://{ha_host}:{ha_port}"
        self.session = requests.Session()
        self.connected = False
    
    def connect(self) -> bool:
        """Test HA connection"""
        try:
            resp = self.session.get(f"{self.ha_url}/api/", timeout=5)
            if resp.status_code == 200:
                self.connected = True
                logger.info(f"Connected to HA: {self.ha_host}:{self.ha_port}")
                return True
        except Exception as e:
            logger.error(f"HA connect failed: {e}")
        return False
    
    def publish(self, entity_id: str, value, unit: str = '') -> None:
        """Publish state to HA"""
        if not self.connected:
            return
        
        try:
            payload = {
                'entity_id': f'sensor.sma_si_evtv_{entity_id}',
                'state': str(value),
                'attributes': {
                    'unit_of_measurement': unit,
                    'last_updated': time.time(),
                }
            }
            
            self.session.post(
                f"{self.ha_url}/api/states/sensor.sma_si_evtv_{entity_id}",
                json=payload,
                timeout=5
            )
        except Exception as e:
            logger.debug(f"Publish error: {e}")


class EVTVtoSIConverter:
    """Main converter: relay → parse → encode → publish"""
    
    def __init__(self, relay_host: str, relay_port: int,
                 ha_host: str, ha_port: int):
        self.relay = RelayClient(relay_host, relay_port)
        self.parser = EVTVParser()
        self.encoder = SIEncoder()
        self.publisher = HAPublisher(ha_host, ha_port)
        self.frame_count = 0
    
    def run(self) -> None:
        """Main loop"""
        logger.info("Starting EVTV→SI converter")
        
        # Connect relay
        if not self.relay.connect():
            logger.error("Failed to connect to relay")
            return
        
        # Connect HA
        if not self.publisher.connect():
            logger.error("Failed to connect to HA")
            self.relay.disconnect()
            return
        
        logger.info("Converter ready, processing frames...")
        
        try:
            while True:
                frame = self.relay.receive_frame()
                
                if not frame:
                    if not self.relay.connected:
                        logger.warning("Relay disconnected, reconnecting...")
                        time.sleep(2)
                        if self.relay.connect():
                            logger.info("Relay reconnected")
                        continue
                    continue
                
                # Parse frame
                frame_id = frame.get('frame_id_int', 0)
                data_bytes = bytes(frame.get('data_bytes', []))
                
                self.parser.parse_frame(frame_id, data_bytes)
                self.frame_count += 1
                
                # Publish all converted states
                self._publish_all()
                
                if self.frame_count % 50 == 0:
                    logger.info(
                        f"Processed {self.frame_count} frames | "
                        f"V={self.parser.data.voltage_v:.1f}V "
                        f"I={self.parser.data.current_a:.1f}A "
                        f"SOC={self.parser.data.soc_pct}%"
                    )
        
        except KeyboardInterrupt:
            logger.info("Stopped")
        except Exception as e:
            logger.error(f"Converter error: {e}")
        finally:
            self.relay.disconnect()
    
    def _publish_all(self) -> None:
        """Publish all converted SI frames"""
        # Status
        status = self.encoder.encode_status(self.parser.data)
        for k, v in status.items():
            if k != 'frame_id':
                self.publisher.publish(k, v)
        
        # State
        state = self.encoder.encode_state(self.parser.data)
        for k, v in state.items():
            if k != 'frame_id':
                self.publisher.publish(k, v)
        
        # Cells
        cells = self.encoder.encode_cells(self.parser.data)
        for k, v in cells.items():
            if k != 'frame_id':
                self.publisher.publish(k, v, 'V')
        
        # Temps
        temps = self.encoder.encode_temps(self.parser.data)
        for k, v in temps.items():
            if k != 'frame_id':
                self.publisher.publish(k, v, '°C')


def main():
    import argparse
    import os
    
    parser = argparse.ArgumentParser('SMA SI EVTV Converter (HAOS)')
    parser.add_argument('--relay-host', default=os.getenv('RELAY_HOST', 'nas.local'))
    parser.add_argument('--relay-port', type=int, default=int(os.getenv('RELAY_PORT', '9001')))
    parser.add_argument('--ha-host', default=os.getenv('HA_HOST', 'localhost'))
    parser.add_argument('--ha-port', type=int, default=int(os.getenv('HA_PORT', '8123')))
    parser.add_argument('--log-level', default=os.getenv('LOG_LEVEL', 'INFO').upper())
    
    args = parser.parse_args()
    logging.getLogger().setLevel(getattr(logging, args.log_level))
    
    converter = EVTVtoSIConverter(
        relay_host=args.relay_host,
        relay_port=args.relay_port,
        ha_host=args.ha_host,
        ha_port=args.ha_port
    )
    
    converter.run()


if __name__ == '__main__':
    main()
