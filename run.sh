#!/bin/bash

set -e

# Load options from add-on config
CONFIG_PATH=/data/options.json

RELAY_HOST=$(jq --raw-output '.relay_host // "nas.local"' $CONFIG_PATH)
RELAY_PORT=$(jq --raw-output '.relay_port // 9001' $CONFIG_PATH)
MQTT_HOST=$(jq --raw-output '.mqtt_host // "localhost"' $CONFIG_PATH)
MQTT_PORT=$(jq --raw-output '.mqtt_port // 1883' $CONFIG_PATH)
LOG_LEVEL=$(jq --raw-output '.log_level // "info"' $CONFIG_PATH)

echo "Starting SMA SI CAN Bridge (Relay Client)"
echo "Relay Server: $RELAY_HOST:$RELAY_PORT"
echo "MQTT Broker: $MQTT_HOST:$MQTT_PORT"
echo "Log Level: $LOG_LEVEL"

# Export config as environment variables
export RELAY_HOST=$RELAY_HOST
export RELAY_PORT=$RELAY_PORT
export MQTT_HOST=$MQTT_HOST
export MQTT_PORT=$MQTT_PORT

# Run the relay client
python3 /app/relay_client.py \
    --relay-host "$RELAY_HOST" \
    --relay-port "$RELAY_PORT" \
    --mqtt-host "$MQTT_HOST" \
    --mqtt-port "$MQTT_PORT"
