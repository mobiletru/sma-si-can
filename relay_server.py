"""
SMA Sunny Island CAN - TCP Relay Server
Runs on VM with PCAN-USB adapter
Streams CAN frames over TCP to remote clients (HAOS add-on, etc.)
"""

import socket
import logging
import threading
import json
from typing import List
import time

from can_interface import CANBusInterface, create_pcan_interface
from protocol import FrameID

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class CANRelayServer:
    """TCP server that streams CAN frames to remote clients + accepts send commands"""
    
    def __init__(self, can_interface: CANBusInterface, 
                 host: str = '0.0.0.0', port: int = 9001):
        """
        Initialize relay server (bidirectional)
        
        Args:
            can_interface: Connected CAN interface
            host: Bind address (0.0.0.0 = all interfaces)
            port: TCP port to listen on
        
        Protocol:
        - Receive frames: {"type": "frame", "frame_id": "0x351", "data_bytes": [...]}
        - Send command: {"type": "send", "frame_id": "0x351", "data": "aabbccddee..."}
        """
        self.can = can_interface
        self.host = host
        self.port = port
        self.server_socket: socket.socket = None
        self.clients: List[socket.socket] = []
        self.running = False
        self.client_lock = threading.Lock()
        self.send_lock = threading.Lock()
    
    def start(self) -> bool:
        """Start the relay server"""
        try:
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.bind((self.host, self.port))
            self.server_socket.listen(5)
            self.running = True
            
            logger.info(f"Relay server listening on {self.host}:{self.port}")
            
            # Start accept thread
            accept_thread = threading.Thread(target=self._accept_loop, daemon=True)
            accept_thread.start()
            
            # Start broadcast thread
            broadcast_thread = threading.Thread(target=self._broadcast_loop, daemon=True)
            broadcast_thread.start()
            
            # Start command handler thread
            command_thread = threading.Thread(target=self._command_loop, daemon=True)
            command_thread.start()
            
            return True
        
        except Exception as e:
            logger.error(f"Failed to start relay server: {e}")
            return False
    
    def _accept_loop(self) -> None:
        """Accept incoming client connections"""
        while self.running:
            try:
                client_socket, addr = self.server_socket.accept()
                
                with self.client_lock:
                    self.clients.append(client_socket)
                
                logger.info(f"Client connected: {addr[0]}:{addr[1]}")
                
                # Send welcome message
                welcome = {
                    "type": "welcome",
                    "message": "SMA SI CAN Relay v1.0",
                    "status": "connected"
                }
                try:
                    client_socket.send(json.dumps(welcome).encode() + b'\n')
                except:
                    pass
            
            except Exception as e:
                if self.running:
                    logger.error(f"Accept error: {e}")
    
    def _broadcast_loop(self) -> None:
        """Read CAN frames and broadcast to all clients"""
        while self.running:
            try:
                # Read all buffered frames
                messages = self.can.receive_all(timeout=0.1)
                
                for msg in messages:
                    # Format as JSON for transmission
                    frame_data = {
                        "type": "frame",
                        "frame_id": f"0x{msg.frame_id:03X}",
                        "frame_id_int": msg.frame_id,
                        "data": msg.data.hex(),
                        "data_bytes": list(msg.data),
                        "timestamp": time.time()
                    }
                    
                    frame_json = json.dumps(frame_data) + '\n'
                    
                    # Send to all connected clients
                    dead_clients = []
                    with self.client_lock:
                        for client in self.clients:
                            try:
                                client.send(frame_json.encode())
                            except Exception as e:
                                logger.debug(f"Client send error: {e}")
                                dead_clients.append(client)
                    
                    # Remove dead clients
                    with self.client_lock:
                        for client in dead_clients:
                            try:
                                client.close()
                                self.clients.remove(client)
                                logger.info("Client disconnected")
                            except:
                                pass
            
            except Exception as e:
                if self.running:
                    logger.error(f"Broadcast error: {e}")
    
    def _command_loop(self) -> None:
        """Listen for send commands from clients"""
        while self.running:
            try:
                with self.client_lock:
                    for client in list(self.clients):
                        try:
                            client.settimeout(0.1)  # Non-blocking
                            data = client.recv(1024)
                            
                            if data:
                                cmd_json = data.decode('utf-8').strip()
                                cmd = json.loads(cmd_json)
                                
                                if cmd.get('type') == 'send':
                                    self._handle_send_command(cmd)
                        except socket.timeout:
                            pass
                        except Exception as e:
                            logger.debug(f"Client command error: {e}")
                
                time.sleep(0.01)
            except Exception as e:
                if self.running:
                    logger.error(f"Command loop error: {e}")
    
    def _handle_send_command(self, cmd: Dict) -> None:
        """Handle send frame command from client"""
        try:
            frame_id = cmd.get('frame_id')
            data_hex = cmd.get('data', '')
            
            # Parse frame ID (0x351 or 351 or "0x351")
            if isinstance(frame_id, str):
                if frame_id.startswith('0x'):
                    frame_id_int = int(frame_id, 16)
                else:
                    frame_id_int = int(frame_id, 16)
            else:
                frame_id_int = int(frame_id)
            
            # Parse data (hex string to bytes)
            data = bytes.fromhex(data_hex)
            
            # Send on CAN
            self.can.send(frame_id_int, data)
            logger.info(f"Sent frame 0x{frame_id_int:03X}: {data_hex}")
        
        except Exception as e:
            logger.error(f"Send command failed: {e}")
    
    def shutdown(self) -> None:
        """Shutdown the relay server"""
        logger.info("Shutting down relay server...")
        self.running = False
        
        with self.client_lock:
            for client in self.clients:
                try:
                    client.close()
                except:
                    pass
            self.clients.clear()
        
        if self.server_socket:
            try:
                self.server_socket.close()
            except:
                pass


def main():
    """Run the relay server"""
    import argparse
    
    parser = argparse.ArgumentParser(description='SMA SI CAN Relay Server')
    parser.add_argument('--host', default='0.0.0.0', help='Bind address')
    parser.add_argument('--port', type=int, default=9001, help='TCP port')
    parser.add_argument('--channel', default='PCAN_USBCH1', help='PCAN channel')
    parser.add_argument('--bitrate', type=int, default=500000, help='CAN bitrate')
    
    args = parser.parse_args()
    
    # Create and connect CAN interface
    can = create_pcan_interface(channel=args.channel)
    if not can.connect():
        logger.error("Failed to connect to PCAN adapter")
        return 1
    
    logger.info(f"Connected to CAN: {args.channel} @ {args.bitrate} bps")
    
    # Create and start relay server
    relay = CANRelayServer(can, host=args.host, port=args.port)
    if not relay.start():
        return 1
    
    # Keep server running
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Shutdown requested")
    finally:
        relay.shutdown()
        can.disconnect()
    
    return 0


if __name__ == '__main__':
    exit(main())
