# Changelog / 變更日誌

All notable changes to the "Ampinvt MPPT Monitor" project will be documented in this file.
本專案的所有重大變更都將記錄在此文件中

## [7.7.0] - Extreme Resilience Edition (2025-12-09)

### 🛡️ Resilience & Safety (韌性與安全性)

* **Multi-stage Failure Backoff (多階段懲罰性退避)**

  * **EN**: Implemented two failure thresholds (e.g., 10 and 20). After 10 consecutive failures, the retry interval is dramatically increased (e.g., to 1 hour) to reduce system load.
  * **TW**: 實作多階段故障退避。在連續失敗 10 次後，重試間隔會大幅增加 (例如增加到 1 小時)，以減少系統在無效連線上消耗的資源。

* **Dedicated Connectivity Sensor (專屬連線狀態感知器)**

  * **EN**: Added a `binary_sensor.connectivity` for each device. This explicitly tells the user whether the device is reachable, without confusing them with the `Unavailable` state of the main entity.
  * **TW**: 新增專屬的「連線狀態」二元感測器。此實體會明確告知使用者設備是否可達，比監控主實體的「不可用」狀態更清晰直觀。

* **Zero Trust Startup (零信任啟動)**

  * **EN**: Maintains the principle of not registering any HA entities until a successful, verified read of the device's hardware specifications (V7.4 feature).
  * **TW**: 延續零信任啟動原則。只有成功驗證設備的硬體規格後，才發送註冊資訊。

### 🛠️ Core Enhancements (核心增強)

* **Robust TCP Upgrade (強化 TCP 升級)**

  * **EN**: Updated `core_tcp.py` with enhanced `flush_buffer` (to clear residual noise) and strict timeout checking in `recv_fixed` to prevent kernel-level hangs.
  * **TW**: 升級 `core_tcp.py`，新增強化的 `flush_buffer` 機制，並在接收時實施更嚴格的超時檢查，以防止底層系統卡頓。

## [7.0.3] - Hardware Limit & Safety Edition (2025-12-08)

### 🚀 Major Features (核心功能)

* **Hardware Current Limit (硬體電流限流)**
    * **EN**: 
        * **Auto Detection**: Reads the hardware maximum charging current (Offset 24) from the device during startup.
        * **Dynamic Cap**: Automatically caps the "Set Max Charge Current" slider in Home Assistant to the device's physical limit (e.g., 60A), preventing invalid configuration.
    * **TW**: 
        * **自動偵測**: 啟動時自動讀取設備的「硬體最大充電電流」(Offset 24)。
        * **動態上限**: 自動將 Home Assistant 上「設定最大充電電流」滑桿的上限鎖定為設備的硬體極限 (例如 60A)，防止使用者設定超出規格的數值。

* **Directory Restructure (目錄結構重組)**
    * **EN**: Moved core logic to `/app` subdirectory while keeping `config.yaml` and `run.sh` at root to comply with Home Assistant Add-on repository standards.
    * **TW**: 將核心程式碼移至 `/app` 子目錄，並將 `config.yaml` 與 `run.sh` 保留在根目錄，以符合 Home Assistant Add-on 倉庫的標準結構。

* **Multi-language Support (多語系支援)**
    * **EN**: Added `language` option in `config.yaml` (tw/en). The system dynamically loads register maps, allowing users to switch between Traditional Chinese and English UIs.
    * **TW**: 在 `config.yaml` 新增 `language` 選項 (tw/en)。系統可動態載入暫存器地圖，允許使用者切換繁體中文或英文介面。

### 🛡️ Reliability (可靠性)

* **Dual Dynamic Range (雙重動態範圍)**
    * **EN**: Smartly adjusts voltage sliders based on battery type (Lead-Acid vs. Lithium) and string count. Lithium mode enforces a strict 14.6V/12V safety limit.
    * **TW**: 根據電池類型 (鉛酸/鋰電) 與串數智慧調整電壓滑桿範圍。鋰電模式下強制實施 14.6V/12V 的安全上限。

