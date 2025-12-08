Ampinvt MPPT Solar Controller 60A</br>
docker compose python開發後,包裝成Home Assistant 的 Add-on，</br>
用於監控 佛山金廣源 (Ampinvt) MPPT 太陽能控制器</br></br>

過壓保護 > 均壓 浮充 > 過壓恢復 > 過放恢復 > 放電下限 </br>

透過 Modbus gateway (串口服務器) 讀取ampinvt mppt數據，</br>
並利用 MQTT Discovery 自動將感測器註冊到 Home Assistant，不用再編寫ha YAML 設定</br></br>

✨ 主要功能</br>
🚀 內建 TCP 封包重組機制 (_recv_fixed)，</br>
解決 WiFi/RS485 傳輸過程中的封包碎片化 (Fragmentation) 問題</br>
自動髒數據清洗 (Flush Buffer)，防止讀取到過期的錯誤數值</br>
支援斷線自動重連與 MQTT Last Will (LWT) 狀態監控</br></br>

📊 完整數據監控：</br>
支援 0xB1 全參數協議 (93 Bytes)，數據完整</br>
自動計算瞬時功率 (Watts = V * I)</br>
監控 PV 電壓、電池電壓、電流、溫度、日發電量、總發電量</br>
即時顯示錯誤狀態 (過壓、過溫、過充等)</br></br>

⚙️ 遠端控制與設定</br>
支援透過 HA 介面遠端開關負載 (Load ON/OFF)</br>
可調整充電參數 (如：電池類型、均充/浮充電壓、限流設定)</br>
🔌 支援讀取多台mppt設備</br>
單一 Add-on 可輪詢多台 MPPT (透過 unit_ids 設定，例如 1, 2, 3或單台1)</br></br>

🛠️ 硬體需求</br>
Ampinvt MPPT 控制器 v1.1 (確認支援 RS485 通訊)。</br>
RS485 轉 乙太網/WiFi 模組 (例如：Elfin EW11, USR-TCP232 等)</br></br>

⚠️ 重要設定：模組必須設定為 TCP Server 模式，並且開啟 透明傳輸 (Transparent Mode)。</br></br>

Home Assistant (OS 或 Supervised 版本，需支援 Add-on Store)。</br>
MQTT Broker (HA 附加元件內建 Mosquitto broker)。</br></br>

