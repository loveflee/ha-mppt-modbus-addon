# ha-mppt-modbus-addon
ampinvt mppt rs485v1.1 </br>
This add-on connects to an Ampinvt MPPT solar charge controller through a Modbus TCP gateway, polls device data, and publishes it to Home Assistant using MQTT.</br>

附加元件 讀取 串口服務器下的 ampinvt mppt </br>
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
