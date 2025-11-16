# ha-mppt-modbus-addon
modbus gateway to ampinvt mppt  get data and push to ha </br>
ampinvt mppt v1.1 </br>

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
alias: 重啟 ha 後也重啟讀取 mppt
description: ""
triggers:
  - trigger: state
    entity_id:
      - input_button.restart_ha
conditions: []
actions:
  - action: homeassistant.restart
    metadata: {}
    data: {}
mode: single
```
