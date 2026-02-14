#!/usr/bin/env python3
"""
Rev4 (HARDWARE_VERSION=40) データ取得テストスクリプト
PlantMonitor Rev4デバイスに接続して全センサーデータ・構成情報を取得します

テスト対象コマンド:
  - CMD_GET_DEVICE_INFO      (0x06) デバイス情報取得
  - CMD_GET_SYSTEM_STATUS    (0x02) システムステータス取得
  - CMD_GET_SENSOR_DATA      (0x01) センサーデータ取得 (soil_data_t, data_version=3)
  - CMD_GET_SENSOR_DATA_V2   (0x17) センサーデータ取得V2
  - CMD_GET_TIME_DATA        (0x0A) 時間指定データ取得 (time_data_response_t, packed)
  - CMD_GET_SENSOR_CONFIG    (0x1A) センサー構成情報取得 (soil_sensor_config_t, packed)

使用方法:
    pip install bleak
    python tests/test_data_retrieval_v40.py

必要なライブラリ:
    pip install bleak
"""

import asyncio
import struct
import sys
import time
from datetime import datetime
from bleak import BleakClient, BleakScanner

# BLE UUIDs (ble_manager.cと一致)
SERVICE_UUID = "59462f12-9543-9999-12c8-58b459a2712d"
COMMAND_UUID = "6a3b2c1d-4e5f-6a7b-8c9d-e0f123456791"
RESPONSE_UUID = "6a3b2c1d-4e5f-6a7b-8c9d-e0f123456792"
SENSOR_DATA_UUID = "6a3b2c01-4e5f-6a7b-8c9d-e0f123456789"

# コマンドID
CMD_GET_SENSOR_DATA = 0x01
CMD_GET_SYSTEM_STATUS = 0x02
CMD_GET_DEVICE_INFO = 0x06
CMD_GET_TIME_DATA = 0x0A
CMD_GET_SENSOR_DATA_V2 = 0x17
CMD_GET_SENSOR_CONFIG = 0x1A

# レスポンスステータス
RESP_STATUS_SUCCESS = 0x00
RESP_STATUS_ERROR = 0x01

# デバイスフィルタ
DEVICE_NAME_FILTER = "PlantMonitor_40"

# 土壌温度センサーデバイスタイプ
SOIL_TEMP_DEVICE_TYPES = {
    0: "None",
    1: "DS18B20",
    2: "TMP102",
    3: "TC74",
}

# 土壌湿度センサータイプ
MOISTURE_SENSOR_TYPES = {
    0: "ADC",
    1: "FDC1004",
}

# グローバル変数
response_received = asyncio.Event()
response_data = None
sequence_num = 0


def create_command_packet(command_id: int, data: bytes = b'') -> bytes:
    """コマンドパケットを作成"""
    global sequence_num
    sequence_num = (sequence_num + 1) % 256

    # パケット構造: command_id(1) + sequence_num(1) + data_length(2, LE) + data(n)
    data_length = len(data)
    packet = struct.pack('<BBH', command_id, sequence_num, data_length) + data
    return packet


def parse_response_packet(data: bytes) -> dict:
    """レスポンスパケットをパース (ble_response_packet_t, packed, 5バイトヘッダ)"""
    if len(data) < 5:
        return {'error': f'パケットが短すぎます ({len(data)} bytes)'}

    # ble_response_packet_t: response_id(1) + status_code(1) + sequence_num(1) + data_length(2, LE)
    response_id, status_code, seq_num, data_length = struct.unpack('<BBBH', data[:5])
    payload = data[5:5 + data_length] if data_length > 0 else b''

    return {
        'response_id': response_id,
        'status_code': status_code,
        'sequence_num': seq_num,
        'data_length': data_length,
        'payload': payload
    }


