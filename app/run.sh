#!/usr/bin/env bash
# ==============================================================================
# 🚀 Home Assistant Add-on 啟動腳本
# ==============================================================================

set -e

# 定義路徑
OPTIONS_PATH="/data/options.json"
CONFIG_PATH="/app/config.yaml"

echo "--- [Init] Add-on 啟動中 ---"

# 1. 檢查並載入設定
if [ -f "$OPTIONS_PATH" ]; then
    echo "⚙️  讀取 HA 設定 (/data/options.json)..."
    
    # Debug: 印出原始 JSON 結構以供除錯 (可選)
    # cat $OPTIONS_PATH

    # 讀取 Modbus 參數 (注意：路徑必須對應 config.yaml 的巢狀結構)
    MODBUS_HOST=$(jq -r '.modbus.host // "192.168.106.12"' $OPTIONS_PATH)
    MODBUS_PORT=$(jq -r '.modbus.port // 502' $OPTIONS_PATH)
    MODBUS_TIMEOUT=$(jq -r '.modbus.timeout // 3.0' $OPTIONS_PATH)
    RETRY_DELAY=$(jq -r '.modbus.retry_delay // 2.0' $OPTIONS_PATH)
    
    # 處理 Unit IDs: 從字串 "1,2,3" 轉為 JSON 陣列 [1,2,3]
    # 這裡讀取的是 .modbus.unit_ids
    SLAVE_IDS=$(jq -r '.modbus.unit_ids' $OPTIONS_PATH | jq -R 'split(",") | map(select(length>0) | tonumber) | if length==0 then [1] else . end')

    # 讀取 MQTT 參數
    MQTT_HOST=$(jq -r '.mqtt.broker // "core-mosquitto"' $OPTIONS_PATH)
    MQTT_PORT=$(jq -r '.mqtt.port // 1883' $OPTIONS_PATH)
    MQTT_USER=$(jq -r '.mqtt.username // ""' $OPTIONS_PATH)
    MQTT_PASS=$(jq -r '.mqtt.password // ""' $OPTIONS_PATH)
    DISC_PREFIX=$(jq -r '.mqtt.discovery_prefix // "homeassistant"' $OPTIONS_PATH)
    NODE_ID=$(jq -r '.mqtt.node_id // "wifi01"' $OPTIONS_PATH)
    DEV_NAME=$(jq -r '.mqtt.device_name // "Ampinvt MPPT"' $OPTIONS_PATH)

    # 讀取 Polling 參數
    POLL_INT=$(jq -r '.polling.poll_interval // 3' $OPTIONS_PATH)
    DELAY_UNIT=$(jq -r '.polling.delay_between_units // 0.5' $OPTIONS_PATH)
    
    # 讀取 Debug 參數
    DEBUG_MODE=$(jq -r '.debug // false' $OPTIONS_PATH)

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
  retry_delay: $RETRY_DELAY

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
