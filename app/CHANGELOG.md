# Changelog

5.4.0 下線跳過機制

All notable changes to the "Ampinvt MPPT Monitor" project will be documented in this file.

## [5.3.0] - 2023-10-27

### 🚀 Major Features (核心功能)
* **Modular Architecture (模組化架構)**: 
    * 全面重構程式碼，將邏輯拆分為 `Command Handler` (指令處理)、`Protocol` (通訊協議)、`HA Manager` (探索與狀態) 與 `Core Logging` (日誌系統)。
    * 大幅提升程式碼可讀性與維護性。
* **Smart Time Sync (智慧時間同步)**: 
    * 新增 `timezone_offset` 設定，解決 Docker 容器時區偏差問題。
    * 支援透過 HA 按鈕一鍵將正確的當地時間寫入 MPPT 設備 (0xDF 指令)。
* **Full Bi-directional Control (全雙向控制)**:
    * 支援 `Switch` (負載/充電開關)、`Button` (消音/背光/同步)、`Number` (電壓/電流設定)、`Select` (電池類型/模式切換)。
    * 新增 `D0` 寫入指令支援，可修改保護電壓與充電參數。

### 🛡️ Robustness & Safety (容錯與安全)
* **Watchdog Mechanism**: 內建連續失敗計數器，偵測 RS485 卡死時自動重啟系統。
* **MQTT LWT (Last Will)**: 支援 MQTT 遺囑，程式斷線時 Home Assistant 實體自動變為 `Unavailable` (灰色)，避免數據誤導。
* **Graceful Exit**: 支援 Docker `SIGTERM` 訊號，關閉前可選擇性清除 HA 上的實體註冊 (`reset_discovery_on_exit`)。
* **Config Validation**: 增強 `config.yaml` 讀取邏輯，具備自動防呆與型別轉換功能。

### 📝 Logging (日誌系統)
* **Structured Logging**: 引入 Python `logging` 模組，取代 `print()`。
* **Log Rotation**: 支援標準輸出 (Stdout) 日誌分級 (INFO/DEBUG/WARNING/ERROR)，方便 Docker logs 查看與除錯。

### 🐛 Fixes (修正)
* 修正 `Select` 實體無法解析帶有 ID 前綴 (如 "3:鋰電池") 的選項問題。
* 修正 Paho MQTT V2 版本回調函式參數不匹配導致的連線錯誤。
* 修正寄存器地址對齊問題 (例如低壓恢復電壓)。

---

## [4.0.0] - Previous Stable
* Initial support for Modbus read/write operations.
* Basic Home Assistant MQTT Discovery.
