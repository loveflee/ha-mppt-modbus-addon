# =============================================================================
# File: generic_adapter.py
# Description: 工業級通用 Modbus 設備解析器 V2.2 (工業封存版)
# 相容：BusMaster V3.8
# 修復歷程：
#   V2.1 : 新增三大 Modbus 硬防線 (FC/Length/ByteCount)。
#   V2.2 : 修復 FC01 Coil 回讀張冠李戴 (導入 read_fc 分流)。
#          補齊 64-bit 'dcba' (四字倒序) 與 FC05 (Coil) 寫入格式。
#          誠實聲明 _poll_index 為受 BusMaster 序列化保護的安全狀態。
# =============================================================================

import struct
import logging

logger = logging.getLogger(__name__)

class DataDecodeError(Exception):
    """解析失敗、長度錯誤、FC 不符或 CRC 校驗失敗"""
    pass

def calc_crc16(data: bytes) -> bytes:
    crc = 0xFFFF
    for pos in data:
        crc ^= pos
        for _ in range(8):
            if crc & 1:
                crc >>= 1
                crc ^= 0xA001
            else:
                crc >>= 1
    return struct.pack('<H', crc)

class GenericModbusAdapter:
    """
    通用 Modbus 設備解析器 V2.2

    狀態說明（誠實版）：
      _poll_index 是 mutable state，用來追蹤輪詢輪次 (Round-Robin)。
      因為 BusMaster V3.8 為嚴格的單一總線序列化排程，此狀態不存在競爭問題，可安全放於此處。

    Context 傳遞設計（防狀態毒化）：
      build_poll_read() → (req_bytes, context)
      build_verify_read() → (req_bytes, context)
      context 包含解碼所需全部資訊（包含 read_fc），
      decode(raw_data, context) 作為純函數，根據 context 決定解析路徑。
    """

    def __init__(self, uid: int, profile: dict):
        self.uid = uid
        self.profile = profile  # 工控配置視為不可變真理
        self.definitions = profile.get("definitions", {})
        self.sensors = profile.get("sensors", [])
        self.settings = profile.get("settings", {})
        
        self._poll_cmds = self._prebuild_poll_cmds()
        self._poll_index = 0

    def _prebuild_poll_cmds(self) -> list:
        cmds = []
        for cmd in self.profile.get("read_commands", []):
            base = struct.pack('>BBHH', self.uid, cmd['fc'], cmd['start_addr'], cmd['count'])
            req = base + calc_crc16(base)
            cmds.append({
                "id": cmd['id'],
                "fc": cmd['fc'],
                "req": req,
                "expected_len": cmd.get('response_len'),
            })
        return cmds

    # =========================================================================
    # 幀驗證 (六層硬防線)
    # =========================================================================

    def _verify_modbus_frame(self, raw_data: bytes, expected_fc: int = None, expected_len: int = None):
        if not raw_data or len(raw_data) < 5:
            raise DataDecodeError(f"封包過短 ({len(raw_data) if raw_data else 0} bytes)")

        if expected_len and len(raw_data) != expected_len:
            raise DataDecodeError(f"長度不符: 預期 {expected_len}, 實際 {len(raw_data)}")

        if raw_data[0] != self.uid:
            raise DataDecodeError(f"Slave ID 不符 (收到 {raw_data[0]}，預期 {self.uid})")

        if expected_fc is not None and raw_data[1] != expected_fc:
            raise DataDecodeError(f"FC 不符 (收到 0x{raw_data[1]:02X}，預期 0x{expected_fc:02X})")

        fc = raw_data[1]

        # 讀取類：ByteCount 數學驗證
        if fc in (1, 2, 3, 4):
            byte_count = raw_data[2]
            actual_data = len(raw_data) - 5  # UID(1)+FC(1)+ByteCount(1)+CRC(2) = 5
            if byte_count != actual_data:
                raise DataDecodeError(f"ByteCount 破裂: 標示 {byte_count} bytes, 實際載荷 {actual_data} bytes")

        # 寫入類：固定 8 bytes 防線
        elif fc in (5, 6, 15, 16):
            if len(raw_data) != 8:
                raise DataDecodeError(f"FC 0x{fc:02X} 回應長度不符: 預期 8 bytes, 實際 {len(raw_data)} bytes")

        # CRC 物理防線
        payload, recv_crc = raw_data[:-2], raw_data[-2:]
        if calc_crc16(payload) != recv_crc:
            raise DataDecodeError("CRC16 校驗失敗（物理干擾或錯位）")

    # =========================================================================
    # 解包管線 (The Decode Pipeline)
    # =========================================================================

    def _unpack_value(self, chunk: bytes, datatype: str, word_order: str):
        if datatype == 'string':
            return chunk.decode('ascii', errors='ignore').strip('\x00 \t')

        # 64-bit (8 bytes)
        if len(chunk) == 8:
            if word_order == 'little':
                chunk = chunk[::-1]
            elif word_order in ('swap', 'word_swap'): # EFGHABCD
                chunk = chunk[4:8] + chunk[0:4]
            elif word_order == 'dcba':                # W3W2W1W0 (Schneider/Eastron)
                chunk = chunk[6:8] + chunk[4:6] + chunk[2:4] + chunk[0:2]
            elif word_order == 'byte_swap':           # BADCFEHG
                chunk = bytes([
                    chunk[1], chunk[0], chunk[3], chunk[2],
                    chunk[5], chunk[4], chunk[7], chunk[6]
                ])
                
            if datatype == 'uint64':  return struct.unpack('>Q', chunk)[0]
            if datatype == 'int64':   return struct.unpack('>q', chunk)[0]
            if datatype == 'float64': return struct.unpack('>d', chunk)[0]

        # 32-bit (4 bytes)
        elif len(chunk) == 4:
            if word_order in ('swap', 'word_swap'):   # CDAB
                chunk = chunk[2:4] + chunk[0:2]
            elif word_order == 'byte_swap':           # BADC
                chunk = bytes([chunk[1], chunk[0], chunk[3], chunk[2]])
            elif word_order == 'little':              # DCBA
                chunk = chunk[::-1]
                
            if datatype == 'uint32':  return struct.unpack('>I', chunk)[0]
            if datatype == 'int32':   return struct.unpack('>i', chunk)[0]
            if datatype == 'float32': return struct.unpack('>f', chunk)[0]

        # 16-bit (2 bytes)
        elif len(chunk) == 2:
            if word_order == 'little':
                chunk = chunk[::-1]
            if datatype == 'uint16': return struct.unpack('>H', chunk)[0]
            if datatype == 'int16':  return struct.unpack('>h', chunk)[0]

        # 8-bit (1 byte)
        elif len(chunk) == 1:
            if datatype == 'int8': return struct.unpack('>b', chunk)[0]
            return chunk[0]

        logger.warning(f"[Adapter] 未能解包: len={len(chunk)} datatype={datatype}")
        return None

    # =========================================================================
    # BusMaster 介面（Context 傳遞設計）
    # =========================================================================

    def build_poll_read(self) -> tuple[bytes, dict]:
        if not self._poll_cmds:
            raise RuntimeError("設備未定義 read_commands")
        cmd = self._poll_cmds[self._poll_index]
        self._poll_index = (self._poll_index + 1) % len(self._poll_cmds)
        return cmd['req'], {"type": "poll", "cmd": cmd}

    def build_verify_read(self, key: str) -> tuple[bytes, dict]:
        setting = None
        target_addr = None
        for addr_str, cfg in self.settings.items():
            if cfg['key'] == key:
                setting = cfg
                target_addr = int(addr_str, 16) if isinstance(addr_str, str) else addr_str
                break

        if not setting:
            raise ValueError(f"找不到寫入 Key: {key}")

        write_fc = setting.get("write_fc", 6)
        read_fc = 0x01 if write_fc in (5, 15) else 0x03
        reg_count = setting.get("verify_count", 1)

        base = struct.pack('>BBHH', self.uid, read_fc, target_addr, reg_count)
        req = base + calc_crc16(base)

        return req, {
            "type": "verify",
            "key": key,
            "read_fc": read_fc,   # 💡 帶入 read_fc 供 decode 分流
        }

    def encode_write(self, key: str, value) -> bytes:
        setting = None
        target_addr = None
        for addr_str, cfg in self.settings.items():
            if cfg['key'] == key:
                setting = cfg
                target_addr = int(addr_str, 16) if isinstance(addr_str, str) else addr_str
                break

        if not setting:
            raise ValueError(f"未知的寫入 Key '{key}'")

        fc = setting.get("write_fc", 6)
        scale = setting.get("scale", 1.0)

        link_sensor = setting.get("link_sensor")
        for s in self.sensors:
            if s['key'] == link_sensor and "map_profile" in s:
                map_dict = self.definitions.get("value_maps", {}).get(s["map_profile"], {})
                for k, v in map_dict.items():
                    if str(v) == str(value):
                        value = k
                        break

        try:
            int_val = int(round(float(value) * scale))
        except (TypeError, ValueError):
            raise ValueError(f"寫入值無效: {value}")

        if fc == 6:
            base = struct.pack('>BBHH', self.uid, 0x06, target_addr, int_val & 0xFFFF)
            return base + calc_crc16(base)
        elif fc == 5:
            # Coil ON = 0xFF00, OFF = 0x0000
            coil_val = 0xFF00 if int_val else 0x0000
            base = struct.pack('>BBHH', self.uid, 0x05, target_addr, coil_val)
            return base + calc_crc16(base)
        else:
            raise NotImplementedError(f"尚不支援功能碼 FC {fc} 組裝")

    def decode(self, raw_data: bytes, context: dict) -> dict:
        result = {}
        ctx_type = context.get("type")

        # -----------------------------------------------------------------
        # Verify 模式 (寫入回讀驗證)
        # -----------------------------------------------------------------
        if ctx_type == "verify":
            key = context["key"]
            read_fc = context.get("read_fc", 0x03) 

            self._verify_modbus_frame(raw_data, expected_fc=read_fc)

            # Exception Response
            if raw_data[1] & 0x80:
                raise DataDecodeError(f"設備回報 Modbus Exception Code: {raw_data[2]}")

            # FC03/FC04：寄存器讀取
            if read_fc in (0x03, 0x04):
                if len(raw_data) >= 7:
                    chunk = raw_data[3:5]
                    val = struct.unpack('>H', chunk)[0]
                    for cfg in self.settings.values():
                        if cfg['key'] == key:
                            scale = cfg.get("scale", 1.0)
                            link_sensor = cfg.get("link_sensor")
                            is_mapped = False
                            for s in self.sensors:
                                if s['key'] == link_sensor and "map_profile" in s:
                                    map_dict = self.definitions.get("value_maps", {}).get(s["map_profile"], {})
                                    if val in map_dict:
                                        result[key] = map_dict[val]
                                        is_mapped = True
                                    break
                            if not is_mapped:
                                result[key] = round(val / scale, 2) if scale != 1.0 else val
                            break

            # FC01/FC02：Coil 讀取
            elif read_fc in (0x01, 0x02):
                if len(raw_data) >= 6:
                    coil_byte = raw_data[3]  # 第一個資料 Byte
                    coil_val = bool(coil_byte & 0x01) # 取 bit 0
                    result[key] = "ON" if coil_val else "OFF"

        # -----------------------------------------------------------------
        # Poll 模式 (輪詢區塊解析)
        # -----------------------------------------------------------------
        elif ctx_type == "poll":
            cmd = context["cmd"]
            self._verify_modbus_frame(
                raw_data,
                expected_fc=cmd['fc'],
                expected_len=cmd.get('expected_len'),
            )

            for sensor in self.sensors:
                if sensor.get("command_id") != cmd['id']:
                    continue

                off = sensor.get("offset")
                length = sensor.get("length", 2)
                key = sensor['key']

                # 邊界檢查
                if off is None or off + length > len(raw_data) - 2:
                    logger.debug(f"[Adapter] sensor {key} offset 越界，跳過")
                    continue

                chunk = raw_data[off: off + length]

                try:
                    # 處理 Alarm Bits
                    if "bits" in sensor:
                        val = chunk[0] if length == 1 else struct.unpack('>H', chunk)[0]
                        for bit_cfg in sensor["bits"]:
                            bit_idx = bit_cfg["bit"]
                            is_on = bool((val >> bit_idx) & 0x01)
                            p_on = bit_cfg.get("ha", {}).get("payload_on", "ON")
                            p_off = bit_cfg.get("ha", {}).get("payload_off", "OFF")
                            result[bit_cfg["id"]] = p_on if is_on else p_off
                        continue

                    # 處理數值
                    datatype = sensor.get("datatype", "uint16" if length == 2 else "uint8")
                    if sensor.get("signed"):
                        datatype = datatype.replace("u", "", 1)
                    word_order = sensor.get("word_order", "big")
                    scale = sensor.get("scale", 1.0)

                    val = self._unpack_value(chunk, datatype, word_order)
                    if val is None:
                        continue

                    # Enum 映射
                    if "map_profile" in sensor:
                        map_dict = self.definitions.get("value_maps", {}).get(sensor["map_profile"], {})
                        result[key] = map_dict.get(val, str(val))
                    else:
                        result[key] = round(val / scale, 2) if scale != 1.0 else val

                except Exception as e:
                    logger.debug(f"[Adapter] 解析 sensor {key} 失敗: {e}")

        else:
            raise DataDecodeError(f"無效的 context type: {ctx_type}")

        if not result:
            raise DataDecodeError("解析成功但未提取出任何有效數據")

        return result
