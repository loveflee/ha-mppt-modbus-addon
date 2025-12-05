#!/usr/bin/env bash
# ==============================================================================
# 🚀 Home Assistant Add-on 啟動腳本
# ==============================================================================

set -e

# 定義路徑
OPTIONS_PATH="/data/options.json"
CONFIG_PATH="/app/config.yaml"

echo "--- [Init] Add-on 啟動中 (v1.7.2) ---"

# 1. 檢查並載入設定
if [ -f "$OPTIONS_PATH" ]; then
    echo "⚙️  讀取 HA 設定 (/data/options.json)..."
    
    # 讀取基礎參數 (使用 jq -r 去除引號)
    MODBUS_HOST=$(jq -r '.modbus_host // "192.168.106.12"' $OPTIONS_PATH)
    MODBUS_PORT=$(jq -r '.modbus_port // 502' $OPTIONS_PATH)
    MODBUS_TIMEOUT=$(jq -r '.modbus_timeout // 3.0' $OPTIONS_PATH)
    
    # 處理 Slave IDs: 將 "1,2,3" 轉為 JSON 陣列 [1,2,3]
    SLAVE_IDS=$(jq -r '.slave_ids' $OPTIONS_PATH | jq -R 'split(",") | map(select(length>0) | tonumber) | if length==0 then [1] else . end')

    MQTT_HOST=$(jq -r '.mqtt_host // "core-mosquitto"' $OPTIONS_PATH)
    MQTT_PORT=$(jq -r '.mqtt_port // 1883' $OPTIONS_PATH)
    MQTT_USER=$(jq -r '.mqtt_username // ""' $OPTIONS_PATH)
    MQTT_PASS=$(jq -r '.mqtt_password // ""' $OPTIONS_PATH)
    DISC_PREFIX=$(jq -r '.discovery_prefix // "homeassistant"' $OPTIONS_PATH)
    
    NODE_ID=$(jq -r '.node_id // "wifi01"' $OPTIONS_PATH)
    DEV_NAME=$(jq -r '.device_name // "Ampinvt MPPT"' $OPTIONS_PATH)

    POLL_INT=$(jq -r '.poll_interval // 3' $OPTIONS_PATH)
    DELAY_UNIT=$(jq -r '.delay_between_units // 0.5' $OPTIONS_PATH)
    DEBUG_MODE=$(jq -r '.debug_mode // false' $OPTIONS_PATH)

    # 2. 動態生成 config.yaml 給 Python 使用
    echo "📄 生成 /app/config.yaml..."
    cat > "$CONFIG_PATH" <<EOF
system:
  debug: $DEBUG_MODE

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

polling:
  poll_interval: $POLL_INT
  delay_between_units: $DELAY_UNIT
EOF

else
    echo "⚠️  警告：找不到 $OPTIONS_PATH，如果是本地測試請忽略。"
fi

# 3. 檢查 Python 檔案是否存在 (除錯用)
if [ ! -f "/app/main.py" ]; then
    echo "❌ 嚴重錯誤：找不到 /app/main.py！"
    echo "當前目錄內容 (/app):"
    ls -al /app
    exit 1
fi

echo "🚀 啟動 Python 主程式..."
# 使用 -u 確保日誌即時輸出
exec python3 -u /app/main.py
