# 🌞 Ampinvt MPPT 智慧監控系統 (V7.8)

這是為佛山金廣源 (Ampinvt) MPPT 太陽能充電控制器設計的高級監控與控制 Add-on。本專案專注於 **穩定性、硬體安全性** 與 **惡劣通訊環境下的高韌性 (Resilience)**。

---
## 7.8
  * pv vol

## ✨ 核心功能與特色 (Key Features)

* **🛡️ 零信任安全啟動 (Zero Trust Startup)**
    * **EN**: The system requires a successful, verified read of the device's actual hardware specs (Type, Voltage, Max Amp) before registering any HA entities. If the device is offline during startup, **no unsafe entity will be created**.
    * **TW**: 系統啟動時必須成功讀取並驗證設備的真實硬體規格 (電池類型、串數、最大電流) 後，才註冊實體。如果設備離線，**不會創建任何危險的實體**。

* **🟢 專屬連線狀態感知 (Dedicated Connectivity Sensor)**
    * **EN**: Adds a distinct `binary_sensor.connectivity` for each MPPT. This explicitly turns OFF (red light) after 20 failures, allowing users to clearly distinguish between 'system crash' and 'device offline'.
    * **TW**: 為每個 MPPT 設備新增專屬的「連線狀態燈」。一旦連續失敗 20 次，燈號會明確顯示「中斷」，方便使用者通過自動化判斷設備硬體是否故障。

* **🧠 硬體規格鎖定 (Hardware Specification Lock)**
    * **EN**: Automatically reads the true physical current limit (e.g., 60A) and enforces it as the maximum value on the HA setting slider. **LiFePO4 Safety**: Locks the maximum charging voltage to 14.6V/12V equivalent.
    * **TW**: 自動讀取硬體最大充電電流，並鎖定 HA 設定滑桿的上限。**鋰鐵安全**：鎖定鋰電池的最高充電電壓在 14.6V/12V (鐵鋰安全極限)。

---

## ⚠️ 系統中肯評估：優點與缺陷 (Candid Assessment: V7.7)

### ✅ 優點：極限穩定與智慧化 (The Good - High Resilience)

| **領域** | **V7.7 的優勢** | **說明** |
| :--- | :--- | :--- |
| **穩定性 (Stability)** | **極高** (High Resilience) | 採用 Socket 同步底層，在廉價 Modbus Gateway 或高干擾環境下，比 Asyncio 更能抗衡時序錯誤。 |
| **控制體驗 (UX)** | **低延遲插隊** (Low Latency) | 插隊輪詢機制確保控制指令享有優先權，操作響應速度極快 (< 0.5秒)。 |
| **故障處理** | **資源節省** (Resource Saving) | **多階段懲罰機制** 避免了 CPU 資源浪費在無效的連線重試上。 |

### ❌ 缺點與先天缺陷 (The Flaws - Structural Limitations)

| **領域** | **V7.7 的極限與缺陷** | **說明** |
| :--- | :--- | :--- |
| **擴充性 (Scale)** | **單線程的物理上限** | 僅能穩定服務 **10 台設備以內**。設備數量增加將線性延長輪詢週期。 |
| **資料完整性** | **斷網即丟失** (Data Loss) | **先天缺陷**：缺乏本地資料庫緩存 (SQLite)。網路中斷期間，發電數據將永久遺失。 |
| **啟動體驗** | **沈默的儀式感** (Startup Silence) | 為了安全，若設備離線，HA 介面將 **完全空白**，使用者需要耐心等待其背景重試成功。 |
| **架構負擔** | **硬闖式通訊** (Brute-Force Comms) | `flush_buffer` 雖然有效，但本質上是通過 **額外的 CPU 週期** 來清除雜訊，彌補底層硬體的不足。 |

---
# ⚙️ Ampinvt MPPT 監控系統設定指南 (V7.7)

本文件詳細說明 `config.yaml` 檔案中所有可配置的選項。請根據您的 Home Assistant 環境和硬體設定進行修改。

## 1. 系統設定 (system)

