#!/usr/bin/env bash
set -e

OPTIONS_PATH="/data/options.json"
CONFIG_PATH="/app/config.yaml"

echo "--- [Init] Starting Ampinvt MPPT Modbus MQTT Poller V7.0.3 ---"

if [ -f "$OPTIONS_PATH" ]; then
    echo "⚙️  Loading HA options..."

    DEBUG_MODE=$(jq -r '.debug // false' "$OPTIONS_PATH")
    TZ_OFFSET=$(jq -r '.timezone_offset // 8' "$OPTIONS_PATH")
    RESET_ON_EXIT=$(jq -r '.reset_discovery_on_exit // false' "$OPTIONS_PATH")

    LANGUAGE=$(jq -r '.language // "tw"' "$OPTIONS_PATH")

    # 🟢 黑名單（故障懲罰）
    FAIL_THRESHOLD=$(jq -r '.blacklist.fail_threshold // 20' "$OPTIONS_PATH")
    ISOLATION_TIME=$(jq -r '.blacklist.isolation_time // 60' "$OPTIONS_PATH")
    LONG_DELAY_THRESHOLD=$(jq -r '.blacklist.long_delay_threshold // 10' "$OPTIONS_PATH")
    LONG_DELAY=$(jq -r '.blacklist.long_delay // 3600' "$OPTIONS_PATH")

    # 🟢 Modbus
    MODBUS_HOST=$(jq -r '.modbus.host // "192.168.106.12"' "$OPTIONS_PATH")
    MODBUS_PORT=$(jq -r '.modbus.port // 502' "$OPTIONS_PATH")
    MODBUS_TIMEOUT=$(jq -r '.modbus.timeout // 3.0' "$OPTIONS_PATH")
    MODBUS_RETRY=$(jq -r '.modbus.retry_delay // 2.0' "$OPTIONS_PATH")

    # unit_ids: "1,2,3" → [1,2,3]
    SLAVE_IDS=$(jq -r '.modbus.unit_ids // "1"' "$OPTIONS_PATH" | jq -R 'split(",") | map(select(length>0) | tonumber)')

    # 🟢 MQTT
    MQTT_HOST=$(jq -r '.mqtt.broker // "core-mosquitto"' "$OPTIONS_PATH")
    MQTT_PORT=$(jq -r '.mqtt.port // 1883' "$OPTIONS_PATH")
    MQTT_USER=$(jq -r '.mqtt.username // ""' "$OPTIONS_PATH")
    MQTT_PASS=$(jq -r '.mqtt.password // ""' "$OPTIONS_PATH")
    DISC_PREFIX=$(jq -r '.mqtt.discovery_prefix // "homeassistant"' "$OPTIONS_PATH")
    NODE_ID=$(jq -r '.mqtt.node_id // "wifi01"' "$OPTIONS_PATH")
    DEVICE_NAME=$(jq -r '.mqtt.device_name // "ampinvt_mppt"' "$OPTIONS_PATH")

    # 🟢 Polling
    POLL_INT=$(jq -r '.polling.poll_interval // 3' "$OPTIONS_PATH")
    DELAY_UNIT=$(jq -r '.polling.delay_between_units // 0.5' "$OPTIONS_PATH")

    #############################
    # 📌 生成 Python 用的 config.yaml
    #############################

cat > "$CONFIG_PATH" <<EOF
system:
  debug: ${DEBUG_MODE}
  timezone_offset: ${TZ_OFFSET}
  reset_discovery_on_exit: ${RESET_ON_EXIT}
  language: "${LANGUAGE}"

blacklist:
  fail_threshold: ${FAIL_THRESHOLD}
  isolation_time: ${ISOLATION_TIME}
  long_delay_threshold: ${LONG_DELAY_THRESHOLD}
  long_delay: ${LONG_DELAY}

modbus:
  host: "${MODBUS_HOST}"
  port: ${MODBUS_PORT}
  unit_ids: ${SLAVE_IDS}
  timeout: ${MODBUS_TIMEOUT}
  retry_delay: ${MODBUS_RETRY}

mqtt:
  broker: "${MQTT_HOST}"
  port: ${MQTT_PORT}
  username: "${MQTT_USER}"
  password: "${MQTT_PASS}"
  discovery_prefix: "${DISC_PREFIX}"
  node_id: "${NODE_ID}"
  device_name: "${DEVICE_NAME}"

polling:
  poll_interval: ${POLL_INT}
  delay_between_units: ${DELAY_UNIT}
EOF

else
    echo "⚠️  No options.json found, using existing config.yaml"
fi

echo "🚀 Launching Python..."
exec python3 /app/main.py