# ---------------------------------------------------------------------------
# Rev4 soil_data_t パーサ (非packed構造体、コンパイラのパディングあり)
#
# soil_data_t (HARDWARE_VERSION==40, data_version=3):
#   offset  0: uint8_t  data_version         (1 byte)
#   offset  1: padding                        (3 bytes)
#   offset  4: struct tm datetime             (9 * int32 = 36 bytes)
#   offset 40: float    lux                   (4 bytes)
#   offset 44: float    temperature           (4 bytes)
#   offset 48: float    humidity              (4 bytes)
#   offset 52: float    soil_moisture         (4 bytes)
#   offset 56: bool     sensor_error          (1 byte)
#   offset 57: padding                        (3 bytes)
#   offset 60: float    soil_temperature[4]   (16 bytes)
#   offset 76: uint8_t  soil_temperature_count(1 byte)
#   offset 77: padding                        (3 bytes)
#   offset 80: float    soil_moisture_cap[4]  (16 bytes)
#   offset 96: float    ext_temperature       (4 bytes)
#   offset100: bool     ext_temperature_valid (1 byte)
#   offset101: padding                        (3 bytes)
#   Total: 104 bytes
# ---------------------------------------------------------------------------
SOIL_DATA_V3_SIZE = 104


def parse_sensor_data_v3(payload: bytes) -> dict:
    """Rev4 (data_version=3) センサーデータをパース (soil_data_t, 非packed)"""
    if len(payload) < SOIL_DATA_V3_SIZE:
        return {'error': f'ペイロードが短すぎます: {len(payload)} bytes (期待: {SOIL_DATA_V3_SIZE})'}

    try:
        # data_version + padding
        data_version = payload[0]
        # struct tm (offset 4)
        tm_fields = struct.unpack_from('<9i', payload, 4)
        tm_sec, tm_min, tm_hour, tm_mday, tm_mon, tm_year = tm_fields[:6]
        # float fields (offset 40)
        lux, temperature, humidity, soil_moisture = struct.unpack_from('<4f', payload, 40)
        # sensor_error (offset 56)
        sensor_error = payload[56]
        # soil_temperature[4] (offset 60)
        soil_temps = struct.unpack_from('<4f', payload, 60)
        # soil_temperature_count (offset 76)
        soil_temp_count = payload[76]
        # soil_moisture_capacitance[4] (offset 80)
        capacitance = struct.unpack_from('<4f', payload, 80)
        # ext_temperature (offset 96)
        ext_temperature = struct.unpack_from('<f', payload, 96)[0]
        # ext_temperature_valid (offset 100)
        ext_temperature_valid = payload[100]

        datetime_str = _format_tm(tm_year, tm_mon, tm_mday, tm_hour, tm_min, tm_sec)

        return {
            'data_version': data_version,
            'datetime': datetime_str,
            'lux': lux,
            'temperature': temperature,
            'humidity': humidity,
            'soil_moisture': soil_moisture,
            'sensor_error': sensor_error,
            'soil_temperature': list(soil_temps),
            'soil_temperature_count': soil_temp_count,
            'capacitance': list(capacitance),
            'ext_temperature': ext_temperature,
            'ext_temperature_valid': bool(ext_temperature_valid),
        }
    except Exception as e:
        return {'error': str(e), 'raw': payload.hex()}


# ---------------------------------------------------------------------------
# Rev4 time_data_response_t パーサ (packed構造体)
#
# time_data_response_t (packed, HARDWARE_VERSION==40):
#   offset  0: uint8_t  data_version         (1 byte)
#   offset  1: struct tm actual_time          (36 bytes)
#   offset 37: float    temperature           (4 bytes)
#   offset 41: float    humidity              (4 bytes)
#   offset 45: float    lux                   (4 bytes)
#   offset 49: float    soil_moisture         (4 bytes)
#   offset 53: float    soil_temperature[4]   (16 bytes)
#   offset 69: uint8_t  soil_temperature_count(1 byte)
#   offset 70: float    soil_moisture_cap[4]  (16 bytes)
#   offset 86: float    ext_temperature       (4 bytes)
#   offset 90: uint8_t  ext_temperature_valid (1 byte)
#   Total: 91 bytes
# ---------------------------------------------------------------------------
TIME_DATA_RESPONSE_V3_SIZE = 91