| 選項 | 類型 | 預設值 | 參數作用與填寫說明 |
| :--- | :--- | :--- | :--- |
| `debug` | `bool` | `false` | 是否開啟偵錯模式。開啟後，日誌中會顯示詳細的 Modbus 原始數據 (Hex)，**僅建議除錯時開啟**。 |
| `timezone_offset` | `int` | `8` | **時區補償**。設定您所在地區與 UTC+0 的時差 (單位：小時)。例如，台北/北京時間為 `8`。用於內建的時間同步功能。 |
| `language` | `str` | `"tw"` | 介面語系選擇。目前支援 `"tw"` (繁體中文) 或 `"en"` (英文)。 |

## 2. 故障懲罰機制 (blacklist) 🛡️

**【極端韌性功能】** 用於處理單一設備的連續通訊失敗。當設備故障時，系統會將其短暫或長期隔離，以節省資源。

| 選項 | 類型 | 預設值 | 參數作用與填寫說明 |
| :--- | :--- | :--- | :--- |
| `fail_threshold` | `int` | `20` | **HA 離線門檻**。單一設備連續失敗達到此次數後，HA 上的實體將被標記為 `Unavailable` (變灰)。 |
| `isolation_time` | `int` | `60` | **初始隔離時間** (秒)。當設備連線失敗時，第一次隔離的時間長度。**建議設為 60 秒**。 |
| `long_delay_threshold` | `int` | `10` | **長延遲門檻**。單一設備連續失敗次數超過此門檻後，系統將進入「長期隔離」。 |
| `long_delay` | `int` | `3600` | **嚴重懲罰時間** (秒)。當失敗達到 `long_delay_threshold` 後，每次重試的間隔時間。**預設 3600 秒即 1 小時 (避免資源浪費)**。 |

## 3. Modbus 通訊設定 (modbus)

| 選項 | 類型 | 預設值 | 參數作用與填寫說明 |
| :--- | :--- | :--- | :--- |
| `host` | `str` | `"192.168.106.12"` | **必填**：您的 Modbus-TCP 網關的 IP 位址。 |
| `port` | `int` | `502` | Modbus-TCP 服務的端口號。除非您的網關有特殊設定，否則通常為 `502`。 |
| `unit_ids` | `str` | `"1"` | **必填**：要監控的 MPPT 設備 ID (Slave ID)。多個設備請用逗號分隔，例如 `"1, 2, 3, 4"`。 |
| `timeout` | `float` | `3.0` | **Modbus 超時時間** (秒)。程式等待設備回應的最長時間。**建議 3.0 秒或更低**。 |

## 4. MQTT Broker 設定 (mqtt)

| 選項 | 類型 | 預設值 | 參數作用與填寫說明 |
| :--- | :--- | :--- | :--- |
| `broker` | `str` | `"core-mosquitto"` | MQTT Broker 的服務 IP 或名稱。若與 HA 運行在同一主機，可使用預設值。 |
| `port` | `int` | `1883` | MQTT 端口號 (非 SSL)。 |
| `username` | `str` | `"mqtt_user"` | MQTT 登入帳號。 |
| `password` | `str` | `"mqtt_password"` | MQTT 登入密碼。 |
| `discovery_prefix` | `str` | `"homeassistant"` | HA MQTT Discovery 的預設前綴。 |
| `node_id` | `str` | `"wifi01"` | 識別此 Add-on 實例的 Node ID。影響實體的唯一 ID。 |
| `device_name` | `str` | `"ampinvt_mppt"` | HA 中顯示的設備名稱。 |
| `reset_discovery_on_exit` | `bool` | `false` | 程式結束時是否清除 HA 上的所有實體註冊 (**生產環境請保持 `false`**)。 |

## 5. 輪詢間隔設定 (polling)

| 選項 | 類型 | 預設值 | 參數作用與填寫說明 |
| :--- | :--- | :--- | :--- |
| `poll_interval` | `int` | `3` | **主循環間隔** (秒)。程式在讀完所有設備後，休息的時間。此值越低，數據更新越快。 |
| `delay_between_units` | `float` | `0.5` | **設備間延遲** (秒)。讀取完一台設備後，等待多長時間再讀下一台 (避免總線衝突)。 |
