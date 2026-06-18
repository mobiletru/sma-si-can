#!/bin/bash

set -e

CONFIG_PATH=/data/options.json

CAN_CHANNEL=$(jq --raw-output '.can_channel // "PCAN_USBCH1"' $CONFIG_PATH)
HA_HOST=$(jq --raw-output '.ha_host // "localhost"' $CONFIG_PATH)
HA_PORT=$(jq --raw-output '.ha_port // 8123' $CONFIG_PATH)
LOG_LEVEL=$(jq --raw-output '.log_level // "info"' $CONFIG_PATH)

echo "Starting SMA SI 6048 - EVTV Bridge"
echo "CAN Channel: $CAN_CHANNEL"
echo "Home Assistant: $HA_HOST:$HA_PORT"
echo "Log Level: $LOG_LEVEL"

export CAN_CHANNEL=$CAN_CHANNEL
export HA_HOST=$HA_HOST
export HA_PORT=$HA_PORT
export LOG_LEVEL=$LOG_LEVEL

python3 /app/bridge_direct.py \
    --can-channel "$CAN_CHANNEL" \
    --ha-host "$HA_HOST" \
    --ha-port "$HA_PORT" \
    --log-level "$LOG_LEVEL"
