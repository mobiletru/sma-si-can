╔══════════════════════════════════════════════════════════════════════════╗
║            PCAN → RJ45 → Sunny Island 6048 CAN Wiring Diagram           ║
╚══════════════════════════════════════════════════════════════════════════╝

┌─────────────────┐                    ┌──────────────────┐
│   PCAN-USB      │                    │      RJ45        │      ┌──────────────┐
│  (DB9 Male)     │                    │  (SI 6048 CAN)   │      │  SI 6048     │
│                 │    Twisted Pair    │                  │      │              │
│   Pin Layout:   ├───────────────────→│   Pin Layout:    │      │ BatTyp:      │
│                 │                    │                  │      │ LiIon_Ext-BMS│
│   1 2 3 4      │                    │  1 2 3 4 5 6 7 8 │      │              │
│   5 6 7 8 9    │                    └──────────────────┘      └──────────────┘
│                 │
└────────┬────────┘
         │
    USB to NAS
    (PCAN adapter)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

CONNECTIONS (3-wire):

┌──────────────────────────────────┬──────────────────────────────────┐
│   DB9 (PCAN Output)              │   RJ45 (SI 6048 Input)          │
├──────────────────────────────────┼──────────────────────────────────┤
│ Pin 2 (CAN-L)      ──────────→   │ Pin 5 (CAN-L)                    │
│ Pin 7 (CAN-H)      ──────────→   │ Pin 4 (CAN-H)                    │
│ Pin 3 (GND/Shield) ──────────→   │ Pin 8 (GND)                      │
└──────────────────────────────────┴──────────────────────────────────┘

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

DETAILED PIN-OUT:

  DB9 Male (PCAN)                      RJ45 Jack (SI 6048)
  ───────────────                      ──────────────────
  
  Top Row:                             Color order (568A standard):
    1  [NC]                              1  [White-Orange]
    2  ●─── CAN-L ────────────────→5   2  [Orange]
    3  ●─── GND  ────────────┐        3  [White-Green]
    4  [NC]                  │        4  ●←─── CAN-H
    5  [NC]                  │        5  ●←─── CAN-L
                             │        6  [Green]
  Bottom Row:                │        7  [White-Brown]
    6  [NC]                  │        8  ●←─── GND
    7  ●─── CAN-H ───────→4  │           (Shield/Pin 8)
    8  [NC]                  │
    9  [NC]                  └─────→8

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

SPECIFICATIONS:

PCAN-USB Settings:
  • Bitrate:        500 kbit/s
  • Frame format:   11-bit (Standard CAN)
  • Termination:    OFF (PCAN side — bus already terminated on SI)
  • Channel:        PCAN_USBCH1

Cable:
  • Type:           Shielded twisted pair (STP)
  • Gauge:          AWG 18-20 (~0.5mm²)
  • Length:         <20m recommended
  • Shield:         Connect to Pin 3 (GND) at PCAN end, Pin 8 at SI end

SI 6048 Settings (CRITICAL):
  • BatTyp:         MUST be set to "LiIon_Ext-BMS" (not VRLA)
  • CAN Address:    Auto-detect
  • Firmware:       v7.300+ required
  • Port:           502 (Modbus TCP fallback)

Termination:
  • SI 6048:        Has 120Ω termination built-in (RJ45 pins 4-5)
  • PCAN:           Termination OFF (don't enable)
  • Confirm:        Bus should have exactly 2 terminators (PCAN off, SI on)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

TROUBLESHOOTING:

Problem: No CAN frames received
  ✓ Check DB9 connector contacts (oxidation)
  ✓ Verify RJ45 cable is Cat5e+ (not damaged)
  ✓ SI BatTyp MUST be "LiIon_Ext-BMS" (check with WebBox or CLI)
  ✓ Confirm termination: SI on, PCAN off
  ✓ Use CAN analyzer to verify bus activity

Problem: SI not sending control frames back
  ✓ SI must be on same physical CAN bus as EVTV
  ✓ SI firmware version >= 7.300
  ✓ Verify SI is receiving SI protocol frames (0x351, 0x35F, etc)
  ✓ Check SI error logs (via WebBox)

Problem: Intermittent connection
  ✓ Check for loose RJ45 connectors
  ✓ Verify cable shielding continuity
  ✓ Test with shorter cable (not >10m)
  ✓ Reseat DB9 connector at PCAN

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

FRAME RATE:

  EVTV BMS → PCAN:    ~10-20 frames/sec (raw EVTV data)
  Bridge → SI 6048:   ~20 frames/sec (SI protocol, 50ms interval)
  Home Assistant:     ~2 Hz update rate (sensor publishing)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

SAFETY:

  ⚠️ Ensure SI is POWERED OFF before connecting/disconnecting cables
  ⚠️ Do not Hot-swap RJ45 while SI is running
  ⚠️ Check for short circuits with multimeter before power-on
  ⚠️ Verify termination resistor (120Ω) is present with ohmmeter
  ⚠️ Use proper shielded cable to avoid EMI interference

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