def parse_time_data_response_v3(payload: bytes) -> dict:
    """Rev4 (data_version=3) 時間指定データをパース (time_data_response_t, packed)"""
    if len(payload) < TIME_DATA_RESPONSE_V3_SIZE:
        return {'error': f'ペイロードが短すぎます: {len(payload)} bytes (期待: {TIME_DATA_RESPONSE_V3_SIZE})'}

    try:
        data_version = payload[0]
        # struct tm (offset 1, packed)
        tm_fields = struct.unpack_from('<9i', payload, 1)
        tm_sec, tm_min, tm_hour, tm_mday, tm_mon, tm_year = tm_fields[:6]
        # float fields (offset 37, packed)
        temperature, humidity, lux, soil_moisture = struct.unpack_from('<4f', payload, 37)
        # soil_temperature[4] (offset 53)
        soil_temps = struct.unpack_from('<4f', payload, 53)
        # soil_temperature_count (offset 69)
        soil_temp_count = payload[69]
        # soil_moisture_capacitance[4] (offset 70)
        capacitance = struct.unpack_from('<4f', payload, 70)
        # ext_temperature (offset 86)
        ext_temperature = struct.unpack_from('<f', payload, 86)[0]
        # ext_temperature_valid (offset 90)
        ext_temperature_valid = payload[90]

        datetime_str = _format_tm(tm_year, tm_mon, tm_mday, tm_hour, tm_min, tm_sec)

        return {
            'data_version': data_version,
            'datetime': datetime_str,
            'lux': lux,
            'temperature': temperature,
            'humidity': humidity,
            'soil_moisture': soil_moisture,
            'soil_temperature': list(soil_temps),
            'soil_temperature_count': soil_temp_count,
            'capacitance': list(capacitance),
            'ext_temperature': ext_temperature,
            'ext_temperature_valid': bool(ext_temperature_valid),
        }
    except Exception as e:
        return {'error': str(e), 'raw': payload.hex()}


# ---------------------------------------------------------------------------
# soil_sensor_config_t パーサ (packed構造体)
#
# soil_sensor_config_t (packed, 99 bytes):
#   offset  0: uint8_t  hardware_version      (1 byte)
#   offset  1: uint8_t  data_structure_version (1 byte)
#   offset  2: soil_moisture_sensor_info_t     (22 bytes)
#     offset  2: uint8_t  sensor_type          (1)
#     offset  3: uint16_t probe_length_mm      (2)
#     offset  5: uint16_t sensing_length_mm    (2)
#     offset  7: uint8_t  channel_count        (1)
#     offset  8: float    capacitance_min_pf   (4)
#     offset 12: float    capacitance_max_pf   (4)
#     offset 16: float    measurement_range_min(4)
#     offset 20: float    measurement_range_max(4)
#   offset 24: uint8_t  soil_temp_sensor_count (1 byte)
#   offset 25: soil_temp_sensor_info_t x4      (4 * 15 = 60 bytes)
#     各15バイト:
#       uint8_t  device_type    (1)
#       int16_t  depth_mm       (2)
#       float    temp_min       (4)
#       float    temp_max       (4)
#       float    temp_resolution(4)
#   offset 85: ext_temp_sensor_info_t          (14 bytes)
#     offset 85: uint8_t  available            (1)
#     offset 86: uint8_t  device_type          (1)
#     offset 87: float    temp_min             (4)
#     offset 91: float    temp_max             (4)
#     offset 95: float    temp_resolution      (4)
#   Total: 99 bytes
# ---------------------------------------------------------------------------
SENSOR_CONFIG_SIZE = 99


