#!/bin/bash

set -e

CONFIG_PATH=/data/options.json

RELAY_HOST=$(jq --raw-output '.relay_host // "nas.local"' $CONFIG_PATH)
RELAY_PORT=$(jq --raw-output '.relay_port // 9001' $CONFIG_PATH)
HA_HOST=$(jq --raw-output '.ha_host // "localhost"' $CONFIG_PATH)
HA_PORT=$(jq --raw-output '.ha_port // 8123' $CONFIG_PATH)
LOG_LEVEL=$(jq --raw-output '.log_level // "info"' $CONFIG_PATH)

echo "Starting SMA SI EVTV Converter"
echo "Relay: $RELAY_HOST:$RELAY_PORT"
echo "Home Assistant: $HA_HOST:$HA_PORT"
echo "Log Level: $LOG_LEVEL"

export RELAY_HOST=$RELAY_HOST
export RELAY_PORT=$RELAY_PORT
export HA_HOST=$HA_HOST
export HA_PORT=$HA_PORT
export LOG_LEVEL=$LOG_LEVEL

python3 /app/converter_addon.py \
    --relay-host "$RELAY_HOST" \
    --relay-port "$RELAY_PORT" \
    --ha-host "$HA_HOST" \
    --ha-port "$HA_PORT" \
    --log-level "$LOG_LEVEL"
