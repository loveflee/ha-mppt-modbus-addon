# app/config.yaml
system:
  debug: false
  language: tw
  timezone_offset: 8
reset_discovery_on_exit: false

blacklist:
  fail_threshold: 20
  isolation_time: 60
  long_delay_threshold: 10
  long_delay: 3600

modbus:
  host: "192.168.106.12"
  port: 502
  unit_ids: [1, 2, 3, 4, 5]
  timeout: 3.0
  retry_delay: 2.0

mqtt:
  broker: "192.168.106.5"  # 👈 必須填寫實體 IP
  port: 1883
  username: "mqtt"
  password: "mqtt"
  discovery_prefix: "homeassistant"
  node_id: "wifi01"
  device_name: "ampinvt_mppt"

polling:
  poll_interval: 3
  delay_between_units: 0.5