def parse_sensor_config(payload: bytes) -> dict:
    """センサー構成情報をパース (soil_sensor_config_t, packed)"""
    if len(payload) < SENSOR_CONFIG_SIZE:
        return {'error': f'ペイロードが短すぎます: {len(payload)} bytes (期待: {SENSOR_CONFIG_SIZE})'}

    try:
        offset = 0
        hw_ver = payload[offset]; offset += 1
        ds_ver = payload[offset]; offset += 1

        # soil_moisture_sensor_info_t (22 bytes)
        m_type = payload[offset]; offset += 1
        probe_len, sense_len = struct.unpack_from('<HH', payload, offset); offset += 4
        ch_count = payload[offset]; offset += 1
        cap_min, cap_max, range_min, range_max = struct.unpack_from('<4f', payload, offset); offset += 16

        # soil_temp_sensor_count
        temp_count = payload[offset]; offset += 1

        # soil_temp_sensor_info_t x4 (各15バイト)
        soil_temps = []
        for i in range(4):
            dev_type = payload[offset]; offset += 1
            depth_mm = struct.unpack_from('<h', payload, offset)[0]; offset += 2
            t_min, t_max, t_res = struct.unpack_from('<3f', payload, offset); offset += 12
            soil_temps.append({
                'device_type': dev_type,
                'device_type_name': SOIL_TEMP_DEVICE_TYPES.get(dev_type, f'Unknown({dev_type})'),
                'depth_mm': depth_mm,
                'temp_min': t_min,
                'temp_max': t_max,
                'resolution': t_res,
            })

        # ext_temp_sensor_info_t (14 bytes)
        ext_avail = payload[offset]; offset += 1
        ext_type = payload[offset]; offset += 1
        ext_min, ext_max, ext_res = struct.unpack_from('<3f', payload, offset); offset += 12

        return {
            'hardware_version': hw_ver,
            'data_structure_version': ds_ver,
            'moisture_sensor': {
                'type': m_type,
                'type_name': MOISTURE_SENSOR_TYPES.get(m_type, f'Unknown({m_type})'),
                'probe_length_mm': probe_len,
                'sensing_length_mm': sense_len,
                'channel_count': ch_count,
                'capacitance_min_pf': cap_min,
                'capacitance_max_pf': cap_max,
                'measurement_range_min': range_min,
                'measurement_range_max': range_max,
            },
            'soil_temp_count': temp_count,
            'soil_temp_sensors': soil_temps,
            'ext_temp_sensor': {
                'available': bool(ext_avail),
                'device_type': ext_type,
                'device_type_name': SOIL_TEMP_DEVICE_TYPES.get(ext_type, f'Unknown({ext_type})'),
                'temp_min': ext_min,
                'temp_max': ext_max,
                'resolution': ext_res,
            }
        }
    except Exception as e:
        return {'error': str(e), 'raw': payload.hex()}


def parse_device_info(payload: bytes) -> dict:
    """デバイス情報をパース (device_info_t, packed)"""
    try:
        device_name = payload[0:32].decode('utf-8').rstrip('\x00')
        firmware_version = payload[32:48].decode('utf-8').rstrip('\x00')
        hardware_version = payload[48:64].decode('utf-8').rstrip('\x00')
        uptime, total_readings = struct.unpack('<II', payload[64:72])

        return {
            'device_name': device_name,
            'firmware_version': firmware_version,
            'hardware_version': hardware_version,
            'uptime_seconds': uptime,
            'total_sensor_readings': total_readings,
        }
    except Exception as e:
        return {'error': str(e), 'raw': payload.hex()}


def parse_system_status(payload: bytes) -> dict:
    """システムステータスをパース (system_status_t, packed)"""
    try:
        uptime, heap_free, heap_min, task_count, current_time = struct.unpack('<5I', payload[0:20])
        wifi_connected = payload[20]
        ble_connected = payload[21]

        if current_time > 0:
            device_time = datetime.fromtimestamp(current_time).strftime('%Y-%m-%d %H:%M:%S')
        else:
            device_time = "未設定"

        return {
            'uptime_seconds': uptime,
            'heap_free': heap_free,
            'heap_min': heap_min,
            'task_count': task_count,
            'current_time': current_time,
            'device_time': device_time,
            'wifi_connected': bool(wifi_connected),
            'ble_connected': bool(ble_connected),
        }
    except Exception as e:
        return {'error': str(e), 'raw': payload.hex()}


def _format_tm(tm_year, tm_mon, tm_mday, tm_hour, tm_min, tm_sec):
    """struct tmフィールドを日時文字列に変換"""
    try:
        dt = datetime(1900 + tm_year, tm_mon + 1, tm_mday, tm_hour, tm_min, tm_sec)
        return dt.strftime('%Y-%m-%d %H:%M:%S')
    except Exception:
        return f'{1900 + tm_year}-{tm_mon + 1:02d}-{tm_mday:02d} {tm_hour:02d}:{tm_min:02d}:{tm_sec:02d}'


