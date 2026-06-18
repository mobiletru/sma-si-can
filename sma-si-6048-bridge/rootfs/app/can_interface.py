"""
CAN Bus Interface Layer
Supports PCAN-USB adapter via python-can library
Handles 11-bit CAN frames at 500 kbit/s
"""

import can
import logging
from typing import Optional, Callable, Dict
from dataclasses import dataclass
from protocol import FrameID, decode_frame

logger = logging.getLogger(__name__)


@dataclass
class CANMessage:
    """Standardized CAN message container"""
    frame_id: int
    data: bytes
    timestamp: float = 0.0
    is_extended: bool = False
    
    def to_can_message(self) -> can.Message:
        """Convert to python-can Message"""
        return can.Message(
            arbitration_id=self.frame_id,
            data=self.data,
            timestamp=self.timestamp,
            is_extended_id=self.is_extended
        )
    
    @staticmethod
    def from_can_message(msg: can.Message) -> 'CANMessage':
        """Convert from python-can Message"""
        return CANMessage(
            frame_id=msg.arbitration_id,
            data=bytes(msg.data),
            timestamp=msg.timestamp,
            is_extended=msg.is_extended_id
        )


class CANBusInterface:
    """
    CAN Bus interface for PCAN-USB or socketCAN
    Handles frame transmission/reception and decoding
    """
    
    def __init__(self, interface: str = 'pcan', channel: str = 'PCAN_USBCH1', 
                 bitrate: int = 500000):
        """
        Initialize CAN bus interface
        
        Args:
            interface: 'pcan' for PCAN-USB, 'socketcan' for native Linux CAN
            channel: PCAN channel name (e.g. 'PCAN_USBCH1', 'PCAN_USBCH2')
            bitrate: CAN bus bitrate in bits/s (default 500000 for SMA SI)
        """
        self.interface = interface
        self.channel = channel
        self.bitrate = bitrate
        self.bus: Optional[can.BusABC] = None
        self.reader: Optional[can.BufferedReader] = None
        self.writer: Optional[can.CyclicSendTaskABC] = None
        self.rx_callback: Optional[Callable] = None
    
    def connect(self) -> bool:
        """Connect to CAN bus"""
        try:
            if self.interface == 'pcan':
                # PCAN-USB adapter via PyPCAN
                self.bus = can.interface.Bus(
                    interface='pcan',
                    channel=self.channel,
                    bitrate=self.bitrate,
                    state=can.BusState.ACTIVE
                )
            elif self.interface == 'socketcan':
                # Native Linux SocketCAN
                self.bus = can.interface.Bus(
                    interface='socketcan',
                    channel=self.channel,
                    bitrate=self.bitrate,
                    state=can.BusState.ACTIVE
                )
            else:
                logger.error(f"Unknown interface: {self.interface}")
                return False
            
            # Set up reader
            self.reader = can.BufferedReader()
            self.bus.add_reader(self.reader)
            
            logger.info(f"Connected to CAN bus: {self.interface}:{self.channel} @ {self.bitrate} bps")
            return True
        
        except Exception as e:
            logger.error(f"Failed to connect to CAN bus: {e}")
            return False
    
    def disconnect(self) -> None:
        """Disconnect from CAN bus"""
        if self.bus:
            try:
                self.bus.shutdown()
                self.bus = None
                self.reader = None
                logger.info("Disconnected from CAN bus")
            except Exception as e:
                logger.error(f"Error disconnecting: {e}")
    
    def send(self, frame_id: int, data: bytes) -> bool:
        """
        Send a CAN frame
        
        Args:
            frame_id: 11-bit CAN ID
            data: 0-8 bytes of data
        
        Returns:
            True if sent successfully
        """
        if not self.bus:
            logger.warning("CAN bus not connected")
            return False
        
        try:
            msg = can.Message(
                arbitration_id=frame_id,
                data=data,
                is_extended_id=False
            )
            self.bus.send(msg)
            logger.debug(f"TX: 0x{frame_id:03X} {data.hex()}")
            return True
        
        except Exception as e:
            logger.error(f"Failed to send CAN frame: {e}")
            return False
    
    def receive(self, timeout: float = 1.0) -> Optional[CANMessage]:
        """
        Receive a single CAN frame
        
        Args:
            timeout: Timeout in seconds
        
        Returns:
            CANMessage or None if timeout
        """
        if not self.reader:
            return None
        
        try:
            msg = self.reader.get_message(timeout=timeout)
            if msg:
                logger.debug(f"RX: 0x{msg.arbitration_id:03X} {bytes(msg.data).hex()}")
                return CANMessage.from_can_message(msg)
        except Exception as e:
            logger.error(f"Error receiving CAN frame: {e}")
        
        return None
    
    def receive_all(self, timeout: float = 0.1) -> list[CANMessage]:
        """
        Receive all buffered CAN frames
        
        Args:
            timeout: Timeout in seconds for first frame
        
        Returns:
            List of CANMessage objects
        """
        messages = []
        msg = self.receive(timeout=timeout)
        
        while msg:
            messages.append(msg)
            msg = self.receive(timeout=0.001)  # Non-blocking for subsequent frames
        
        return messages
    
    def set_filter(self, frame_id: int, mask: int = 0x7FF) -> None:
        """
        Set CAN frame filter (11-bit mask)
        
        Args:
            frame_id: Frame ID to accept
            mask: Mask for matching (0x7FF = exact match)
        """
        if not self.bus:
            return
        
        try:
            filters = [
                {"can_id": frame_id, "can_mask": mask, "extended": False}
            ]
            self.bus.set_filters(filters)
            logger.info(f"CAN filter set: 0x{frame_id:03X} mask 0x{mask:03X}")
        except Exception as e:
            logger.warning(f"Cannot set CAN filter: {e}")
    
    def monitor_frames(self, frame_ids: list[int], callback: Callable[[int, Dict], None]) -> None:
        """
        Monitor specific frame IDs and decode payloads
        
        Args:
            frame_ids: List of frame IDs to monitor
            callback: Function(frame_id, decoded_data) called for each frame
        """
        logger.info(f"Monitoring frames: {[f'0x{fid:03X}' for fid in frame_ids]}")
        
        try:
            while self.bus:
                msg = self.receive(timeout=0.5)
                if msg and msg.frame_id in frame_ids:
                    decoded = decode_frame(msg.frame_id, msg.data)
                    callback(msg.frame_id, decoded)
        
        except KeyboardInterrupt:
            logger.info("Monitor stopped")
        except Exception as e:
            logger.error(f"Monitor error: {e}")


# Pre-configured instance for standard PCAN-USB setup
def create_pcan_interface(channel: str = 'PCAN_USBCH1') -> CANBusInterface:
    """Create a PCAN-USB interface with standard SMA SI settings"""
    return CANBusInterface(
        interface='pcan',
        channel=channel,
        bitrate=500000  # SMA SI standard
    )


def create_socketcan_interface(channel: str = 'can0') -> CANBusInterface:
    """Create a SocketCAN interface with standard SMA SI settings"""
    return CANBusInterface(
        interface='socketcan',
        channel=channel,
        bitrate=500000  # SMA SI standard
    )
