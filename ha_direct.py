"""
SMA Sunny Island CAN - Direct to Home Assistant REST API
VM reads PCAN, publishes directly to Home Assistant via REST API
No relay server, no HAOS add-on, no MQTT needed
"""

import json
import logging
import time
from typing import Dict
import requests

from can_interface import CANBusInterface, create_pcan_interface
from protocol import FrameID, decode_frame

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class DirectHABridge:
    """Direct PCAN to Home Assistant REST API"""
    
    def __init__(self, can_interface: CANBusInterface,
                 ha_host: str = 'nas.local',
                 ha_port: int = 8123,
                 ha_token: str = None):
        """
        Initialize direct bridge
        
        Args:
            can_interface: Connected CAN interface
            ha_host: HA host (nas.local, 192.168.x.x, or home.mobileccs.com)
            ha_port: HA port (8123 default)
            ha_token: HA long-lived access token
        """
        self.can = can_interface
        self.ha_host = ha_host
        self.ha_port = ha_port
        self.ha_token = ha_token
        self.ha_url = f"http://{ha_host}:{ha_port}"
        self.ha_connected = False
        self.session = requests.Session()
        
        # Device registry for HA
        self.device_id = 'sma_si_bms_main'
        self.device_name = 'SMA Sunny Island BMS'
        
        # Map frame IDs to entity definitions
        self.entities = {
            'pack_voltage_v': {'name': 'Pack Voltage', 'unit': 'V', 'class': 'voltage', 'icon': 'mdi:flash'},
            'pack_current_a': {'name': 'Pack Current', 'unit': 'A', 'class': 'current', 'icon': 'mdi:current-ac'},
            'temperature_c': {'name': 'BMS Temperature', 'unit': '°C', 'class': 'temperature', 'icon': 'mdi:thermometer'},
            'soc_pct': {'name': 'State of Charge', 'unit': '%', 'class': 'battery', 'icon': 'mdi:battery'},
            'soh_pct': {'name': 'State of Health', 'unit': '%', 'class': 'battery', 'icon': 'mdi:heart'},
            'cell_1_v': {'name': 'Cell 1 Voltage', 'unit': 'V', 'class': 'voltage', 'icon': 'mdi:flash'},
            'cell_2_v': {'name': 'Cell 2 Voltage', 'unit': 'V', 'class': 'voltage', 'icon': 'mdi:flash'},
            'cell_3_v': {'name': 'Cell 3 Voltage', 'unit': 'V', 'class': 'voltage', 'icon': 'mdi:flash'},
            'cell_4_v': {'name': 'Cell 4 Voltage', 'unit': 'V', 'class': 'voltage', 'icon': 'mdi:flash'},
            'temp_1_c': {'name': 'Temp Sensor 1', 'unit': '°C', 'class': 'temperature', 'icon': 'mdi:thermometer'},
            'temp_2_c': {'name': 'Temp Sensor 2', 'unit': '°C', 'class': 'temperature', 'icon': 'mdi:thermometer'},
            'temp_3_c': {'name': 'Temp Sensor 3', 'unit': '°C', 'class': 'temperature', 'icon': 'mdi:thermometer'},
            'temp_4_c': {'name': 'Temp Sensor 4', 'unit': '°C', 'class': 'temperature', 'icon': 'mdi:thermometer'},
        }
    
    def connect_ha(self) -> bool:
        """Test connection to Home Assistant"""
        try:
            headers = {}
            if self.ha_token:
                headers['Authorization'] = f'Bearer {self.ha_token}'
            
            resp = requests.get(f"{self.ha_url}/api/", headers=headers, timeout=5)
            
            if resp.status_code == 200:
                self.ha_connected = True
                logger.info(f"Connected to HA: {self.ha_host}:{self.ha_port}")
                return True
            else:
                logger.error(f"HA connection failed (status {resp.status_code})")
                return False
        
        except Exception as e:
            logger.error(f"HA connect failed: {e}")
            return False
    
    def update_state(self, entity_id: str, value: float) -> None:
        """Update entity state in Home Assistant via REST API"""
        if not self.ha_connected:
            return
        
        try:
            headers = {
                'Content-Type': 'application/json',
            }
            if self.ha_token:
                headers['Authorization'] = f'Bearer {self.ha_token}'
            
            # Use homeassistant.set_state service
            payload = {
                'entity_id': f'sensor.sma_si_{entity_id}',
                'state': str(value),
                'attributes': {
                    'friendly_name': self.entities[entity_id]['name'],
                    'unit_of_measurement': self.entities[entity_id]['unit'],
                    'device_class': self.entities[entity_id]['class'],
                    'icon': self.entities[entity_id]['icon'],
                    'last_updated': time.time(),
                }
            }
            
            resp = self.session.post(
                f"{self.ha_url}/api/states/sensor.sma_si_{entity_id}",
                json=payload,
                headers=headers,
                timeout=5
            )
            
            if resp.status_code not in [200, 201]:
                logger.debug(f"State update failed: {entity_id} (status {resp.status_code})")
        
        except Exception as e:
            logger.debug(f"State update error: {e}")
    
    def process_frame(self, frame_id: int, data: bytes) -> None:
        """Decode frame and update Home Assistant states"""
        try:
            decoded = decode_frame(frame_id, data)
            
            # Special handling for cell voltages
            if frame_id == FrameID.CELL_VOLTAGES_1:
                cells = decoded.get('cell_voltages', [])
                for i, voltage in enumerate(cells, 1):
                    entity_id = f'cell_{i}_v'
                    self.update_state(entity_id, voltage)
            
            # Special handling for temps
            elif frame_id == FrameID.TEMPS:
                temps = decoded.get('temperatures_c', [])
                for i, temp in enumerate(temps, 1):
                    entity_id = f'temp_{i}_c'
                    self.update_state(entity_id, temp)
            
            # Standard: update each decoded value
            else:
                for key, value in decoded.items():
                    if key not in ['raw', 'timestamp'] and key in self.entities:
                        self.update_state(key, value)
        
        except Exception as e:
            logger.debug(f"Frame decode error: {e}")
    
    def shutdown(self) -> None:
        """Cleanup"""
        logger.info("Shutting down...")
        self.can.disconnect()
        try:
            self.session.close()
        except:
            pass