def notification_handler(sender, data):
    """レスポンス通知ハンドラ"""
    global response_data
    response_data = data
    response_received.set()


async def scan_devices(timeout: float = 10.0) -> list:
    """BLEデバイスをスキャン (PlantMonitor_40のみフィルタ)"""
    print(f"  BLEデバイスをスキャン中... ({timeout}秒)")

    devices = await BleakScanner.discover(timeout=timeout)
    filtered = [d for d in devices if d.name and d.name.startswith(DEVICE_NAME_FILTER)]
    filtered.sort(key=lambda d: d.name)
    return filtered


async def select_device() -> str:
    """デバイスをスキャンして選択"""
    devices = await scan_devices()

    if not devices:
        print(f"  {DEVICE_NAME_FILTER} デバイスが見つかりませんでした")
        return None

    print(f"\n  {len(devices)} 個の {DEVICE_NAME_FILTER} デバイスが見つかりました")
    print("=" * 60)
    for i, device in enumerate(devices, 1):
        print(f"  {i:2d}. {device.name} ({device.address})")
    print("=" * 60)

    if len(devices) == 1:
        selected = devices[0]
        print(f"  自動選択: {selected.name} ({selected.address})")
        return selected.address

    while True:
        try:
            choice = input(f"\n接続するデバイス番号を入力 (1-{len(devices)}, 0で終了): ").strip()
            if choice == "0":
                return None
            idx = int(choice) - 1
            if 0 <= idx < len(devices):
                return devices[idx].address
        except (ValueError, EOFError):
            pass


async def send_command(client: BleakClient, command_id: int, data: bytes = b'', timeout: float = 5.0) -> dict:
    """コマンドを送信してレスポンスを待つ"""
    global response_data
    response_received.clear()
    response_data = None

    packet = create_command_packet(command_id, data)

    await client.write_gatt_char(COMMAND_UUID, packet)

    try:
        await asyncio.wait_for(response_received.wait(), timeout=timeout)
        if response_data:
            return parse_response_packet(response_data)
    except asyncio.TimeoutError:
        return {'error': 'タイムアウト'}

    return {'error': 'レスポンスなし'}


def print_separator(title: str, char: str = "=", width: int = 60):
    print(f"\n{char * width}")
    print(f"  {title}")
    print(f"{char * width}")


def print_sensor_data(sensor: dict):
    """センサーデータを表示"""
    if 'error' in sensor:
        print(f"  パースエラー: {sensor}")
        return

    print(f"  data_version    : {sensor['data_version']}")
    print(f"  日時            : {sensor['datetime']}")
    print(f"  気温            : {sensor['temperature']:.1f} C")
    print(f"  湿度            : {sensor['humidity']:.1f} %")
    print(f"  照度            : {sensor['lux']:.0f} lux")
    print(f"  土壌水分        : {sensor['soil_moisture']:.1f} pF")

    if 'sensor_error' in sensor:
        print(f"  センサーエラー  : {sensor['sensor_error']}")

    count = sensor.get('soil_temperature_count', 0)
    print(f"  土壌温度センサー数: {count}")
    for i in range(count):
        temp = sensor['soil_temperature'][i]
        print(f"    [TMP102 #{i}]   : {temp:.2f} C")

    caps = sensor.get('capacitance', [])
    if caps:
        cap_str = ', '.join(f'{c:.1f}' for c in caps)
        print(f"  静電容量 (pF)   : [{cap_str}]")

    if 'ext_temperature' in sensor:
        valid = sensor['ext_temperature_valid']
        ext_t = sensor['ext_temperature']
        status = f"{ext_t:.2f} C" if valid else "無効"
        print(f"  拡張温度 (DS18B20): {status}")


# ---------------------------------------------------------------------------
# テスト関数
# ---------------------------------------------------------------------------

