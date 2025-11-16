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
alias: 日出 重啟附加元件 mppt 讀取
description: ""
triggers:
  - trigger: sun
    event: sunrise
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
actions:
  - data:
      addon: 34caa00e_mppt_modbus_mqtt_poller
    action: hassio.addon_restart
  - delay:
      hours: 0
      minutes: 2
      seconds: 0
      milliseconds: 0
  - data:
      addon: 34caa00e_mppt_modbus_mqtt_poller
    action: hassio.addon_restart
mode: single
```
