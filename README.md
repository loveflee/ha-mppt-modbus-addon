# 🌞 Ampinvt MPPT 智慧監控系統 (V7.7)

這是為佛山金廣源 (Ampinvt) MPPT 太陽能充電控制器設計的高級監控與控制 Add-on。本專案專注於 **穩定性、硬體安全性** 與 **惡劣通訊環境下的高韌性 (Resilience)**。

---

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


# 🛠️ 安裝與啟動指南 (Installation & Setup Guide)

本文件提供 Ampinvt MPPT 監控系統 V7.7 版本的啟動步驟。本系統建議在 Home Assistant OS 或 Proxmox (搭配 Docker) 環境下運行。

## 1. 環境準備 (Prerequisites)

* **EN**: **MQTT Broker**: Your Home Assistant must have Mosquitto Broker running.
* **TW**: **MQTT Broker**: 您的 Home Assistant 必須安裝並運行 Mosquitto Broker (或任何 MQTT 服務)。

* **EN**: **Modbus Gateway**: A stable Modbus-TCP gateway (e.g., USR-TCP232-410S) is required.
* **TW**: **Modbus 網關**: 您需要一個穩定的 Modbus-TCP 網關 (例如 USR-TCP232-410S, USR-WIFI232-G2 等)。

* **EN**: **Docker Environment**: The host machine must have Docker or Docker Compose installed.
* **TW**: **Docker 環境**: 主機需安裝 Docker 或 Docker Compose。

---

## 2. 檔案配置 (File Configuration)

請在專案根目錄下創建或修改以下三個關鍵文件：

### A. `requirements.txt` (相依性 / Dependencies)

* **EN**: Ensure Flask is added for future Web UI expansion.
* **TW**: 請確保 Flask 已經被加入，以便未來擴充 Web 介面。
