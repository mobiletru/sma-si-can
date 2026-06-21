"""
SMA Sunny Island Li-Ion External BMS CAN Protocol
Protocol: SMA Li-Ion external BMS via CAN bus
Bitrate: 500 kbit/s, 11-bit standard IDs
Reference: SMA SI6048-US firmware documentation
"""

from enum import IntEnum
from dataclasses import dataclass
from typing import Dict, Tuple

# CAN Frame IDs (11-bit)
class FrameID(IntEnum):
    """SMA Li-Ion external BMS protocol frame IDs"""
    STATUS = 0x351          # BMS status, pack voltage, current
    CELL_VOLTAGES_1 = 0x355  # Cell voltages 1-4
    CELL_VOLTAGES_2 = 0x356  # Cell voltages 5-8
    TEMPS = 0x35A           # Temperature sensors
    BALANCING = 0x35E       # Cell balancing status
    STATE = 0x35F           # SOC, SOH, error state


@dataclass
class BMSFrame:
    """Decoded BMS frame structure"""
    frame_id: int
    dlc: int  # Data length code (0-8 bytes)
    data: bytes
    timestamp: float = 0.0


class StatusFrame:
    """0x351: BMS Status frame
    Byte 0-1: Pack voltage (0.01V per LSB, offset 0V)
    Byte 2-3: Pack current (0.1A per LSB, offset -3200A, signed)
    Byte 4: Temperature (°C, offset -40°C)
    Byte 5: BMS error flags
    Byte 6-7: Reserved
    """
    
    @staticmethod
    def pack(pack_voltage_v: float, pack_current_a: float, temp_c: float, error_flags: int = 0) -> bytes:
        """Encode status frame"""
        voltage_raw = int(pack_voltage_v / 0.01)  # 0.01V LSB
        current_raw = int((pack_current_a + 3200) / 0.1)  # 0.1A LSB, offset 3200A
        temp_raw = int(temp_c + 40)  # offset -40°C
        
        return bytes([
            voltage_raw & 0xFF,
            (voltage_raw >> 8) & 0xFF,
            current_raw & 0xFF,
            (current_raw >> 8) & 0xFF,
            temp_raw & 0xFF,
            error_flags & 0xFF,
            0x00, 0x00
        ])
    
    @staticmethod
    def unpack(data: bytes) -> Dict:
        """Decode status frame"""
        if len(data) < 6:
            return {}
        
        voltage_raw = data[0] | (data[1] << 8)
        current_raw = data[2] | (data[3] << 8)
        if current_raw & 0x8000:  # Sign extend
            current_raw = current_raw - 0x10000
        temp_raw = data[4]
        error_flags = data[5]
        
        return {
            'pack_voltage_v': voltage_raw * 0.01,
            'pack_current_a': (current_raw * 0.1) - 3200,
            'temperature_c': temp_raw - 40,
            'error_flags': error_flags,
            'timestamp': 0.0
        }


class StateFrame:
    """0x35F: BMS State frame
    Byte 0: SOC (0-100%, 1% per LSB)
    Byte 1: SOH (0-100%, 1% per LSB)
    Byte 2-3: Error state code
    Byte 4-7: Reserved
    """
    
    @staticmethod
    def pack(soc_pct: float, soh_pct: float, error_code: int = 0) -> bytes:
        """Encode state frame"""
        soc_raw = int(soc_pct)
        soh_raw = int(soh_pct)
        
        return bytes([
            soc_raw & 0xFF,
            soh_raw & 0xFF,
            error_code & 0xFF,
            (error_code >> 8) & 0xFF,
            0x00, 0x00, 0x00, 0x00
        ])
    
    @staticmethod
    def unpack(data: bytes) -> Dict:
        """Decode state frame"""
        if len(data) < 4:
            return {}
        
        error_code = data[2] | (data[3] << 8)
        
        return {
            'soc_pct': float(data[0]),
            'soh_pct': float(data[1]),
            'error_code': error_code,
        }


