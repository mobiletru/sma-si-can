#!/bin/bash
set -e

MODBUS_MODE="${MODBUS_MODE:-tcp}"
MODBUS_HOST="${MODBUS_HOST:-127.0.0.1}"
MODBUS_PORT="${MODBUS_PORT:-502}"
MODBUS_UNIT="${MODBUS_UNIT:-1}"
MODBUS_SERIAL="${MODBUS_SERIAL:-/dev/ttyUSB0}"
MODBUS_BAUD="${MODBUS_BAUD:-9600}"
MODBUS_REGISTER_MAP="${MODBUS_REGISTER_MAP:-modbus_register_map.json}"
MODBUS_POLL_INTERVAL="${MODBUS_POLL_INTERVAL:-0.5}"

CAN_INTERFACE="${CAN_INTERFACE:-pcan}"
CAN_CHANNEL="${CAN_CHANNEL:-PCAN_USBCH1}"
CAN_SEND_INTERVAL="${CAN_SEND_INTERVAL:-0.05}"
LOG_LEVEL="${LOG_LEVEL:-INFO}"

echo "Starting Modbus → SMA SI CAN converter"
echo "Modbus: ${MODBUS_MODE} ${MODBUS_HOST}:${MODBUS_PORT} unit=${MODBUS_UNIT}"
echo "CAN: ${CAN_INTERFACE} ${CAN_CHANNEL}"
echo "Register map: ${MODBUS_REGISTER_MAP}"

exec python3 modbus_to_si_converter.py \
  --modbus-mode "$MODBUS_MODE" \
  --modbus-host "$MODBUS_HOST" \
  --modbus-port "$MODBUS_PORT" \
  --modbus-unit "$MODBUS_UNIT" \
  --modbus-serial "$MODBUS_SERIAL" \
  --modbus-baud "$MODBUS_BAUD" \
  --register-map "$MODBUS_REGISTER_MAP" \
  --can-interface "$CAN_INTERFACE" \
  --can-channel "$CAN_CHANNEL" \
  --poll-interval "$MODBUS_POLL_INTERVAL" \
  --send-interval "$CAN_SEND_INTERVAL" \
  --log-level "$LOG_LEVEL"