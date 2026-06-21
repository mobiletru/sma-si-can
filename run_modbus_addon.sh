#!/bin/bash
set -e

CONFIG_PATH=/data/options.json

MODBUS_MODE=$(jq --raw-output '.modbus_mode // "tcp"' "$CONFIG_PATH")
MODBUS_HOST=$(jq --raw-output '.modbus_host // "127.0.0.1"' "$CONFIG_PATH")
MODBUS_PORT=$(jq --raw-output '.modbus_port // 502' "$CONFIG_PATH")
MODBUS_UNIT=$(jq --raw-output '.modbus_unit // 1' "$CONFIG_PATH")
MODBUS_SERIAL=$(jq --raw-output '.modbus_serial // "/dev/ttyUSB0"' "$CONFIG_PATH")
MODBUS_BAUD=$(jq --raw-output '.modbus_baud // 9600' "$CONFIG_PATH")
REGISTER_MAP_PATH=$(jq --raw-output '.register_map_path // "/config/modbus_register_map.json"' "$CONFIG_PATH")
CAN_INTERFACE=$(jq --raw-output '.can_interface // "pcan"' "$CONFIG_PATH")
CAN_CHANNEL=$(jq --raw-output '.can_channel // "PCAN_USBCH1"' "$CONFIG_PATH")
POLL_INTERVAL=$(jq --raw-output '.poll_interval // "0.5"' "$CONFIG_PATH")
SEND_INTERVAL=$(jq --raw-output '.send_interval // "0.05"' "$CONFIG_PATH")
LOG_LEVEL=$(jq --raw-output '.log_level // "info"' "$CONFIG_PATH")

if [ ! -f "$REGISTER_MAP_PATH" ]; then
    echo "Register map not found at $REGISTER_MAP_PATH, falling back to bundled default"
    REGISTER_MAP_PATH="/app/modbus_register_map.json"
fi

echo "Starting SMA SI Modbus Bridge"
echo "Modbus: $MODBUS_MODE"
if [ "$MODBUS_MODE" = "tcp" ]; then
    echo "Modbus target: $MODBUS_HOST:$MODBUS_PORT unit=$MODBUS_UNIT"
else
    echo "Modbus target: serial=$MODBUS_SERIAL baud=$MODBUS_BAUD unit=$MODBUS_UNIT"
fi
echo "CAN: $CAN_INTERFACE $CAN_CHANNEL"
echo "Register map: $REGISTER_MAP_PATH"
echo "Poll interval: $POLL_INTERVAL"
echo "Send interval: $SEND_INTERVAL"
echo "Log level: $LOG_LEVEL"

exec python3 /app/modbus_to_si_converter.py \
    --modbus-mode "$MODBUS_MODE" \
    --modbus-host "$MODBUS_HOST" \
    --modbus-port "$MODBUS_PORT" \
    --modbus-unit "$MODBUS_UNIT" \
    --modbus-serial "$MODBUS_SERIAL" \
    --modbus-baud "$MODBUS_BAUD" \
    --register-map "$REGISTER_MAP_PATH" \
    --can-interface "$CAN_INTERFACE" \
    --can-channel "$CAN_CHANNEL" \
    --poll-interval "$POLL_INTERVAL" \
    --send-interval "$SEND_INTERVAL" \
    --log-level "$LOG_LEVEL"