* **Interjection Polling (插隊輪詢)**
    * **EN**: Prioritizes MQTT commands over periodic polling to ensure instant control response (< 0.5s latency).
    * **TW**: 優先處理 MQTT 指令，確保控制操作即時響應 (延遲小於 0.5 秒)。

### 🐛 Fixes (修正)

* **EN**:
    * Fixed HA Add-on installation failure due to incorrect `config.yaml` path.
    * Fixed `KeyError` in HA Manager when registering switches.
    * Added `struct` import to properly decode hardware current limit (16-bit integer).
* **TW**:
    * 修正因 `config.yaml` 路徑錯誤導致 HA Add-on 無法安裝的問題。
    * 修正 HA Manager 在註冊開關時發生的 `KeyError`。
    * 新增 `struct` 模組引用，以正確解碼硬體電流限制數值 (16位元整數)。

---


## [5.7.1] - Smart Voltage Range Edition (2025-12-08)

### 🚀 Major Features (核心功能)

* **Dual Dynamic Range (雙重動態範圍)**
    * **EN**: 
        * **Auto Detection**: Automatically scans battery count (1-8S) and type (Lead-Acid/Lithium) on startup.
        * **Smart Slider**: Automatically scales Home Assistant voltage sliders based on battery count (e.g., 12V range vs 48V range).
        * **Lithium Safety**: Enforces a strict 14.6V limit (per 12V unit) for Lithium Iron Phosphate (LiFePO4) batteries to prevent overcharging.
    * **TW**: 
        * **自動偵測**: 啟動時自動掃描電池串數 (1-8串) 與類型 (鉛酸/鋰電)。
        * **智慧滑桿**: 根據電池串數自動縮放 HA 電壓設定範圍 (例如 12V 系統與 48V 系統會看到不同的安全範圍)。
        * **鐵鋰安全**: 針對磷酸鐵鋰電池實施嚴格的電壓上限 (每 12V 單位限制在 14.6V)，防止誤操作導致過充危險。

* **Interjection Polling (插隊輪詢)**
    * **EN**: Implemented a "Check Command -> Read Data" loop logic. Ensures MQTT commands are processed immediately before each device read, reducing control latency to < 0.5s.
    * **TW**: 實作「先檢查指令 -> 再讀取數據」的迴圈邏輯。確保 MQTT 指令在每次讀取設備前優先處理，將控制延遲降至 0.5 秒內。

* **Socket Core (同步核心)**
    * **EN**: Reverted to blocking `socket` with `TCP_NODELAY` for maximum physical layer stability with RS485 adapters.
    * **TW**: 回歸使用阻塞式 `socket` 搭配 `TCP_NODELAY`，以獲得對 RS485 轉接器最佳的物理層穩定性 (解決 Asyncio 與老舊硬體的時序相容問題)。

### 🛡️ Reliability (可靠性)

* **Startup Scan (啟動掃描)**
    * **EN**: Performs a synchronous scan of all devices at startup to populate device details before sending HA discovery config.
    * **TW**: 程式啟動時執行同步掃描，在發送 HA 註冊資訊前先取得正確的設備詳情。

* **Write-Verify (寫入回讀)**
    * **EN**: Automatically triggers a data read (`Read B1`) immediately after a successful parameter write (`Write D0`). HA entities update instantly after setting a value.
    * **TW**: 在成功寫入參數 (Write D0) 後，自動觸發數據讀取 (Read B1)。讓 Home Assistant 實體在設定後立即更新數值，無需等待下一輪輪詢。

* **Robust Config (強健設定)**
    * **EN**: Enhanced `config.yaml` parser that automatically fixes malformed `unit_ids` (e.g., handles "1, 2", [1, 2], or single integer 1).
    * **TW**: 增強 `config.yaml` 解析器，具備自動防呆機制，能自動修正格式錯誤的 `unit_ids` (例如處理字串 "1, 2"、列表 [1, 2] 或單一整數 1)。

### 🐛 Fixes (修正)

* **EN**:
    * Fixed `KeyError` in HA Manager when registering switches.
    * Fixed `0x24` -> `0x26` register mapping error.
    * Fixed "No Response" issue by adding pre-write delay (0.3s) and auto-retry logic.
