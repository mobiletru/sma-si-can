"""
MQTT Bridge for SMA Sunny Island CAN
Publishes decoded BMS data to MQTT for Home Assistant integration
"""

import json
import logging
from typing import Dict, Optional
import paho.mqtt.client as mqtt
from can_interface import CANBusInterface
from protocol import FrameID, decode_frame

logger = logging.getLogger(__name__)


class MQTTBridge:
    """Bridge between CAN bus and MQTT"""
    
    def __init__(self, broker_host: str = 'localhost', broker_port: int = 1883,
                 topic_prefix: str = 'home/sma-si', client_id: str = 'sma-si-can'):
        """
        Initialize MQTT bridge
        
        Args:
            broker_host: MQTT broker hostname
            broker_port: MQTT broker port
            topic_prefix: Base MQTT topic path
            client_id: MQTT client ID
        """
        self.broker_host = broker_host
        self.broker_port = broker_port
        self.topic_prefix = topic_prefix
        self.client = mqtt.Client(client_id=client_id)
        self.connected = False
        
        # Set up callbacks
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_message = self._on_message
    
    def _on_connect(self, client, userdata, flags, rc):
        """MQTT connection callback"""
        if rc == 0:
            self.connected = True
            logger.info(f"Connected to MQTT broker: {self.broker_host}:{self.broker_port}")
        else:
            logger.error(f"Failed to connect to MQTT broker (code {rc})")
    
    def _on_disconnect(self, client, userdata, rc):
        """MQTT disconnection callback"""
        self.connected = False
        if rc != 0:
            logger.warning(f"Unexpected disconnection from MQTT (code {rc})")
    
    def _on_message(self, client, userdata, msg):
        """MQTT message callback (for subscriptions)"""
        logger.debug(f"MQTT message: {msg.topic} = {msg.payload}")
    
    def connect(self, username: Optional[str] = None, password: Optional[str] = None) -> bool:
        """Connect to MQTT broker"""
        try:
            if username and password:
                self.client.username_pw_set(username, password)
            
            self.client.connect(self.broker_host, self.broker_port, keepalive=60)
            self.client.loop_start()
            return True
        
        except Exception as e:
            logger.error(f"Failed to connect to MQTT: {e}")
            return False
    
    def disconnect(self) -> None:
        """Disconnect from MQTT broker"""
        try:
            self.client.loop_stop()
            self.client.disconnect()
            self.connected = False
        except Exception as e:
            logger.error(f"Error disconnecting from MQTT: {e}")
    
    def publish(self, topic: str, payload: Dict, retain: bool = True) -> bool:
        """Publish JSON payload to MQTT"""
        if not self.connected:
            return False
        
        try:
            full_topic = f"{self.topic_prefix}/{topic}"
            json_payload = json.dumps(payload)
            self.client.publish(full_topic, json_payload, retain=retain)
            logger.debug(f"Published to {full_topic}: {json_payload}")
            return True
        
        except Exception as e:
            logger.error(f"Failed to publish to MQTT: {e}")
            return False
    
    def publish_frame(self, frame_id: int, data: bytes) -> bool:
        """Publish decoded CAN frame to MQTT"""
        try:
            decoded = decode_frame(frame_id, data)
            
            # Map frame IDs to topic names
            frame_names = {
                FrameID.STATUS: "status",
                FrameID.STATE: "state",
                FrameID.CELL_VOLTAGES_1: "cells/1-4",
                FrameID.TEMPS: "temps",
                FrameID.BALANCING: "balancing",
            }
            
            topic_name = frame_names.get(frame_id, f"frame_0x{frame_id:03X}")
            
            # Add frame ID and timestamp
            payload = {
                "frame_id": f"0x{frame_id:03X}",
                "raw": data.hex(),
                **decoded
            }
            
            return self.publish(topic_name, payload)
        
        except Exception as e:
            logger.error(f"Error publishing frame: {e}")
            return False
    
    def subscribe(self, topic: str) -> None:
        """Subscribe to MQTT topic"""
        if self.connected:
            full_topic = f"{self.topic_prefix}/{topic}"
            self.client.subscribe(full_topic)
            logger.info(f"Subscribed to {full_topic}")


class CANToMQTTBridge:
    """Bridge that continuously reads CAN frames and publishes to MQTT"""
    
    def __init__(self, can_interface: CANBusInterface, mqtt_bridge: MQTTBridge,
                 frame_ids: Optional[list[int]] = None):
        """
        Initialize CAN-to-MQTT bridge
        
        Args:
            can_interface: Connected CANBusInterface
            mqtt_bridge: Connected MQTTBridge
            frame_ids: List of frame IDs to monitor (None = all)
        """
        self.can = can_interface
        self.mqtt = mqtt_bridge
        self.frame_ids = frame_ids or [
            FrameID.STATUS,
            FrameID.STATE,
            FrameID.CELL_VOLTAGES_1,
            FrameID.TEMPS,
        ]
    
    def run(self) -> None:
        """Run the bridge loop"""
        logger.info(f"Starting CAN-to-MQTT bridge, monitoring {len(self.frame_ids)} frames")
        
        try:
            while True:
                # Receive all pending frames
                messages = self.can.receive_all(timeout=0.1)
                
                for msg in messages:
                    # Filter by frame ID if specified
                    if msg.frame_id in self.frame_ids:
                        self.mqtt.publish_frame(msg.frame_id, msg.data)
        
        except KeyboardInterrupt:
            logger.info("Bridge stopped by user")
        except Exception as e:
            logger.error(f"Bridge error: {e}")
        finally:
            self.shutdown()
    
    def shutdown(self) -> None:
        """Shutdown the bridge"""
        logger.info("Shutting down bridge...")
        self.can.disconnect()
        self.mqtt.disconnect()


def create_bridge(can_interface: str = 'pcan',
                  can_channel: str = 'PCAN_USBCH1',
                  mqtt_host: str = 'localhost',
                  mqtt_port: int = 1883,
                  mqtt_prefix: str = 'home/sma-si') -> CANToMQTTBridge:
    """
    Factory function to create a complete CAN-to-MQTT bridge
    
    Args:
        can_interface: 'pcan' or 'socketcan'
        can_channel: CAN channel name
        mqtt_host: MQTT broker host
        mqtt_port: MQTT broker port
        mqtt_prefix: MQTT topic prefix
    
    Returns:
        Configured CANToMQTTBridge instance
    """
    # Create CAN interface
    if can_interface == 'pcan':
        from can_interface import create_pcan_interface
        can = create_pcan_interface(channel=can_channel)
    else:
        from can_interface import create_socketcan_interface
        can = create_socketcan_interface(channel=can_channel)
    
    # Create MQTT bridge
    mqtt = MQTTBridge(
        broker_host=mqtt_host,
        broker_port=mqtt_port,
        topic_prefix=mqtt_prefix
    )
    
    # Connect both
    if not can.connect():
        raise RuntimeError("Failed to connect to CAN bus")
    
    if not mqtt.connect():
        raise RuntimeError("Failed to connect to MQTT broker")
    
    # Return bridge
    return CANToMQTTBridge(can, mqtt)