async def test_device_info(client: BleakClient) -> dict:
    """テスト: デバイス情報取得"""
    print_separator("CMD_GET_DEVICE_INFO (0x06)")
    response = await send_command(client, CMD_GET_DEVICE_INFO)

    if response.get('status_code') == RESP_STATUS_SUCCESS:
        info = parse_device_info(response['payload'])
        if 'error' not in info:
            print(f"  デバイス名      : {info['device_name']}")
            print(f"  ファームウェア  : {info['firmware_version']}")
            print(f"  ハードウェア    : {info['hardware_version']}")
            print(f"  稼働時間        : {info['uptime_seconds']} 秒")
            print(f"  センサー読取回数: {info['total_sensor_readings']}")
            return info
        else:
            print(f"  パースエラー: {info}")
    else:
        print(f"  エラー: {response}")
    return None


async def test_system_status(client: BleakClient) -> dict:
    """テスト: システムステータス取得"""
    print_separator("CMD_GET_SYSTEM_STATUS (0x02)")
    response = await send_command(client, CMD_GET_SYSTEM_STATUS)

    if response.get('status_code') == RESP_STATUS_SUCCESS:
        status = parse_system_status(response['payload'])
        if 'error' not in status:
            print(f"  稼働時間        : {status['uptime_seconds']} 秒")
            print(f"  空きヒープ      : {status['heap_free']:,} bytes")
            print(f"  最小ヒープ      : {status['heap_min']:,} bytes")
            print(f"  タスク数        : {status['task_count']}")
            print(f"  デバイス時刻    : {status['device_time']}")
            print(f"  WiFi接続        : {status['wifi_connected']}")
            print(f"  BLE接続         : {status['ble_connected']}")
            return status
        else:
            print(f"  パースエラー: {status}")
    else:
        print(f"  エラー: {response}")
    return None


async def test_sensor_data(client: BleakClient) -> dict:
    """テスト: センサーデータ取得 (CMD_GET_SENSOR_DATA)"""
    print_separator("CMD_GET_SENSOR_DATA (0x01) - soil_data_t")
    response = await send_command(client, CMD_GET_SENSOR_DATA)

    if response.get('status_code') == RESP_STATUS_SUCCESS:
        payload = response['payload']
        print(f"  レスポンスサイズ: {len(payload)} bytes (期待: {SOIL_DATA_V3_SIZE})")

        sensor = parse_sensor_data_v3(payload)
        print_sensor_data(sensor)
        return sensor
    else:
        print(f"  エラー: {response}")
    return None


async def test_sensor_data_v2(client: BleakClient) -> dict:
    """テスト: センサーデータ取得V2 (CMD_GET_SENSOR_DATA_V2)"""
    print_separator("CMD_GET_SENSOR_DATA_V2 (0x17) - soil_data_t")
    response = await send_command(client, CMD_GET_SENSOR_DATA_V2)

    if response.get('status_code') == RESP_STATUS_SUCCESS:
        payload = response['payload']
        print(f"  レスポンスサイズ: {len(payload)} bytes (期待: {SOIL_DATA_V3_SIZE})")

        sensor = parse_sensor_data_v3(payload)
        print_sensor_data(sensor)
        return sensor
    else:
        print(f"  エラー: {response}")
    return None


