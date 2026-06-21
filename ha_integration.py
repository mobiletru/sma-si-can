"""
Home Assistant Integration for SMA Sunny Island CAN
Direct HA REST API + native MQTT discovery
Runs as HAOS add-on, publishes to HA's built-in MQTT (if enabled)
"""

import json
import logging
import requests
from typing import Dict, Optional
import paho.mqtt.client as mqtt
from can_interface import CANBusInterface
from protocol import FrameID, decode_frame

logger = logging.getLogger(__name__)


class HomeAssistantIntegration:
    """Direct integration with Home Assistant"""
    
    def __init__(self, ha_host: str = 'http://localhost:8123',
                 ha_token: Optional[str] = None,
                 mqtt_host: str = 'localhost',
                 mqtt_port: int = 1883):
        """
        Initialize HA integration
        
        Args:
            ha_host: Home Assistant URL
            ha_token: Long-lived access token (optional, for REST API)
            mqtt_host: MQTT broker (HA's built-in at localhost:1883)
            mqtt_port: MQTT broker port
        """
        self.ha_host = ha_host
        self.ha_token = ha_token
        self.mqtt_host = mqtt_host
        self.mqtt_port = mqtt_port
        self.mqtt_client = mqtt.Client(client_id='sma-si-can-ha')
        self.mqtt_connected = False
    
    def connect_mqtt(self) -> bool:
        """Connect to HA's built-in MQTT"""
        try:
            self.mqtt_client.on_connect = self._mqtt_on_connect
            self.mqtt_client.on_disconnect = self._mqtt_on_disconnect
            self.mqtt_client.connect(self.mqtt_host, self.mqtt_port, keepalive=60)
            self.mqtt_client.loop_start()
            return True
        except Exception as e:
            logger.error(f"Failed to connect to MQTT: {e}")
            return False
    
    def _mqtt_on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            self.mqtt_connected = True
            logger.info("Connected to Home Assistant MQTT")
        else:
            logger.error(f"MQTT connection failed (code {rc})")
    
    def _mqtt_on_disconnect(self, client, userdata, rc):
        self.mqtt_connected = False
    
    def publish_mqtt_discovery(self, entity_id: str, name: str, 
                               unit: str = '', value_template: str = '') -> bool:
        """
        Publish MQTT discovery for HA auto-add
        Uses homeassistant/sensor/{unique_id}/config
        """
        if not self.mqtt_connected:
            return False
        
        discovery_topic = f"homeassistant/sensor/sma-si/{entity_id}/config"
        
        config = {
            "name": name,
            "unique_id": f"sma_si_{entity_id}",
            "state_topic": f"home/sma-si/{entity_id}",
            "unit_of_measurement": unit,
            "device_class": self._get_device_class(entity_id),
            "json_attributes_topic": f"home/sma-si/{entity_id}",
            "device": {
                "identifiers": ["sma_si_bms"],
                "name": "SMA Sunny Island BMS",
                "manufacturer": "SMA",
                "model": "SI6048-US",
                "sw_version": "1.0.0"
            }
        }
        
        try:
            self.mqtt_client.publish(
                discovery_topic,
                json.dumps(config),
                retain=True
            )
            logger.debug(f"Published discovery for {entity_id}")
            return True
        except Exception as e:
            logger.error(f"Discovery publish failed: {e}")
            return False
    
    def publish_sensor(self, entity_id: str, value: float, 
                      name: str = '', unit: str = '') -> bool:
        """Publish sensor value to MQTT state topic"""
        if not self.mqtt_connected:
            return False
        
        topic = f"home/sma-si/{entity_id}"
        
        try:
            # First publish discovery if not yet published
            if name:
                self.publish_mqtt_discovery(entity_id, name, unit)
            
            # Publish value
            payload = json.dumps({
                "value": value,
                "unit": unit,
                "timestamp": __import__('time').time()
            })
            
            self.mqtt_client.publish(topic, payload, retain=True)
            logger.debug(f"Published {entity_id} = {value} {unit}")
            return True
        
        except Exception as e:
            logger.error(f"Sensor publish failed: {e}")
            return False
    
    def _get_device_class(self, entity_id: str) -> str:
        """Map entity IDs to HA device classes"""
        device_classes = {
            'pack_voltage': 'voltage',
            'pack_current': 'current',
            'temperature': 'temperature',
            'soc': 'battery',
            'soh': 'battery',
        }
        return device_classes.get(entity_id, '')
    
    def disconnect(self) -> None:
        """Disconnect from MQTT"""
        try:
            self.mqtt_client.loop_stop()
            self.mqtt_client.disconnect()
        except:
            pass


