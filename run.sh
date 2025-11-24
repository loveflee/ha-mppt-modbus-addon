#!/usr/bin/env bash
# run.sh
set -e

echo "📦 MPPT Modbus MQTT Poller Add-on starting..."

# 確保在 /app 執行
cd /app

# 從 HA Add-on 的 /data/options.json 載入設定（給 main.py 也會用的環境變數）
if [ -f /data/options.json ]; then
  echo "--- 從 /data/options.json 載入設定 ---"

  export MODBUS_HOST=$(jq -r '.modbus_host' /data/options.json)
  export MODBUS_PORT=$(jq -r '.modbus_port' /data/options.json)

  export MQTT_BROKER_HOST=$(jq -r '.mqtt_host' /data/options.json)
  export MQTT_PORT=$(jq -r '.mqtt_port' /data/options.json)
  export MQTT_USERNAME=$(jq -r '.mqtt_username' /data/options.json)
  export MQTT_PASSWORD=$(jq -r '.mqtt_password' /data/options.json)

  export SLAVE_IDS=$(jq -r '.slave_ids' /data/options.json)
  export POLL_INTERVAL_SECONDS=$(jq -r '.poll_interval_seconds' /data/options.json)
  export DEVICE_DELAY_MS=$(jq -r '.device_delay_ms' /data/options.json)

  export NODE_ID=$(jq -r '.node_id' /data/options.json)
  export MODULE_NAME=$(jq -r '.module_name' /data/options.json)

  export LATITUDE=$(jq -r '.latitude' /data/options.json)
  export LONGITUDE=$(jq -r '.longitude' /data/options.json)

  # 🕒 新增：讀取 timezone，若有設定就直接覆蓋 TZ 環境變數
  TZ_OPTION=$(jq -r '.timezone // empty' /data/options.json)
  if [ -n "$TZ_OPTION" ]; then
    export TZ="$TZ_OPTION"
  fi

  # 📝 新增：log_level（讓 main.py 去處理 logging 設定）
  export LOG_LEVEL=$(jq -r '.log_level // "INFO"' /data/options.json)

else
  echo "[ERROR] 找不到 /data/options.json，無法載入設定" >&2
fi

# 額外 debug：顯示目前目錄與內容
echo "當前工作目錄：$(pwd)"
echo "目錄內容："
ls -al

# 檢查 main.py 是否存在
if [ ! -f "main.py" ]; then
  echo "[ERROR] /app/main.py 不存在，無法啟動程式" >&2
  exit 1
fi

# 設定時區（如果有 TZ 環境變數）
if [ -n "${TZ}" ]; then
  export TZ="${TZ}"
fi

echo "--- 正在啟動 MPPT Modbus Poller 主程式 ---"
echo "MQTT Broker: ${MQTT_BROKER_HOST}:${MQTT_PORT}"
echo "Modbus Server: ${MODBUS_HOST}:${MODBUS_PORT}"
echo "Slave IDs to poll: ${SLAVE_IDS}"
echo "HA Node ID: ${NODE_ID}"
echo "TZ: ${TZ}"
echo "LOG_LEVEL: ${LOG_LEVEL}"

# 執行主程式
python3 /app/main.py
