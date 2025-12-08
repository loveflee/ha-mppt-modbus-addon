#!/usr/bin/env bash
set -e
OPTIONS_PATH="/data/options.json"
CONFIG_PATH="/app/config.yaml"

echo "--- [Init] Starting Ampinvt Monitor V7.0 ---"

if [ -f "$OPTIONS_PATH" ]; then
    echo "⚙️  Loading HA options..."
    DEBUG_MODE=$(jq -r '.debug // false' $OPTIONS_PATH)
    TZ_OFFSET=$(jq -r '.timezone_offset // 8' $OPTIONS_PATH)
    RESET_ON_EXIT=$(jq -r '.reset_discovery_on_exit // false' $OPTIONS_PATH)
    
    # 🟢 讀取語言 (預設 tw)
    LANGUAGE=$(jq -r '.language // "tw"' $OPTIONS_PATH)
    
    MODBUS_HOST=$(jq -r '.modbus.host // "192.168.106.12"' $OPTIONS_PATH)
    MODBUS_PORT=$(jq -r '.modbus.port // 502' $OPTIONS_PATH)
    MODBUS_TIMEOUT=$(jq -r '.modbus.timeout // 3.0' $OPTIONS_PATH)
    SLAVE_IDS=$(jq -r '.modbus.unit_ids' $OPTIONS_PATH | jq -R 'split(",") | map(select(length>0) | tonumber) | if length==0 then [1] else . end')
    MQTT_HOST=$(jq -r '.mqtt.broker // "core-mosquitto"' $OPTIONS_PATH)
    MQTT_PORT=$(jq -r '.mqtt.port // 1883' $OPTIONS_PATH)
    MQTT_USER=$(jq -r '.mqtt.username // ""' $OPTIONS_PATH)
    MQTT_PASS=$(jq -r '.mqtt.password // ""' $OPTIONS_PATH)
    DISC_PREFIX=$(jq -r '.mqtt.discovery_prefix // "homeassistant"' $OPTIONS_PATH)
    NODE_ID=$(jq -r '.mqtt.node_id // "wifi01"' $OPTIONS_PATH)
    DEV_NAME=$(jq -r '.mqtt.device_name // "Ampinvt MPPT"' $OPTIONS_PATH)
    POLL_INT=$(jq -r '.polling.poll_interval // 3' $OPTIONS_PATH)
    DELAY_UNIT=$(jq -r '.polling.delay_between_units // 0.5' $OPTIONS_PATH)

    cat > "$CONFIG_PATH" <<EOF
system:
  debug: $DEBUG_MODE
  timezone_offset: $TZ_OFFSET
  language: "$LANGUAGE"
modbus:
  host: "$MODBUS_HOST"
  port: $MODBUS_PORT
  unit_ids: $SLAVE_IDS
  timeout: $MODBUS_TIMEOUT
  retry_delay: 5.0
mqtt:
  broker: "$MQTT_HOST"
  port: $MQTT_PORT
  username: "$MQTT_USER"
  password: "$MQTT_PASS"
  discovery_prefix: "$DISC_PREFIX"
  node_id: "$NODE_ID"
  device_name: "$DEV_NAME"
  reset_discovery_on_exit: $RESET_ON_EXIT
polling:
  poll_interval: $POLL_INT
  delay_between_units: $DELAY_UNIT
EOF
else
    echo "⚠️  No options.json found, using existing config.yaml"
fi

echo "🚀 Launching Python..."
exec python3 /app/main.py
