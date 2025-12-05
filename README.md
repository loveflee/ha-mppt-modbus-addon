🌞 Ampinvt MPPT Solar Controller Monitor (Home Assistant Add-on)這是一個專為 Home Assistant 設計的 Add-on，用於監控 佛山金廣源 (Ampinvt) MPPT 太陽能控制器。它透過 Modbus TCP (RS485 轉乙太網/WiFi) 讀取數據，並利用 MQTT Discovery 自動將感測器註冊到 Home Assistant，無需手動編寫 YAML 設定。✨ 主要功能🚀 工業級連線穩定性：內建 TCP 封包重組機制 (_recv_fixed)，解決 WiFi/RS485 傳輸過程中的封包碎片化 (Fragmentation) 問題。自動髒數據清洗 (Flush Buffer)，防止讀取到過期的錯誤數值。支援斷線自動重連與 MQTT Last Will (LWT) 狀態監控。📊 完整數據監控：支援 0xB1 全參數協議 (93 Bytes)，數據最完整。自動計算瞬時功率 (Watts = V * I)，補足部分舊款韌體未提供功率數據的問題。監控 PV 電壓、電池電壓、電流、溫度、日發電量、總發電量。即時顯示錯誤狀態 (過壓、過溫、過充等)。⚙️ 遠端控制與設定：支援透過 HA 介面遠端開關負載 (Load ON/OFF)。可調整充電參數 (如：電池類型、均充/浮充電壓、限流設定)。🔌 多設備支援：單一 Add-on 可輪詢多台 MPPT (透過 slave_ids 設定，例如 1, 2, 3)。🛠️ 硬體需求Ampinvt MPPT 控制器 (確認支援 RS485 通訊)。RS485 轉 乙太網/WiFi 模組 (例如：Elfin EW11, USR-TCP232 等)。⚠️ 重要設定：模組必須設定為 TCP Server 模式，並且開啟 透明傳輸 (Transparent Mode)。Home Assistant (OS 或 Supervised 版本，需支援 Add-on Store)。MQTT Broker (例如 HA 內建的 Mosquitto broker)。📥 安裝步驟在 Home Assistant 中，前往 設定 > Add-ons > Add-on Store。點擊右上角的三個點 ... > Repositories。輸入本專案的 GitHub 網址：[https://github.com/loveflee/ha-mppt-modbus-addon](https://github.com/loveflee/ha-mppt-modbus-addon)
點擊 Add。重新整理頁面，找到 "Ampinvt MPPT Monitor" 並點擊安裝。⚙️ 設定說明 (Configuration)安裝後，請至 Add-on 的 Configuration 頁籤進行設定：參數說明範例modbus_hostRS485 轉接器的 IP 地址192.168.1.100modbus_portRS485 轉接器的 Port502slave_idsMPPT 設備 ID (支援多台，用逗號分隔)1, 2, 3mqtt_hostMQTT Broker IP (通常是 HA 的 IP)core-mosquittomqtt_usernameMQTT 帳號 (若無可留空)mqtt_usermqtt_passwordMQTT 密碼 (若無可留空)passwordnode_id用於 MQTT Topic 的識別名稱 (建議英文)wifi01poll_interval每一輪掃描後的休息秒數3delay_between_units多台設備輪詢時的間隔秒數0.5debug_mode是否開啟詳細日誌 (會顯示 Hex 數據)false⚠️ 常見問題 (FAQ)Q1: 為什麼日誌顯示 "Length Error" 或連線超時？請檢查您的 RS485 轉接器設定。務必確認 Baud Rate (波特率) 與 MPPT 設定一致 (預設通常是 9600)，且模式為 None (無校驗), 8 Data bits, 1 Stop bit。確認轉接器工作模式為 Transparent (透傳)，不要開啟 Modbus RTU <-> TCP 轉換功能 (因為此 MPPT 使用非標準 Modbus 封包)。Q2: 為什麼找不到實體 (Entity)？請確認您的 MQTT 設定正確。如果您更換了 node_id，HA 會視為新設備。本程式設計為相容舊版 ID 結構，以保留歷史數據。Q3: 支援哪些型號？測試於佛山金廣源 (Ampinvt) 60A MPPT 控制器 (黑色/藍色外殼版本)。支援 V1.1 通訊協議 (指令 0xB1)。📜 LicenseMIT License. 歡迎 Fork 與提交 PR 改進
建議日出重啟附加元件 </br>
腳本
```
sequence:
  - action: hassio.addon_restart
    metadata: {}
    data:
      addon: 34caa00e_mppt_modbus_mqtt_poller
alias: 重啟附加元件modbus app
description: ""
```
自動化
```
alias: 日出 前20分鐘重啟 mppt 讀取
description: ""
triggers:
  - event: sunrise
    offset: "-00:20:00"
    trigger: sun
conditions: []
actions:
  - action: hassio.addon_restart
    metadata: {}
    data:
      addon: 34caa00e_mppt_modbus_mqtt_poller
mode: single

```
自動化2
```
alias: HA 重啟後 重啟讀取 mppt
description: ""
triggers:
  - event: start
    trigger: homeassistant
conditions:
  - condition: time
    after: "05:00:00"
    before: "21:00:00"
actions:
  - delay:
      hours: 0
      minutes: 0
      seconds: 30
      milliseconds: 0
    enabled: true
  - data:
      addon: 34caa00e_mppt_modbus_mqtt_poller
    action: hassio.addon_restart
mode: single
```
附加元件的日誌訊息更新較慢推薦使用 mqtt explorer 觀察訊息
https://mqtt-explorer.com/