def main():
    """Run direct bridge"""
    import argparse
    import os
    
    parser = argparse.ArgumentParser(
        description='SMA SI CAN - Direct to Home Assistant via REST API'
    )
    parser.add_argument('--can-channel', 
                       default=os.getenv('CAN_CHANNEL', 'PCAN_USBCH1'),
                       help='PCAN channel name')
    parser.add_argument('--ha-host',
                       default=os.getenv('HA_HOST', 'nas.local'),
                       help='HA host (nas.local, 192.168.1.50, home.mobileccs.com)')
    parser.add_argument('--ha-port', type=int,
                       default=int(os.getenv('HA_PORT', '8123')),
                       help='HA port (default 8123)')
    parser.add_argument('--ha-token',
                       default=os.getenv('HA_TOKEN', None),
                       help='HA long-lived access token (optional)')
    parser.add_argument('--log-level',
                       default=os.getenv('LOG_LEVEL', 'info').upper(),
                       choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
                       help='Logging level')
    
    args = parser.parse_args()
    
    # Set log level
    logging.getLogger().setLevel(getattr(logging, args.log_level))
    
    # Create CAN interface
    logger.info(f"Connecting to PCAN: {args.can_channel}")
    can = create_pcan_interface(channel=args.can_channel)
    
    if not can.connect():
        logger.error("Failed to connect to PCAN adapter")
        return 1
    
    logger.info(f"Connected to PCAN: {args.can_channel}")
    
    # Create and run bridge
    bridge = DirectHABridge(
        can,
        ha_host=args.ha_host,
        ha_port=args.ha_port,
        ha_token=args.ha_token
    )
    
    if not bridge.connect_ha():
        logger.error("Failed to connect to Home Assistant")
        can.disconnect()
        return 1
    
    logger.info("Starting frame processing...")
    
    frame_count = 0
    try:
        while True:
            messages = can.receive_all(timeout=0.5)
            
            for msg in messages:
                bridge.process_frame(msg.frame_id, msg.data)
                frame_count += 1
                
                if frame_count % 100 == 0:
                    logger.info(f"Processed {frame_count} frames")
    
    except KeyboardInterrupt:
        logger.info("Stopped by user")
    except Exception as e:
        logger.error(f"Bridge error: {e}")
    finally:
        bridge.shutdown()
    
    return 0


if __name__ == '__main__':
    exit(main())