* **TW**:
    * 修正 `ha_manager.py` 在註冊開關/按鈕時發生的 `KeyError` 錯誤。
    * 修正 `0x24` 暫存器地址錯誤 (過放恢復電壓正確位置應為 `0x26`)。
    * 修正寫入無回應問題，新增「寫入前緩衝 (0.3s)」與「自動重試」機制。
## [5.6.0] - Sweet Spot Edition (2025-12-7)

### 🚀 Major Features (核心功能)

* **Interjection Polling (插隊輪詢)**
    * **EN**: Implemented a "Check Command -> Read Data" loop logic. Ensures MQTT commands are processed immediately before each device read, reducing control latency to < 3s.
    * **TW**: 實作「先檢查指令 -> 再讀取數據」的迴圈邏輯。確保 MQTT 指令在每次讀取設備前優先處理，將控制延遲降至 3 秒內。

* **Immediate Read-Back (立即回讀)**
    * **EN**: Automatically triggers a data read (`Read B1`) immediately after a successful parameter write (`Write D0`). HA entities update instantly after setting a value.
    * **TW**: 在成功寫入參數 (Write D0) 後，自動觸發數據讀取 (Read B1)。讓 Home Assistant 實體在設定後立即更新數值，無需等待下一輪輪詢。

* **Robust Configuration (強健設定)**
    * **EN**: Enhanced `config.yaml` parser that automatically fixes malformed `unit_ids` (e.g., handles "1, 2", [1, 2], or single integer 1).
    * **TW**: 增強 `config.yaml` 解析器，具備自動防呆機制，能自動修正格式錯誤的 `unit_ids` (例如處理字串 "1, 2"、列表 [1, 2] 或單一整數 1)。

* **Smart Time Sync (智慧時間同步)**
    * **EN**: Supports `timezone_offset` configuration to sync correct local time to MPPT devices (Critical for timer-based load control).
    * **TW**: 支援 `timezone_offset` 設定，解決 Docker 時區問題，可將正確的當地時間同步至 MPPT 設備 (對時控負載功能至關重要)。

### 🛡️ Architecture & Stability (架構與穩定性)

* **Socket-based Core (Socket 核心)**
    * **EN**: Reverted to blocking `socket` with `TCP_NODELAY` for maximum physical layer stability with RS485 adapters.
    * **TW**: 回歸使用阻塞式 `socket` 搭配 `TCP_NODELAY`，以獲得對 RS485 轉接器最佳的物理層穩定性 (解決 Asyncio 與老舊硬體的時序相容問題)。

* **Modular Design (模組化設計)**
    * **EN**: Separated logic into `command_handler.py` (Logic), `ha_manager.py` (Discovery), and `core_logging.py` (Logs).
    * **TW**: 將邏輯拆分為 `command_handler.py` (指令邏輯)、`ha_manager.py` (HA 發現) 與 `core_logging.py` (日誌系統)，提升維護性。

* **HA Reliability (HA 可靠性)**
    * **EN**: 
        * Discovery & LWT set to `Retain=True` to survive Home Assistant restarts.
        * Sensor states set to `Retain=False` to prevent stale data.
    * **TW**: 
        * 將 Discovery 設定檔與 LWT 遺囑設為 `Retain=True`，確保 HA 重啟後實體自動恢復。
        * 將感測器數據設為 `Retain=False`，避免顯示過期的舊數據。

### 🐛 Fixes (修正)

* **EN**:
    * Fixed `0x26` register address for Discharge Recovery Voltage (was incorrectly mapped to 0x24).
    * Fixed Paho MQTT V2 callback compatibility issues.
    * Added `flush_buffer` to prevent data collision on RS485 bus.
* **TW**:
    * 修正 `0x26` 暫存器地址錯誤 (過放恢復電壓原誤植為 0x24)。
    * 修正 Paho MQTT V2 回調函式參數不匹配問題。
    * 新增 `flush_buffer` 機制，在發送前強制清空緩衝區以防止數據碰撞。

All notable changes to the "Ampinvt MPPT Monitor" project will be documented in this file.

## [5.3.0] - 2025-12-6

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