async def test_time_data(client: BleakClient) -> dict:
    """テスト: 時間指定データ取得 (CMD_GET_TIME_DATA)"""
    print_separator("CMD_GET_TIME_DATA (0x0A) - time_data_response_t (packed)")

    # 現在時刻のstruct tmをリクエストとして送信
    now = time.localtime()
    # time_data_request_t = struct tm (9 * int32 = 36 bytes)
    request_data = struct.pack('<9i',
                               now.tm_sec, now.tm_min, now.tm_hour,
                               now.tm_mday, now.tm_mon - 1, now.tm_year - 1900,
                               now.tm_wday, now.tm_yday, now.tm_isdst)

    print(f"  リクエスト時刻: {time.strftime('%Y-%m-%d %H:%M:%S', now)}")

    response = await send_command(client, CMD_GET_TIME_DATA, request_data)

    if response.get('status_code') == RESP_STATUS_SUCCESS:
        payload = response['payload']
        print(f"  レスポンスサイズ: {len(payload)} bytes (期待: {TIME_DATA_RESPONSE_V3_SIZE})")

        data = parse_time_data_response_v3(payload)
        if 'error' not in data:
            print(f"  data_version    : {data['data_version']}")
            print(f"  実データ時刻    : {data['datetime']}")
            print(f"  気温            : {data['temperature']:.1f} C")
            print(f"  湿度            : {data['humidity']:.1f} %")
            print(f"  照度            : {data['lux']:.0f} lux")
            print(f"  土壌水分        : {data['soil_moisture']:.1f} pF")
            count = data.get('soil_temperature_count', 0)
            print(f"  土壌温度センサー数: {count}")
            for i in range(count):
                print(f"    [TMP102 #{i}]   : {data['soil_temperature'][i]:.2f} C")
            caps = data.get('capacitance', [])
            if caps:
                cap_str = ', '.join(f'{c:.1f}' for c in caps)
                print(f"  静電容量 (pF)   : [{cap_str}]")
            valid = data['ext_temperature_valid']
            ext_t = data['ext_temperature']
            print(f"  拡張温度 (DS18B20): {f'{ext_t:.2f} C' if valid else '無効'}")
            return data
        else:
            print(f"  パースエラー: {data}")
    elif response.get('status_code') == RESP_STATUS_ERROR:
        print(f"  データなし (指定時刻のバッファデータが見つかりません)")
    else:
        print(f"  エラー: {response}")
    return None


async def test_sensor_config(client: BleakClient) -> dict:
    """テスト: センサー構成情報取得 (CMD_GET_SENSOR_CONFIG)"""
    print_separator("CMD_GET_SENSOR_CONFIG (0x1A) - soil_sensor_config_t (packed)")
    response = await send_command(client, CMD_GET_SENSOR_CONFIG)

    if response.get('status_code') == RESP_STATUS_SUCCESS:
        payload = response['payload']
        print(f"  レスポンスサイズ: {len(payload)} bytes (期待: {SENSOR_CONFIG_SIZE})")

        config = parse_sensor_config(payload)
        if 'error' not in config:
            print(f"  ハードウェアVer : {config['hardware_version']}")
            print(f"  データ構造Ver   : {config['data_structure_version']}")
            print(f"  --- 土壌湿度センサー ---")
            ms = config['moisture_sensor']
            print(f"    タイプ        : {ms['type_name']}")
            print(f"    プローブ長    : {ms['probe_length_mm']} mm")
            print(f"    センシング長  : {ms['sensing_length_mm']} mm")
            print(f"    チャンネル数  : {ms['channel_count']}")
            print(f"    静電容量範囲  : {ms['capacitance_min_pf']:.1f} - {ms['capacitance_max_pf']:.1f} pF")
            print(f"    計測範囲      : {ms['measurement_range_min']:.1f} - {ms['measurement_range_max']:.1f}")
            print(f"  --- 土壌温度センサー (検出: {config['soil_temp_count']}台) ---")
            for i, ts in enumerate(config['soil_temp_sensors']):
                if i < config['soil_temp_count']:
                    print(f"    [{i}] {ts['device_type_name']}: "
                          f"深さ {ts['depth_mm']}mm, "
                          f"範囲 {ts['temp_min']:.1f}~{ts['temp_max']:.1f}C, "
                          f"分解能 {ts['resolution']:.4f}C")
                else:
                    print(f"    [{i}] {ts['device_type_name']} (未接続)")
            print(f"  --- 拡張温度センサー ---")
            ext = config['ext_temp_sensor']
            if ext['available']:
                print(f"    タイプ        : {ext['device_type_name']}")
                print(f"    範囲          : {ext['temp_min']:.1f}~{ext['temp_max']:.1f}C")
                print(f"    分解能        : {ext['resolution']:.4f}C")
            else:
                print(f"    なし")
            return config
        else:
            print(f"  パースエラー: {config}")
    else:
        print(f"  エラー: {response}")
    return None


