#!/bin/bash

set -e

CONFIG_PATH=/data/options.json

CAN_INTERFACE=$(jq --raw-output '.can_interface // "socketcan"' $CONFIG_PATH)
CAN_CHANNEL=$(jq --raw-output '.can_channel // "can0"' $CONFIG_PATH)
HA_HOST=$(jq --raw-output '.ha_host // "localhost"' $CONFIG_PATH)
HA_PORT=$(jq --raw-output '.ha_port // 8123' $CONFIG_PATH)
LOG_LEVEL=$(jq --raw-output '.log_level // "info"' $CONFIG_PATH)

echo "Starting SMA SI 6048 - EVTV Bridge"
echo "CAN Interface: $CAN_INTERFACE"
echo "CAN Channel: $CAN_CHANNEL"
echo "Home Assistant: $HA_HOST:$HA_PORT"
echo "Log Level: $LOG_LEVEL"

export CAN_INTERFACE=$CAN_INTERFACE
export CAN_CHANNEL=$CAN_CHANNEL
export HA_HOST=$HA_HOST
export HA_PORT=$HA_PORT
export LOG_LEVEL=$LOG_LEVEL

# For SocketCAN, bring the link up at 500 kbit/s (PCAN-USB on HAOS is can0).
# Best-effort: requires NET_ADMIN and iproute2; ignore if already up / no perms.
if [ "$CAN_INTERFACE" = "socketcan" ]; then
    ip link set "$CAN_CHANNEL" type can bitrate 500000 2>/dev/null || true
    ip link set "$CAN_CHANNEL" up 2>/dev/null || true
fi

python3 /app/bridge_direct.py \
    --can-interface "$CAN_INTERFACE" \
    --can-channel "$CAN_CHANNEL" \
    --ha-host "$HA_HOST" \
    --ha-port "$HA_PORT" \
    --log-level "$LOG_LEVEL"