class CANToHABridge:
    """CAN bus to Home Assistant bridge"""
    
    def __init__(self, can_interface: CANBusInterface, 
                 ha_integration: HomeAssistantIntegration):
        """
        Initialize CAN-to-HA bridge
        
        Args:
            can_interface: Connected CAN interface
            ha_integration: HA integration instance
        """
        self.can = can_interface
        self.ha = ha_integration
        self.frame_ids = [
            FrameID.STATUS,
            FrameID.STATE,
            FrameID.CELL_VOLTAGES_1,
            FrameID.TEMPS,
        ]
    
    def process_frame(self, frame_id: int, data: bytes) -> None:
        """Process a CAN frame and publish to HA"""
        try:
            decoded = decode_frame(frame_id, data)
            
            if frame_id == FrameID.STATUS:
                self.ha.publish_sensor(
                    'pack_voltage_v',
                    decoded.get('pack_voltage_v', 0),
                    'Pack Voltage',
                    'V'
                )
                self.ha.publish_sensor(
                    'pack_current_a',
                    decoded.get('pack_current_a', 0),
                    'Pack Current',
                    'A'
                )
                self.ha.publish_sensor(
                    'temperature_c',
                    decoded.get('temperature_c', 0),
                    'BMS Temperature',
                    '°C'
                )
            
            elif frame_id == FrameID.STATE:
                self.ha.publish_sensor(
                    'soc_pct',
                    decoded.get('soc_pct', 0),
                    'State of Charge',
                    '%'
                )
                self.ha.publish_sensor(
                    'soh_pct',
                    decoded.get('soh_pct', 0),
                    'State of Health',
                    '%'
                )
            
            elif frame_id == FrameID.CELL_VOLTAGES_1:
                cells = decoded.get('cell_voltages', [])
                for i, voltage in enumerate(cells, 1):
                    self.ha.publish_sensor(
                        f'cell_{i}_v',
                        voltage,
                        f'Cell {i} Voltage',
                        'V'
                    )
            
            elif frame_id == FrameID.TEMPS:
                temps = decoded.get('temperatures_c', [])
                for i, temp in enumerate(temps, 1):
                    self.ha.publish_sensor(
                        f'temp_{i}_c',
                        temp,
                        f'Temperature Sensor {i}',
                        '°C'
                    )
        
        except Exception as e:
            logger.error(f"Error processing frame: {e}")
    
    def run(self) -> None:
        """Main bridge loop"""
        logger.info("Starting CAN-to-HA bridge")
        
        try:
            while True:
                messages = self.can.receive_all(timeout=0.5)
                
                for msg in messages:
                    if msg.frame_id in self.frame_ids:
                        self.process_frame(msg.frame_id, msg.data)
        
        except KeyboardInterrupt:
            logger.info("Bridge stopped")
        except Exception as e:
            logger.error(f"Bridge error: {e}")
        finally:
            self.shutdown()
    
    def shutdown(self) -> None:
        """Shutdown bridge"""
        logger.info("Shutting down...")
        self.can.disconnect()
        self.ha.disconnect()


def create_ha_bridge(can_interface: str = 'pcan',
                     can_channel: str = 'PCAN_USBCH1',
                     ha_host: str = 'http://localhost:8123') -> CANToHABridge:
    """Factory to create CAN-to-HA bridge (no external MQTT needed)"""
    
    # CAN interface
    if can_interface == 'pcan':
        from can_interface import create_pcan_interface
        can = create_pcan_interface(channel=can_channel)
    else:
        from can_interface import create_socketcan_interface
        can = create_socketcan_interface(channel=can_channel)
    
    if not can.connect():
        raise RuntimeError("Failed to connect to CAN bus")
    
    # HA integration (connects to HA's built-in MQTT at localhost:1883)
    ha = HomeAssistantIntegration(
        ha_host=ha_host,
        mqtt_host='localhost',
        mqtt_port=1883
    )
    
    if not ha.connect_mqtt():
        raise RuntimeError("Failed to connect to Home Assistant MQTT")
    
    return CANToHABridge(can, ha)