📥 安裝步驟</br>
在 Home Assistant 中，前往 設定 > Add-ons(附加元件) > Add-on Store。</br>
點擊右上角的三個點 ... > 管理儲存庫(Repositories)</br>
添加入本專案的 GitHub 網址：</br>
[https://github.com/loveflee/ha-mppt-modbus-addon](https://github.com/loveflee/ha-mppt-modbus-addon)</br>


點擊 Add。</br>
重新整理頁面，找到 "MPPT Modbus MQTT Poller" 點擊安裝</br>
⚙️ 設定說明 (Configuration)</br>
安裝後，請至 Add-on 的 Configuration 頁面進行設定：</br>
參數說明範例</br></br></br>

[modbus分頁 點我跳轉下方詳細版說明](https://github.com/loveflee/ha-mppt-modbus-addon/blob/main/README.md#%EF%B8%8F-configuration-%E8%A8%AD%E5%AE%9A%E8%AA%AA%E6%98%8E)</br>
-------------------------------------</br>
host</br>
填入串口服務器ip:比如192.168.1.100</br></br>
port</br>
填入串口服務器port:502</br></br>
unit_ids</br>
MPPT 設備 ID (支援單台或多台，用逗號分隔)</br>
(mppt設備的地址address)</br>
單台:</br>
1</br>
多台:</br>
1, 2, 3, 4, 5</br></br>


mqtt分頁</br>
-------------------------------------</br>
borker(通常是 HA 的 IP)</br>
core-mosquitto</br></br>
port(ha預設mqtt port:1883)</br>
1883</br>
username</br>
新增帳號( 勾選>>限制本地登入 )</br></br>
password</br>
新增帳號密碼</br>

node_id</br>
用於 MQTT Topic 的識別名稱 (建議英文)</br>
wifi01</br>
poll_interval</br>
每一輪掃描後的休息秒數</br>
3</br>
delay_between_units</br>
多台設備輪詢時的間隔秒數</br>
0.5</br>

</br></br></br>
⚠️ 常見問題 (FAQ)</br>
Q1: 為什麼日誌顯示 "Length Error" 或連線超時？</br>
請檢查您的 RS485 轉接器設定。務必確認 Baud Rate (波特率) 與 MPPT 設定一致 (預設通常是 9600)，且模式為 None (無校驗), 8 Data bits, 1 Stop bit。
確認轉接器工作模式為 Transparent (透傳)，不要開啟 Modbus RTU <-> TCP 轉換功能 (因為此 MPPT 使用非標準 Modbus 封包)。</br>
Q2: 為什麼找不到實體 (Entity)？</br>
請確認您的 MQTT 設定正確。
如果您更換了 node_id，HA 會視為新設備。本程式設計為相容舊版 ID 結構，以保留歷史數據。</br>
Q3: 支援哪些型號？</br>
測試於佛山金廣源 (Ampinvt) 60A MPPT 控制器 (黑色/藍色外殼版本)。</br>
支援 V1.1 通訊協議 (指令 0xB1)。
</br>
</br>
瞬間總發電量 設定>裝置與服務>輔助工具>新增輔助工具>template>感測器 貼上 公式 測量單位:W
```
{% set mppt1 = states('sensor.mppt_kong_zhi_qi_1_jin_ri_fa_dian_liang') | float(0) %}
{% set mppt2 = states('sensor.mppt_kong_zhi_qi_2_jin_ri_fa_dian_liang') | float(0) %}
{% set mppt3 = states('sensor.mppt_kong_zhi_qi_3_jin_ri_fa_dian_liang') | float(0) %}
{% set mppt4 = states('sensor.mppt_kong_zhi_qi_4_jin_ri_fa_dian_liang') | float(0) %}
{% set mppt5 = states('sensor.mppt_kong_zhi_qi_5_jin_ri_fa_dian_liang') | float(0) %}

{{ (mppt1 + mppt2 + mppt3 + mppt4 + mppt5) }}
```
</br>

推薦使用 [mqtt explorer](https://mqtt-explorer.com/) 觀察訊息!!!</br></br>
# Ampinvt MPPT Solar Controller Home Assistant Add-on
### 佛山金廣源 MPPT 太陽能控制器 HA 插件

![Home Assistant](https://img.shields.io/badge/Home%20Assistant-Add--on-blue) ![Python](https://img.shields.io/badge/Made%20with-Python-yellow) ![Docker](https://img.shields.io/badge/Container-Docker-blue)

此 Add-on 專為監控 **佛山金廣源 (Ampinvt)** MPPT 太陽能控制器而設計。核心程式採用 Python 開發，透過 Modbus Gateway (串口服務器) 讀取數據，並利用 MQTT Discovery 協定自動將感測器註冊至 Home Assistant，無需繁瑣的手動 YAML 設定。

This Add-on is designed to monitor **Ampinvt** MPPT Solar Controllers. The core is developed in Python, reading data via a Modbus Gateway (Serial Server) and automatically registering sensors to Home Assistant using the MQTT Discovery protocol, eliminating the need for manual YAML configuration.

---

## ✨ Key Features (主要功能)

### 🚀 Robust Communication (穩健通訊)
* **TCP Packet Reassembly (`_recv_fixed`):** Solves fragmentation issues common in WiFi/RS485 transmission by ensuring complete data frames are received.
    * **TCP 封包重組機制：** 內建 `_recv_fixed` 機制，解決 WiFi 或 RS485 傳輸過程中常見的封包碎片化 (Fragmentation) 問題。
* **Auto Flush Buffer:** Automatically cleans "dirty data" from the buffer to prevent reading outdated or incorrect values.
    * **自動髒數據清洗：** 自動清除緩衝區內的殘留數據，防止讀取到過期的錯誤數值。
* **Connection Stability:** Supports automatic reconnection and MQTT Last Will and Testament (LWT) for status monitoring.
    * **連線穩定性：** 支援斷線自動重連與 MQTT Last Will (LWT) 狀態監控。

### 📊 Comprehensive Monitoring (完整數據監控)
* **Full Protocol Support:** Reads the full `0xB1` parameter set (93 Bytes).
    * 支援 0xB1 全參數協議 (93 Bytes)，數據完整。
* **Real-time Metrics:** Monitors PV Voltage, Battery Voltage, Current, Temperature, Daily Yield, and Total Yield.
    * 監控 PV 電壓、電池電壓、電流、溫度、日發電量、總發電量。
* **Smart Calculation:** Automatically calculates instantaneous power (`Watts = V * I`).
    * 自動計算瞬時功率 (Watts = V * I)。
* **Error Reporting:** Real-time display of error states (Over-voltage, Over-temp, Over-charge, etc.).
    * 即時顯示錯誤狀態 (過壓、過溫、過充等)。

### ⚙️ Control & Scalability (控制與擴展)
* **Remote Control:** Switch Load ON/OFF directly from Home Assistant. Adjustable charging parameters (Battery Type, Equalize/Float Voltage, Current Limits).
    * **遠端控制：** 支援透過 HA 介面遠端開關負載 (Load ON/OFF)，並可調整充電參數 (如：電池類型、均充/浮充電壓、限流設定)。
* **Multi-Device Support:** Poll multiple MPPT units with a single Add-on instance (e.g., unit_ids: 1, 2, 3).
    * **多設備支援：** 單一 Add-on 可輪詢多台 MPPT 設備 (透過 unit_ids 設定，例如 1, 2, 3)。

---

## 🛠️ Hardware Requirements (硬體需求)

1.  **Ampinvt MPPT Controller v1.1:** Must support RS485 communication (Black or Blue case versions).
    * **Ampinvt MPPT 控制器 v1.1：** 需確認支援 RS485 通訊 (通常為黑色或藍色外殼版本)。
2.  **RS485 to Ethernet/WiFi Module:** Such as Elfin EW11, USR-TCP232, etc.
    * **RS485 轉 乙太網/WiFi 模組：** 例如：Elfin EW11, USR-TCP232 等。
3.  **Home Assistant:** OS or Supervised version (Supports Add-on Store).
    * **Home Assistant：** OS 或 Supervised 版本 (需支援 Add-on Store)。
4.  **MQTT Broker:** Standard Mosquitto broker addon in HA.
    * **MQTT Broker：** HA 內建的 Mosquitto broker 附加元件。

> **⚠️ Important Setting / 重要設定:**
> The RS485 module must be set to **TCP Server** mode and **Transparent Mode**.
> 模組必須設定為 **TCP Server** 模式，並且開啟 **透明傳輸 (Transparent Mode)**。

---

## 📥 Installation (安裝步驟)

1.  **Add Repository:**
    Go to **Settings > Add-ons > Add-on Store**. Click the explicit menu (`...`) > **Repositories**.
    Add the URL of this project:
    `https://github.com/loveflee/ha-mppt-modbus-addon`

    **新增儲存庫：**
    前往 **設定 > Add-ons(附加元件) > Add-on Store**。點擊右上角三點選單 (`...`) > **管理儲存庫(Repositories)**。
    輸入本專案網址。

2.  **Install:**
    Refresh the page, find **"MPPT Modbus MQTT Poller"**, and click **Install**.
    **安裝：** 重新整理頁面，找到 "MPPT Modbus MQTT Poller" 點擊安裝。

---

## ⚙️ Configuration (設定說明)

Configure the Add-on via the **Configuration** tab.
安裝後，請至 Add-on 的 Configuration 頁面進行設定：

### Modbus Settings (Modbus 分頁)

| Parameter | Description (說明) | Example (範例) |
| :--- | :--- | :--- |
| `host` | IP address of the Serial Server (串口服務器 IP) | `192.168.1.100` |
| `port` | Port of the Serial Server (串口服務器 Port) | `502` |
| `unit_ids` | MPPT Device IDs, comma separated (MPPT 設備 ID，逗號分隔) | `1` (Single) or `1, 2, 3` (Multi) |

### MQTT Settings (MQTT 分頁)

| Parameter | Description (說明) | Example (範例) |
| :--- | :--- | :--- |
| `broker` | MQTT Broker IP (usually HA core) | `core-mosquitto` |
| `port` | MQTT Port | `1883` |
| `username` | MQTT User (Ensure local access allowed) | `mqtt_user` |
| `password` | MQTT Password | `your_password` |

### Application Settings (應用程式設定)

| Parameter | Description (說明) | Example (範例) |
| :--- | :--- | :--- |
| `node_id` | Unique ID for MQTT Topic (建議使用英文) | `wifi01` |
| `poll_interval` | Rest time (seconds) after a full scan cycle (每輪掃描後的休息秒數) | `3` |
| `delay_between_units` | Interval (seconds) between polling different units (多台輪詢間隔) | `0.5` |

---

## ⚠️ FAQ (常見問題)

**Q1: Why do I see "Length Error" or connection timeouts in the logs?**
**Q1: 為什麼日誌顯示 "Length Error" 或連線超時？**

* **Check Baud Rate:** Ensure the RS485 adapter matches the MPPT settings (Default: 9600, None, 8, 1).
    * **檢查波特率：** 務必確認 RS485 轉接器設定與 MPPT 一致 (預設通常是 9600, None, 8, 1)。
* **Transparent Mode Only:** Ensure the adapter is in **Transparent Mode**. Do NOT enable "Modbus RTU <-> TCP" conversion, as this MPPT uses a custom/non-standard Modbus packet structure that standard converters might corrupt.
    * **僅限透傳模式：** 確認轉接器工作模式為 Transparent (透傳)，**不要**開啟 Modbus RTU <-> TCP 轉換功能 (因為此 MPPT 使用非標準 Modbus 封包)。

**Q2: Why can't I find the Entities in Home Assistant?**
**Q2: 為什麼找不到實體 (Entity)？**

* Check your MQTT Broker configuration.
    * 請確認您的 MQTT 設定正確。
* If you changed the `node_id`, HA treats it as a new device. This is intentional to preserve historical data for the old ID.
    * 如果您更換了 `node_id`，HA 會視為新設備。本程式設計為相容舊版 ID 結構，以保留歷史數據。

**Q3: Which models are supported?**
**Q3: 支援哪些型號？**

* Tested on Ampinvt 60A MPPT Controllers (Black/Blue case).
* Supports V1.1 Protocol (Command `0xB1`).
    * 測試於佛山金廣源 (Ampinvt) 60A MPPT 控制器 (黑色/藍色外殼版本)。
    * 支援 V1.1 通訊協議 (指令 0xB1)。

---

## 💡 Advanced: Total Power Template (進階：總功率加總)

If you have multiple MPPTs and want to calculate the total instantaneous power, create a **Template Sensor** helper in Home Assistant.
如果您有多台 MPPT 並希望計算瞬間總發電量，可在 Home Assistant 建立 **Template Sensor (模板感測器)**。

**Steps:**
Settings > Devices & Services > Helpers > Create Helper > Template > Sensor.
**路徑：**
設定 > 裝置與服務 > 輔助工具 > 新增輔助工具 > Template (模板) > 感測器。

**State Formula (狀態公式):**
*(Unit of Measurement: W)*

```yaml
{% set mppt1 = states('sensor.mppt_kong_zhi_qi_1_jin_ri_fa_dian_liang') | float(0) %}
{% set mppt2 = states('sensor.mppt_kong_zhi_qi_2_jin_ri_fa_dian_liang') | float(0) %}
{% set mppt3 = states('sensor.mppt_kong_zhi_qi_3_jin_ri_fa_dian_liang') | float(0) %}
{% set mppt4 = states('sensor.mppt_kong_zhi_qi_4_jin_ri_fa_dian_liang') | float(0) %}
{% set mppt5 = states('sensor.mppt_kong_zhi_qi_5_jin_ri_fa_dian_liang') | float(0) %}

{{ (mppt1 + mppt2 + mppt3 + mppt4 + mppt5) }}
