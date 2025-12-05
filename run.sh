#!/usr/bin/env bash
# ==============================================================================
# 🚀 Home Assistant Add-on 啟動腳本 (run.sh)
# 
# 功能：
# 1. 讀取 /data/options.json (使用者在 HA 網頁設定的參數)
# 2. 使用 jq 動態生成 /app/config.yaml (Python 程式需要的設定檔)
# 3. 處理 slave_ids 字串轉換為 JSON 陣列
# 4. 啟動 Python 主程式
# ==============================================================================

set -e

# 定義路徑
OPTIONS_PATH="/data/options.json"
CONFIG_PATH="/app/config.yaml"

echo "--- [Init] 正在初始化 Ampinvt MPPT Monitor ---"

# 檢查 options.json 是否存在 (本地測試時可能不存在)
if [ ! -f "$OPTIONS_PATH" ]; then
    echo "⚠️  警告：找不到 $OPTIONS_PATH，將使用預設 config.yaml 或環境變數"
else
    echo "⚙️  正在從 HA Add-on 設定生成 config.yaml..."

    # 1. 讀取基礎參數
    MODBUS_HOST=$(jq -r '.modbus_host' $OPTIONS_PATH)
    MODBUS_PORT=$(jq -r '.modbus_port' $OPTIONS_PATH)
    MODBUS_TIMEOUT=$(jq -r '.modbus_timeout // 3.0' $OPTIONS_PATH)
    
    # 2. 處理 Slave IDs (將字串 "1,2,3" 轉換為 JSON 陣列 [1,2,3])
    # 如果輸入為空，預設為 [1]
    SLAVE_IDS=$(jq -r '.slave_ids' $OPTIONS_PATH | jq -R 'split(",") | map(select(length>0) | tonumber) | if length==0 then [1] else . end')

    MQTT_HOST=$(jq -r '.mqtt_host' $OPTIONS_PATH)
    MQTT_PORT=$(jq -r '.mqtt_port' $OPTIONS_PATH)
    MQTT_USER=$(jq -r '.mqtt_username // ""' $OPTIONS_PATH)
    MQTT_PASS=$(jq -r '.mqtt_password // ""' $OPTIONS_PATH)
    DISC_PREFIX=$(jq -r '.discovery_prefix // "homeassistant"' $OPTIONS_PATH)
    NODE_ID=$(jq -r '.node_id // "ampinvt_gw"' $OPTIONS_PATH)
    DEV_NAME=$(jq -r '.device_name // "Ampinvt MPPT"' $OPTIONS_PATH)

    POLL_INT=$(jq -r '.poll_interval // 3' $OPTIONS_PATH)
    DELAY_UNIT=$(jq -r '.delay_between_units // 0.5' $OPTIONS_PATH)
    DEBUG_MODE=$(jq -r '.debug_mode // false' $OPTIONS_PATH)

    # 3. 生成 config.yaml
    # 注意：YAML 兼容 JSON 格式的陣列寫法，所以 SLAVE_IDS 直接填入即可
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

    echo "✅ config.yaml 生成完畢！內容預覽："
    # 遮蔽密碼後顯示內容
    sed 's/password: ".*"/password: "***"/' "$CONFIG_PATH"
fi

# 4. 檢查 Python 腳本是否存在
if [ ! -f "/app/main.py" ]; then
    echo "❌ 錯誤：找不到 /app/main.py，請檢查 Docker Image 建置是否正確。"
    exit 1
fi

echo "--------------------------------------------------------"
echo "🚀 啟動 Python 主程式..."
echo "--------------------------------------------------------"

# 執行 Python (使用 -u 參數確保日誌不被緩衝，即時輸出到 HA Console)
exec python3 -u /app/main.py