class CellVoltagesFrame1:
    """0x355: Cell voltages 1-4
    Each voltage: 16-bit little-endian, 0.001V per LSB
    """
    
    @staticmethod
    def pack(cell_voltages: Tuple[float, float, float, float]) -> bytes:
        """Encode cell voltages 1-4"""
        data = bytearray(8)
        for i, voltage in enumerate(cell_voltages[:4]):
            raw = int(voltage / 0.001) & 0xFFFF
            data[i * 2:(i + 1) * 2] = raw.to_bytes(2, 'little')
        return bytes(data)
    
    @staticmethod
    def unpack(data: bytes) -> Dict:
        """Decode cell voltages 1-4"""
        if len(data) < 8:
            return {}
        
        voltages = []
        for i in range(4):
            raw = int.from_bytes(data[i * 2:(i + 1) * 2], 'little')
            voltages.append(raw * 0.001)
        
        return {
            'cell_voltages': voltages,
        }


class CellVoltagesFrame2:
    """0x356: Cell voltages 5-8
    Each voltage: 16-bit little-endian, 0.001V per LSB
    """
    
    @staticmethod
    def pack(cell_voltages: Tuple[float, float, float, float]) -> bytes:
        """Encode cell voltages 5-8"""
        data = bytearray(8)
        for i, voltage in enumerate(cell_voltages[:4]):
            raw = int(voltage / 0.001) & 0xFFFF
            data[i * 2:(i + 1) * 2] = raw.to_bytes(2, 'little')
        return bytes(data)
    
    @staticmethod
    def unpack(data: bytes) -> Dict:
        """Decode cell voltages 5-8"""
        if len(data) < 8:
            return {}
        
        voltages = []
        for i in range(4):
            raw = int.from_bytes(data[i * 2:(i + 1) * 2], 'little')
            voltages.append(raw * 0.001)
        
        return {
            'cell_voltages': voltages,
        }


class TemperatureFrame:
    """0x35A: Temperature sensors (up to 4 sensors)
    Each temp: 0.1°C per LSB, offset -40°C, 8-bit signed
    """
    
    @staticmethod
    def pack(temps: Tuple[float, ...]) -> bytes:
        """Encode temperature frame"""
        data = bytearray(8)
        for i, temp in enumerate(temps[:4]):
            temp_raw = int((temp + 40) / 0.1)
            data[i] = temp_raw & 0xFF
        return bytes(data)
    
    @staticmethod
    def unpack(data: bytes) -> Dict:
        """Decode temperature frame"""
        if len(data) < 4:
            return {}
        
        temps = []
        for i in range(4):
            temp_raw = data[i]
            if temp_raw & 0x80:  # Sign extend if needed
                temp_raw = temp_raw - 0x100
            temps.append((temp_raw * 0.1) - 40)
        
        return {
            'temperatures_c': temps,
        }


# Protocol frame registry
FRAME_DECODERS = {
    FrameID.STATUS: StatusFrame,
    FrameID.STATE: StateFrame,
    FrameID.CELL_VOLTAGES_1: CellVoltagesFrame1,
    FrameID.CELL_VOLTAGES_2: CellVoltagesFrame2,
    FrameID.TEMPS: TemperatureFrame,
}


def decode_frame(frame_id: int, data: bytes) -> Dict:
    """Decode a CAN frame to human-readable format"""
    decoder_class = FRAME_DECODERS.get(frame_id)
    if decoder_class:
        return decoder_class.unpack(data)
    return {'raw': data.hex()}


def encode_frame(frame_id: int, payload: Dict) -> bytes:
    """Encode a CAN frame from human-readable format"""
    encoder_class = FRAME_DECODERS.get(frame_id)
    if encoder_class:
        fields = dict(payload)
        if frame_id == FrameID.STATUS and 'temperature_c' in fields and 'temp_c' not in fields:
            fields['temp_c'] = fields['temperature_c']
        if frame_id == FrameID.TEMPS and 'temperatures_c' in fields and 'temps' not in fields:
            fields['temps'] = fields['temperatures_c']
        return encoder_class.pack(**fields)
    raise ValueError(f"No encoder for frame ID 0x{frame_id:03X}")