async def test_all(address: str):
    """全データ取得テスト"""
    print(f"\n  {address} に接続中...")

    async with BleakClient(address) as client:
        print(f"  接続成功!")
        await client.start_notify(RESPONSE_UUID, notification_handler)
        print(f"  レスポンス通知を購読しました\n")

        # テスト1: デバイス情報
        await test_device_info(client)
        await asyncio.sleep(0.5)

        # テスト2: システムステータス
        await test_system_status(client)
        await asyncio.sleep(0.5)

        # テスト3: センサーデータ (CMD_GET_SENSOR_DATA)
        await test_sensor_data(client)
        await asyncio.sleep(0.5)

        # テスト4: センサーデータV2 (CMD_GET_SENSOR_DATA_V2)
        await test_sensor_data_v2(client)
        await asyncio.sleep(0.5)

        # テスト5: 時間指定データ取得
        await test_time_data(client)
        await asyncio.sleep(0.5)

        # テスト6: センサー構成情報
        await test_sensor_config(client)

        await client.stop_notify(RESPONSE_UUID)
        print_separator("全テスト完了", "-")


async def continuous_monitor(address: str, interval: float = 5.0):
    """連続モニタリング"""
    print(f"\n  {address} に接続中...")

    async with BleakClient(address) as client:
        print(f"  接続成功!")
        await client.start_notify(RESPONSE_UUID, notification_handler)

        print(f"\n  {interval}秒間隔でセンサーデータを取得中... (Ctrl+C で終了)\n")

        header = (
            f"{'日時':>19s} | "
            f"{'気温':>5s} | {'湿度':>5s} | {'照度':>6s} | "
            f"{'土壌':>7s} | "
            f"{'Cap0':>7s} {'Cap1':>7s} {'Cap2':>7s} {'Cap3':>7s} | "
            f"{'ST0':>6s} {'ST1':>6s} {'ST2':>6s} {'ST3':>6s} | "
            f"{'Ext':>6s}"
        )
        print(header)
        print("-" * len(header))

        try:
            while True:
                response = await send_command(client, CMD_GET_SENSOR_DATA)
                if response.get('status_code') == RESP_STATUS_SUCCESS:
                    sensor = parse_sensor_data_v3(response['payload'])
                    if 'error' not in sensor:
                        count = sensor['soil_temperature_count']
                        st = sensor['soil_temperature']
                        st_str = ' '.join(
                            f'{st[i]:6.2f}' if i < count else '  ----'
                            for i in range(4)
                        )
                        caps = sensor.get('capacitance', [0, 0, 0, 0])
                        cap_str = ' '.join(f'{c:7.1f}' for c in caps)
                        ext_valid = sensor.get('ext_temperature_valid', False)
                        ext_t = sensor.get('ext_temperature', 0.0)
                        ext_str = f'{ext_t:6.2f}' if ext_valid else '  ----'

                        print(
                            f"{sensor['datetime']:>19s} | "
                            f"{sensor['temperature']:5.1f} | "
                            f"{sensor['humidity']:5.1f} | "
                            f"{sensor['lux']:6.0f} | "
                            f"{sensor['soil_moisture']:7.1f} | "
                            f"{cap_str} | "
                            f"{st_str} | "
                            f"{ext_str}"
                        )
                    else:
                        print(f"パースエラー: {sensor}")
                else:
                    print(f"エラー: {response}")

                await asyncio.sleep(interval)
        except KeyboardInterrupt:
            print("\n  モニタリング終了")

        await client.stop_notify(RESPONSE_UUID)


async def main():
    """メイン関数"""
    print("=" * 60)
    print("  PlantMonitor Rev4 (HW40) データ取得テスト")
    print("=" * 60)

    address = await select_device()
    if address is None:
        return

    print("\n  テストモードを選択してください:")
    print("  1. 全コマンドテスト（デバイス情報, ステータス, センサーデータ, 時間指定, 構成情報）")
    print("  2. 連続モニタリング（5秒間隔でセンサーデータ取得）")
    print("  3. 終了")

    try:
        choice = input("\n選択 (1-3): ").strip()
    except EOFError:
        choice = "1"

    if choice == "1":
        await test_all(address)
    elif choice == "2":
        await continuous_monitor(address)
    else:
        print("終了します")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n  終了")
    except Exception as e:
        print(f"\n  エラー: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
