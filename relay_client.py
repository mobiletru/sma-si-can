"""
SMA SI CAN - Relay Client for HAOS
Connects to TCP relay server on VM, publishes to Home Assistant MQTT
"""

import json
import logging
import socket
import threading
import time
from typing import Optional, Dict

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class RelayClient:
    """Client that connects to CAN relay server"""
    
    def __init__(self, relay_host: str, relay_port: int = 9001):
        """
        Initialize relay client
        
        Args:
            relay_host: Relay server hostname/IP
            relay_port: Relay server TCP port
        """
        self.relay_host = relay_host
        self.relay_port = relay_port
        self.socket: Optional[socket.socket] = None
        self.connected = False
        self.running = False
    
    def connect(self) -> bool:
        """Connect to relay server"""
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.connect((self.relay_host, self.relay_port))
            self.socket.settimeout(5.0)
            self.connected = True
            self.running = True
            
            logger.info(f"Connected to relay server: {self.relay_host}:{self.relay_port}")
            return True
        
        except Exception as e:
            logger.error(f"Failed to connect to relay server: {e}")
            self.connected = False
            return False
    
    def disconnect(self) -> None:
        """Disconnect from relay server"""
        self.running = False
        if self.socket:
            try:
                self.socket.close()
            except:
                pass
            self.connected = False
    
    def receive_frame(self, timeout: float = 1.0) -> Optional[Dict]:
        """
        Receive a single frame from relay server
        
        Returns:
            Dict with frame data or None if timeout
        """
        if not self.connected:
            return None
        
        try:
            # Read until newline
            data = b''
            while b'\n' not in data:
                chunk = self.socket.recv(1024)
                if not chunk:
                    self.connected = False
                    return None
                data += chunk
            
            # Parse JSON
            frame_json = data.split(b'\n')[0].decode('utf-8')
            frame = json.loads(frame_json)
            return frame
        
        except socket.timeout:
            return None
        except Exception as e:
            logger.error(f"Error receiving frame: {e}")
            self.connected = False
            return None
    
    def receive_frames_blocking(self, callback) -> None:
        """
        Blocking receive loop
        
        Args:
            callback: Function(frame_dict) called for each frame
        """
        while self.running:
            frame = self.receive_frame(timeout=1.0)
            if frame:
                callback(frame)
            else:
                # Reconnect if disconnected
                if not self.connected and self.running:
                    logger.warning("Relay disconnected, reconnecting...")
                    time.sleep(2)
                    self.connect()


class RelayToMQTTBridge:
    """Bridge relay client to Home Assistant MQTT"""
    
    def __init__(self, relay_host: str, relay_port: int = 9001,
                 mqtt_host: str = 'localhost', mqtt_port: int = 1883):
        """Initialize bridge"""
        self.relay = RelayClient(relay_host, relay_port)
        self.mqtt_host = mqtt_host
        self.mqtt_port = mqtt_port
        self.mqtt_client = None
        self.mqtt_connected = False
    
    def connect_mqtt(self) -> bool:
        """Connect to Home Assistant MQTT"""
        try:
            import paho.mqtt.client as mqtt
            
            self.mqtt_client = mqtt.Client(client_id='sma-si-can-relay')
            self.mqtt_client.on_connect = self._mqtt_on_connect
            self.mqtt_client.connect(self.mqtt_host, self.mqtt_port, keepalive=60)
            self.mqtt_client.loop_start()
            
            # Wait for connection
            for _ in range(10):
                if self.mqtt_connected:
                    return True
                time.sleep(0.5)
            
            return False
        
        except Exception as e:
            logger.error(f"Failed to connect to MQTT: {e}")
            return False
    
    def _mqtt_on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            self.mqtt_connected = True
            logger.info("Connected to Home Assistant MQTT")
        else:
            logger.error(f"MQTT connection failed (code {rc})")
    
    def publish_frame(self, frame: Dict) -> None:
        """Publish a frame to MQTT"""
        if not self.mqtt_connected or not self.mqtt_client:
            return
        
        try:
            # Map frame IDs to topics
            frame_id = frame.get('frame_id_int', 0)
            
            topic_map = {
                0x351: 'home/sma-si/status',
                0x355: 'home/sma-si/cells/1-4',
                0x356: 'home/sma-si/cells/5-8',
                0x35A: 'home/sma-si/temps',
                0x35E: 'home/sma-si/balancing',
                0x35F: 'home/sma-si/state',
            }
            
            topic = topic_map.get(frame_id, f"home/sma-si/frame_{frame_id:03X}")
            
            # Clean up frame for MQTT
            payload = {
                'frame_id': frame.get('frame_id'),
                'raw': frame.get('data'),
                'timestamp': frame.get('timestamp')
            }
            
            self.mqtt_client.publish(
                topic,
                json.dumps(payload),
                retain=True
            )
            
            logger.debug(f"Published {topic}")
        
        except Exception as e:
            logger.error(f"Publish failed: {e}")
    
    def run(self) -> None:
        """Main loop"""
        logger.info("Starting relay-to-MQTT bridge")
        
        # Connect to relay
        if not self.relay.connect():
            logger.error("Failed to connect to relay server")
            return
        
        # Connect to MQTT
        if not self.connect_mqtt():
            logger.error("Failed to connect to MQTT")
            self.relay.disconnect()
            return
        
        # Receive and publish
        try:
            self.relay.receive_frames_blocking(self.publish_frame)
        except KeyboardInterrupt:
            logger.info("Stopped")
        finally:
            self.shutdown()
    
    def shutdown(self) -> None:
        """Shutdown bridge"""
        logger.info("Shutting down...")
        self.relay.disconnect()
        if self.mqtt_client:
            try:
                self.mqtt_client.loop_stop()
                self.mqtt_client.disconnect()
            except:
                pass


def main():
    """Run the relay-to-MQTT bridge"""
    import argparse
    import os
    
    parser = argparse.ArgumentParser(description='SMA SI Relay-to-MQTT Bridge')
    parser.add_argument('--relay-host', 
                       default=os.getenv('RELAY_HOST', 'localhost'),
                       help='Relay server host')
    parser.add_argument('--relay-port', type=int,
                       default=int(os.getenv('RELAY_PORT', '9001')),
                       help='Relay server port')
    parser.add_argument('--mqtt-host',
                       default=os.getenv('MQTT_HOST', 'localhost'),
                       help='MQTT broker host')
    parser.add_argument('--mqtt-port', type=int,
                       default=int(os.getenv('MQTT_PORT', '1883')),
                       help='MQTT broker port')
    
    args = parser.parse_args()
    
    bridge = RelayToMQTTBridge(
        relay_host=args.relay_host,
        relay_port=args.relay_port,
        mqtt_host=args.mqtt_host,
        mqtt_port=args.mqtt_port
    )
    
    bridge.run()


if __name__ == '__main__':
    main()
