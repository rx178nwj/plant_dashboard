# blueprints/devices/routes.py
from flask import Blueprint, render_template, jsonify, request, Response
import asyncio
import json
import logging
import random
import device_manager as dm
from ble_manager import scan_devices as ble_scan
from blueprints.dashboard.routes import requires_auth
import config  # configをインポート
from bleak import BleakClient

devices_bp = Blueprint('devices', __name__, template_folder='../../templates')
logger = logging.getLogger(__name__)


def determine_data_version(device_name):
    """
    デバイス名からdata_versionを判定する

    PlantMonitor_XX_YYYY形式のデバイス名から、XXの部分(ハードウェアバージョン)を取得し、
    30以上ならdata_version=2、それ以外はdata_version=1を返す

    Args:
        device_name: デバイス名 (例: "PlantMonitor_30_B9B2", "PlantMonitor_20_DA06")

    Returns:
        int: data_version (1 or 2)
    """
    if not device_name:
        return 1

    # PlantMonitor_XX_YYYY形式のデバイス名からハードウェアバージョンを抽出
    if device_name.startswith('PlantMonitor_'):
        parts = device_name.split('_')
        if len(parts) >= 2:
            try:
                hw_version = int(parts[1])
                # ハードウェアバージョン30以上はdata_version=2
                if hw_version >= 30:
                    return 2
            except ValueError:
                # 数値に変換できない場合はデフォルト値を返す
                logger.warning(f"デバイス名 '{device_name}' からハードウェアバージョンを抽出できませんでした")

    # デフォルトはdata_version=1
    return 1


@devices_bp.route('/devices')
@requires_auth
def devices():
    """デバイス管理ページを表示します。"""
    conn = dm.get_db_connection()
    registered_devices = conn.execute('SELECT * FROM devices ORDER BY device_name').fetchall()
    conn.close()
    return render_template('devices.html', registered_devices=registered_devices)


@devices_bp.route('/devices/profiles')
@requires_auth
def devices_profiles():
    """デバイスプロファイル管理ページを表示します。"""
    conn = dm.get_db_connection()
    registered_devices = conn.execute('SELECT * FROM devices ORDER BY device_type, device_name').fetchall()

    # 各デバイスに最新のセンサーデータと関連する植物情報を追加
    devices_with_data = []
    for device in registered_devices:
        device_dict = dict(device)

        # 最新のセンサーデータを取得
        sensor_data = conn.execute("""
            SELECT *
            FROM sensor_data
            WHERE device_id = ?
            ORDER BY timestamp DESC
            LIMIT 1
        """, (device['device_id'],)).fetchone()

        device_dict['sensor_data'] = dict(sensor_data) if sensor_data else {}

        # plant sensorの場合、関連する植物情報を取得
        if device['device_type'] == 'plant_sensor':
            plant_info = conn.execute("""
                SELECT
                    mp.managed_plant_id,
                    mp.plant_name,
                    p.genus,
                    p.species,
                    COALESCE(mp.image_url, p.image_url) as display_image_url
                FROM managed_plants mp
                LEFT JOIN plants p ON mp.library_plant_id = p.plant_id
                WHERE mp.assigned_plant_sensor_id = ?
            """, (device['device_id'],)).fetchone()

            device_dict['assigned_plant'] = dict(plant_info) if plant_info else None
        else:
            device_dict['assigned_plant'] = None

        devices_with_data.append(device_dict)

    conn.close()
    return render_template('devices_profiles.html', registered_devices=devices_with_data)


@devices_bp.route('/devices/profile/<device_id>')
@requires_auth
def device_profile_detail(device_id):
    """デバイス詳細ページを表示します。"""
    conn = dm.get_db_connection()

    # デバイス情報を取得
    device = conn.execute('SELECT * FROM devices WHERE device_id = ?', (device_id,)).fetchone()

    if not device:
        conn.close()
        return "Device not found", 404

    device_dict = dict(device)

    # 最新のセンサーデータを取得
    sensor_data = conn.execute("""
        SELECT *
        FROM sensor_data
        WHERE device_id = ?
        ORDER BY timestamp DESC
        LIMIT 1
    """, (device_id,)).fetchone()

    device_dict['sensor_data'] = dict(sensor_data) if sensor_data else {}

    # plant sensorの場合、関連する植物情報を取得
    if device['device_type'] == 'plant_sensor':
        plant_info = conn.execute("""
            SELECT
                mp.managed_plant_id,
                mp.plant_name,
                p.genus,
                p.species,
                COALESCE(mp.image_url, p.image_url) as display_image_url
            FROM managed_plants mp
            LEFT JOIN plants p ON mp.library_plant_id = p.plant_id
            WHERE mp.assigned_plant_sensor_id = ?
        """, (device_id,)).fetchone()

        device_dict['assigned_plant'] = dict(plant_info) if plant_info else None
    else:
        device_dict['assigned_plant'] = None

    conn.close()
    return render_template('device_detail.html', device=device_dict)


@devices_bp.route('/devices/threshold/<device_id>')
@requires_auth
def device_threshold_config(device_id):
    """デバイスの閾値設定ページを表示します。"""
    conn = dm.get_db_connection()

    # デバイス情報を取得
    device = conn.execute('SELECT * FROM devices WHERE device_id = ?', (device_id,)).fetchone()

    if not device:
        conn.close()
        return "Device not found", 404

    device_dict = dict(device)

    # plant sensorの場合、関連する植物情報を取得
    if device['device_type'] == 'plant_sensor':
        plant_info = conn.execute("""
            SELECT
                mp.managed_plant_id,
                mp.plant_name,
                mp.library_plant_id,
                p.genus,
                p.species,
                COALESCE(mp.image_url, p.image_url) as display_image_url
            FROM managed_plants mp
            LEFT JOIN plants p ON mp.library_plant_id = p.plant_id
            WHERE mp.assigned_plant_sensor_id = ?
        """, (device_id,)).fetchone()

        device_dict['assigned_plant'] = dict(plant_info) if plant_info else None
    else:
        device_dict['assigned_plant'] = None

    conn.close()
    return render_template('device_threshold.html', device=device_dict)


@devices_bp.route('/devices/edit/<device_id>')
@requires_auth
def edit_device(device_id):
    """デバイス編集ページを表示します。"""
    conn = dm.get_db_connection()
    device = conn.execute('SELECT * FROM devices WHERE device_id = ?', (device_id,)).fetchone()
    
    if not device:
        conn.close()
        return "Device not found", 404

    device_dict = dict(device)

    # 紐づいているプラント情報を取得
    plant_info = conn.execute("""
        SELECT
            mp.managed_plant_id,
            mp.plant_name,
            p.genus,
            p.species,
            COALESCE(mp.image_url, p.image_url) as display_image_url
        FROM managed_plants mp
        LEFT JOIN plants p ON mp.library_plant_id = p.plant_id
        WHERE mp.assigned_plant_sensor_id = ? OR mp.assigned_switchbot_id = ?
    """, (device_id, device_id)).fetchone()
    device_dict['assigned_plant'] = dict(plant_info) if plant_info else None
    conn.close()

    # テンプレート表示用のダミーデータ/初期値
    # 実際にはデバイスから取得するか、DBの別テーブルから取得する
    device_info = {
        "device_name": device['device_name'],
        "firmware_version": "Unknown",
        "hardware_version": "Unknown",
        "total_sensor_readings": 0
    }
    
    system_status = {
        "uptime_seconds": 0,
        "heap_free": 0,
        "task_count": 0,
        "current_time_str": "--",
        "wifi_connected": False,
        "ble_connected": False
    }
    
    plant_profile = {
        "plant_name": "Unknown",
        "soil_dry_threshold": 0,
        "soil_wet_threshold": 0,
        "soil_dry_days_for_watering": 0,
        "temp_high_limit": 0,
        "temp_low_limit": 0,
        "watering_threshold": 0
    }
    
    wifi_config = {
        "ssid": "--",
        "password": "--"
    }
    
    timezone = "Asia/Tokyo"
    
    sensor_config = {
        "hardware_version": 0,
        "data_structure_version": 0,
        "moisture_sensor": {"sensor_type": 0, "probe_length_mm": 0},
        "soil_temp_sensors": [],
        "ext_temp_sensor": {"available": False}
    }

    return render_template('device_edit.html', 
                           device=device_dict,
                           device_info=device_info,
                           system_status=system_status,
                           plant_profile=plant_profile,
                           wifi_config=wifi_config,
                           timezone=timezone,
                           sensor_config=sensor_config)


async def read_device_settings_from_ble(mac_address):
    """
    BLE経由でデバイスから設定情報を読み込む非同期関数
    コマンド/レスポンスプロトコルを使用して以下を取得:
    - CMD_GET_DEVICE_INFO (0x06)
    - CMD_GET_SYSTEM_STATUS (0x02)
    - CMD_GET_PLANT_PROFILE (0x0C)
    - CMD_GET_WIFI_CONFIG (0x0E)
    - CMD_GET_TIMEZONE (0x10)
    - CMD_GET_SENSOR_CONFIG (0x1A)
    """
    import struct
    from datetime import datetime

    SERVICE_UUID = "592F4612-9543-9999-12C8-58B459A2712D"
    COMMAND_UUID = "6A3B2C1D-4E5F-6A7B-8C9D-E0F123456791"
    RESPONSE_UUID = "6A3B2C1D-4E5F-6A7B-8C9D-E0F123456792"

    CMD_GET_SYSTEM_STATUS = 0x02
    CMD_GET_DEVICE_INFO = 0x06
    CMD_GET_PLANT_PROFILE = 0x0C
    CMD_GET_WIFI_CONFIG = 0x0E
    CMD_GET_TIMEZONE = 0x10
    CMD_GET_SENSOR_CONFIG = 0x1A

    response_data = {}

    def notification_handler(sender, data):
        if len(data) >= 5:
            resp_id = data[0]
            response_data[resp_id] = data

    async def send_command(client, command_id, seq=0, data=b""):
        packet = struct.pack("<BBH", command_id, seq, len(data)) + data
        await client.write_gatt_char(COMMAND_UUID, packet, response=False)

        for _ in range(50):  # 5秒タイムアウト
            if command_id in response_data:
                break
            await asyncio.sleep(0.1)

        if command_id not in response_data:
            raise Exception(f"Response timeout for command 0x{command_id:02X}")

        raw = response_data.pop(command_id)
        resp_id = raw[0]
        status = raw[1]
        resp_seq = raw[2]
        data_len = struct.unpack("<H", raw[3:5])[0]
        resp_payload = raw[5:]

        if status != 0x00:
            raise Exception(f"Command 0x{command_id:02X} failed with status 0x{status:02X}")

        return resp_payload

    logger.info(f"Connecting to {mac_address} to fetch settings...")

    async with BleakClient(mac_address) as client:
        await client.start_notify(RESPONSE_UUID, notification_handler)

        try:
            # CMD_GET_DEVICE_INFO (0x06) - 72バイト
            raw = await send_command(client, CMD_GET_DEVICE_INFO, seq=1)
            device_name = raw[:32].decode('utf-8').rstrip('\x00')
            fw_ver = raw[32:48].decode('utf-8').rstrip('\x00')
            hw_ver = raw[48:64].decode('utf-8').rstrip('\x00')
            uptime_dev, total_readings = struct.unpack("<II", raw[64:72])
            device_info = {
                "device_name": device_name,
                "firmware_version": fw_ver,
                "hardware_version": hw_ver,
                "total_sensor_readings": total_readings
            }

            # CMD_GET_SYSTEM_STATUS (0x02) - 24バイト
            raw = await send_command(client, CMD_GET_SYSTEM_STATUS, seq=2)
            uptime, heap_free, heap_min, task_count, current_time, wifi_connected, ble_connected = \
                struct.unpack('<IIIIIBBxx', raw[:24])
            if current_time > 0:
                current_time_str = datetime.fromtimestamp(current_time).strftime('%Y-%m-%d %H:%M:%S')
            else:
                current_time_str = "未設定"
            system_status = {
                "uptime_seconds": uptime,
                "heap_free": heap_free,
                "heap_min": heap_min,
                "task_count": task_count,
                "current_time_str": current_time_str,
                "wifi_connected": bool(wifi_connected),
                "ble_connected": bool(ble_connected)
            }

            # CMD_GET_PLANT_PROFILE (0x0C) - 60バイト
            raw = await send_command(client, CMD_GET_PLANT_PROFILE, seq=3)
            p_name = raw[:32].decode('utf-8').rstrip('\x00')
            p_dry, p_wet, p_days, p_temp_high, p_temp_low, p_watering = \
                struct.unpack("<ffifff", raw[32:60])
            plant_profile = {
                "plant_name": p_name,
                "soil_dry_threshold": round(p_dry, 2),
                "soil_wet_threshold": round(p_wet, 2),
                "soil_dry_days_for_watering": p_days,
                "temp_high_limit": round(p_temp_high, 2),
                "temp_low_limit": round(p_temp_low, 2),
                "watering_threshold": round(p_watering, 2)
            }

            # CMD_GET_WIFI_CONFIG (0x0E) - 96バイト
            try:
                raw = await send_command(client, CMD_GET_WIFI_CONFIG, seq=4)
                ssid = raw[:32].decode('utf-8').rstrip('\x00')
                password_masked = raw[32:96].decode('utf-8').rstrip('\x00')
                wifi_config = {
                    "ssid": ssid,
                    "password": password_masked
                }
            except Exception as e:
                logger.warning(f"Failed to get WiFi config: {e}")
                wifi_config = {"ssid": "", "password": ""}

            # CMD_GET_TIMEZONE (0x10)
            try:
                raw = await send_command(client, CMD_GET_TIMEZONE, seq=5)
                timezone = raw.decode('utf-8').rstrip('\x00')
            except Exception as e:
                logger.warning(f"Failed to get timezone: {e}")
                timezone = ""

            # CMD_GET_SENSOR_CONFIG (0x1A)
            try:
                raw = await send_command(client, CMD_GET_SENSOR_CONFIG, seq=6)
                offset = 0
                hw_ver_num, ds_ver = struct.unpack_from('<BB', raw, offset); offset += 2

                # 土壌湿度センサー (22バイト)
                m_type, probe_len, sense_len, ch_count = struct.unpack_from('<BHHB', raw, offset); offset += 6
                cap_min, cap_max, range_min, range_max = struct.unpack_from('<ffff', raw, offset); offset += 16

                # 土壌温度センサー
                temp_count = struct.unpack_from('<B', raw, offset)[0]; offset += 1
                soil_temps = []
                for i in range(4):
                    dev_type, depth = struct.unpack_from('<bh', raw, offset); offset += 3
                    t_min, t_max, t_res = struct.unpack_from('<fff', raw, offset); offset += 12
                    soil_temps.append({
                        'device_type': dev_type, 'depth_mm': depth,
                        'temp_min': round(t_min, 4), 'temp_max': round(t_max, 4),
                        'resolution': round(t_res, 4)
                    })

                # 拡張温度センサー (14バイト)
                ext_avail, ext_type = struct.unpack_from('<BB', raw, offset); offset += 2
                ext_min, ext_max, ext_res = struct.unpack_from('<fff', raw, offset); offset += 12

                sensor_config = {
                    'hardware_version': hw_ver_num,
                    'data_structure_version': ds_ver,
                    'moisture_sensor': {
                        'sensor_type': m_type,
                        'probe_length_mm': probe_len,
                        'sensing_length_mm': sense_len,
                        'channel_count': ch_count,
                        'capacitance_min_pf': round(cap_min, 2),
                        'capacitance_max_pf': round(cap_max, 2),
                    },
                    'soil_temp_count': temp_count,
                    'soil_temp_sensors': soil_temps[:temp_count],
                    'ext_temp_sensor': {
                        'available': bool(ext_avail),
                        'device_type': ext_type,
                        'temp_min': round(ext_min, 2),
                        'temp_max': round(ext_max, 2),
                        'resolution': round(ext_res, 4)
                    }
                }
            except Exception as e:
                logger.warning(f"Failed to get sensor config: {e}")
                sensor_config = {
                    'hardware_version': 0, 'data_structure_version': 0,
                    'moisture_sensor': {'sensor_type': 0, 'probe_length_mm': 0},
                    'soil_temp_sensors': [],
                    'ext_temp_sensor': {'available': False, 'device_type': 0}
                }

        finally:
            await client.stop_notify(RESPONSE_UUID)

    return {
        "device_info": device_info,
        "system_status": system_status,
        "plant_profile": plant_profile,
        "wifi_config": wifi_config,
        "timezone": timezone,
        "sensor_config": sensor_config
    }


async def write_device_settings_to_ble(mac_address, settings):
    """
    BLE経由でデバイスに設定情報を書き込む非同期関数
    コマンド/レスポンスプロトコルを使用して以下を書き込み・NVS保存:
    - CMD_SET_PLANT_PROFILE (0x03) + CMD_SAVE_PLANT_PROFILE (0x14)
    - CMD_SET_WIFI_CONFIG (0x0D) + CMD_SAVE_WIFI_CONFIG (0x13)
    - CMD_SET_TIMEZONE (0x15) + CMD_SAVE_TIMEZONE (0x16)
    """
    import struct

    COMMAND_UUID = "6A3B2C1D-4E5F-6A7B-8C9D-E0F123456791"
    RESPONSE_UUID = "6A3B2C1D-4E5F-6A7B-8C9D-E0F123456792"

    CMD_SET_PLANT_PROFILE = 0x03
    CMD_SET_WIFI_CONFIG = 0x0D
    CMD_SAVE_WIFI_CONFIG = 0x13
    CMD_SAVE_PLANT_PROFILE = 0x14
    CMD_SET_TIMEZONE = 0x15
    CMD_SAVE_TIMEZONE = 0x16

    response_data = {}

    def notification_handler(sender, data):
        if len(data) >= 5:
            resp_id = data[0]
            response_data[resp_id] = data

    async def send_command(client, command_id, seq=0, data=b""):
        packet = struct.pack("<BBH", command_id, seq, len(data)) + data
        await client.write_gatt_char(COMMAND_UUID, packet, response=False)

        for _ in range(50):  # 5秒タイムアウト
            if command_id in response_data:
                break
            await asyncio.sleep(0.1)

        if command_id not in response_data:
            raise Exception(f"Response timeout for command 0x{command_id:02X}")

        raw = response_data.pop(command_id)
        status = raw[1]

        if status != 0x00:
            raise Exception(f"Command 0x{command_id:02X} failed with status 0x{status:02X}")

        return raw[5:]

    logger.info(f"Connecting to {mac_address} to write settings...")
    seq = 0

    async with BleakClient(mac_address) as client:
        await client.start_notify(RESPONSE_UUID, notification_handler)

        try:
            # Plant Profile書き込み
            if 'plant_profile' in settings:
                pp = settings['plant_profile']
                name_bytes = pp.get('plant_name', '').encode('utf-8')[:31].ljust(32, b'\x00')
                profile_data = name_bytes + struct.pack(
                    "<ffifff",
                    float(pp.get('soil_dry_threshold', 0)),
                    float(pp.get('soil_wet_threshold', 0)),
                    int(pp.get('soil_dry_days_for_watering', 0)),
                    float(pp.get('temp_high_limit', 0)),
                    float(pp.get('temp_low_limit', 0)),
                    float(pp.get('watering_threshold', 0))
                )
                seq += 1
                await send_command(client, CMD_SET_PLANT_PROFILE, seq=seq, data=profile_data)
                logger.info("Plant profile written to device")

                # NVSに保存
                seq += 1
                await send_command(client, CMD_SAVE_PLANT_PROFILE, seq=seq)
                logger.info("Plant profile saved to NVS")

            # WiFi設定書き込み
            if 'wifi_config' in settings:
                wc = settings['wifi_config']
                ssid = wc.get('ssid', '')
                password = wc.get('password', '')

                # パスワードがマスク値（例: "abc***"）の場合は書き込みをスキップ
                if ssid and password and not password.endswith('***'):
                    ssid_bytes = ssid.encode('utf-8')[:31].ljust(32, b'\x00')
                    password_bytes = password.encode('utf-8')[:63].ljust(64, b'\x00')
                    wifi_data = ssid_bytes + password_bytes

                    seq += 1
                    await send_command(client, CMD_SET_WIFI_CONFIG, seq=seq, data=wifi_data)
                    logger.info("WiFi config written to device")

                    # NVSに保存
                    seq += 1
                    await send_command(client, CMD_SAVE_WIFI_CONFIG, seq=seq)
                    logger.info("WiFi config saved to NVS")
                else:
                    logger.info("WiFi password is masked, skipping WiFi config write")

            # タイムゾーン設定書き込み
            if 'timezone' in settings and settings['timezone']:
                tz_str = settings['timezone']
                tz_bytes = tz_str.encode('utf-8')
                if len(tz_bytes) > 63:
                    raise ValueError("Timezone string too long (max 63 bytes)")
                tz_data = tz_bytes + b'\x00'

                try:
                    seq += 1
                    await send_command(client, CMD_SET_TIMEZONE, seq=seq, data=tz_data)
                    logger.info(f"Timezone set to: {tz_str}")

                    # NVSに保存
                    seq += 1
                    await send_command(client, CMD_SAVE_TIMEZONE, seq=seq)
                    logger.info("Timezone saved to NVS")
                except Exception as e:
                    logger.warning(f"Failed to set timezone: {e}")

        finally:
            await client.stop_notify(RESPONSE_UUID)

    return True


async def read_device_data_at_time_from_ble(mac_address, target_time):
    """
    BLE経由で指定時刻のデータを取得する非同期関数 (Mock)
    """
    logger.info(f"Fetching data from {mac_address} at {target_time}...")
    
    # 通信遅延のシミュレーション
    await asyncio.sleep(1.5)
    
    return {
        "timestamp": target_time,
        "temperature": round(random.uniform(20.0, 30.0), 1),
        "humidity": round(random.uniform(40.0, 70.0), 1),
        "light_lux": int(random.uniform(100, 1000)),
        "soil_moisture": int(random.uniform(1500, 3000)),
        "soil_temperature1": round(random.uniform(18.0, 25.0), 1)
    }


async def update_device_firmware_ble(mac_address, firmware_file):
    """
    BLE経由でファームウェアを更新する非同期関数 (Mock)
    """
    logger.info(f"Starting firmware update for {mac_address}...")
    # 実際にはここでファイルを読み込み、BLE経由でパケット送信を行う
    # file_content = firmware_file.read()
    
    # 更新プロセスのシミュレーション
    await asyncio.sleep(3)
    
    return True


async def reboot_device_ble(mac_address):
    """
    BLE経由でデバイスを再起動する非同期関数 (Mock)
    """
    logger.info(f"Sending reboot command to {mac_address}...")
    # 実際にはここで再起動コマンドを書き込む
    # await client.write_gatt_char(UUID_CONTROL_POINT, b'\x01')
    await asyncio.sleep(1)
    return True


@devices_bp.route('/api/device/<device_id>/fetch-settings')
@requires_auth
def api_fetch_device_settings(device_id):
    """デバイスから最新の設定情報を取得するAPI"""
    conn = dm.get_db_connection()
    device = conn.execute('SELECT * FROM devices WHERE device_id = ?', (device_id,)).fetchone()
    conn.close()

    if not device:
        return jsonify({'success': False, 'message': 'Device not found'}), 404

    try:
        # 非同期関数を実行して設定を取得
        settings = asyncio.run(read_device_settings_from_ble(device['mac_address']))
        return jsonify({'success': True, 'data': settings})
    except Exception as e:
        logger.error(f"Failed to fetch settings from device: {e}", exc_info=True)
        return jsonify({'success': False, 'message': f"Communication error: {str(e)}"}), 500


@devices_bp.route('/api/device/<device_id>/update-settings', methods=['POST'])
@requires_auth
def api_update_device_settings(device_id):
    """デバイスに設定情報を書き込むAPI"""
    data = request.json
    conn = dm.get_db_connection()
    device = conn.execute('SELECT * FROM devices WHERE device_id = ?', (device_id,)).fetchone()
    conn.close()

    if not device:
        return jsonify({'success': False, 'message': 'Device not found'}), 404

    try:
        # 非同期関数を実行して設定を書き込む
        asyncio.run(write_device_settings_to_ble(device['mac_address'], data))
        return jsonify({'success': True, 'message': 'Settings successfully written to device.'})
    except Exception as e:
        logger.error(f"Failed to write settings to device: {e}", exc_info=True)
        return jsonify({'success': False, 'message': f"Communication error: {str(e)}"}), 500


@devices_bp.route('/api/device/<device_id>/update-firmware', methods=['POST'])
@requires_auth
def api_update_firmware(device_id):
    """デバイスのファームウェアを更新するAPI"""
    if 'firmware_file' not in request.files:
        return jsonify({'success': False, 'message': 'No file part'}), 400
    
    file = request.files['firmware_file']
    if file.filename == '':
        return jsonify({'success': False, 'message': 'No selected file'}), 400

    conn = dm.get_db_connection()
    device = conn.execute('SELECT * FROM devices WHERE device_id = ?', (device_id,)).fetchone()
    conn.close()

    if not device:
        return jsonify({'success': False, 'message': 'Device not found'}), 404

    try:
        # 非同期関数を実行
        asyncio.run(update_device_firmware_ble(device['mac_address'], file))
        return jsonify({'success': True, 'message': 'Firmware update initiated successfully. The device will reboot.'})
    except Exception as e:
        logger.error(f"Failed to update firmware: {e}", exc_info=True)
        return jsonify({'success': False, 'message': f"Update failed: {str(e)}"}), 500


@devices_bp.route('/api/device/<device_id>/reboot', methods=['POST'])
@requires_auth
def api_reboot_device(device_id):
    """デバイスを再起動するAPI"""
    conn = dm.get_db_connection()
    device = conn.execute('SELECT * FROM devices WHERE device_id = ?', (device_id,)).fetchone()
    conn.close()

    if not device:
        return jsonify({'success': False, 'message': 'Device not found'}), 404

    try:
        # 非同期関数を実行
        asyncio.run(reboot_device_ble(device['mac_address']))
        return jsonify({'success': True, 'message': 'Device is rebooting...'})
    except Exception as e:
        logger.error(f"Failed to reboot device: {e}", exc_info=True)
        return jsonify({'success': False, 'message': f"Reboot failed: {str(e)}"}), 500


@devices_bp.route('/api/device/<device_id>/fetch-data-at-time', methods=['POST'])
@requires_auth
def api_fetch_device_data_at_time(device_id):
    """指定された日時のデータをデバイスから取得するAPI"""
    data = request.json
    target_time = data.get('target_time')
    
    conn = dm.get_db_connection()
    device = conn.execute('SELECT * FROM devices WHERE device_id = ?', (device_id,)).fetchone()
    conn.close()

    if not device:
        return jsonify({'success': False, 'message': 'Device not found'}), 404

    try:
        result = asyncio.run(read_device_data_at_time_from_ble(device['mac_address'], target_time))
        return jsonify({'success': True, 'data': result})
    except Exception as e:
        logger.error(f"Failed to fetch data from device: {e}", exc_info=True)
        return jsonify({'success': False, 'message': f"Communication error: {str(e)}"}), 500


@devices_bp.route('/api/ble-scan', methods=['POST'])
@requires_auth
def api_ble_scan():
    """周辺のBLEデバイスをスキャンして結果を返します。"""
    try:
        # 非同期関数であるble_scanを実行し、結果を待つ
        devices = asyncio.run(ble_scan())
        return jsonify({'success': True, 'devices': devices})
    except Exception as e:
        logger.error(f"BLEスキャンに失敗しました: {e}", exc_info=True)
        return jsonify({'success': False, 'message': str(e)}), 500


@devices_bp.route('/api/add-device', methods=['POST'])
@requires_auth
def api_add_device():
    """新しいデバイスをデータベースに登録します。"""
    data = request.json
    try:
        conn = dm.get_db_connection()
        # device_typeを先頭に使用してユニークなIDを生成
        # MACアドレスの末尾6桁を追加
        device_type = data['device_type']
        mac_suffix = data['mac_address'].replace(':', '')[-6:].lower()
        device_id = f"{device_type}_{mac_suffix}"

        # デバイス名からdata_versionを自動判定
        device_name = data['device_name']
        data_version = determine_data_version(device_name)
        logger.info(f"デバイス '{device_name}' のdata_versionを {data_version} として登録します")

        conn.execute(
            "INSERT INTO devices (device_id, device_name, mac_address, device_type, data_version) VALUES (?, ?, ?, ?, ?)",
            (device_id, device_name, data['mac_address'], data['device_type'], data_version)
        )
        conn.commit()
        conn.close()
        dm.load_devices_from_db()  # メモリ上のデバイスリストを再読み込み
        return jsonify({'success': True, 'message': 'デバイスが正常に追加されました。'})
    except Exception as e:
        logger.error(f"デバイスの追加に失敗しました: {e}", exc_info=True)
        # データベースの一意性制約エラーなどを考慮
        return jsonify({'success': False, 'message': f'デバイスの追加に失敗しました: {e}'}), 500


@devices_bp.route('/api/device/<device_id>', methods=['PUT'])
@requires_auth
def api_update_device(device_id):
    """デバイス情報を更新します。"""
    data = request.json
    try:
        conn = dm.get_db_connection()
        # デバイスが存在するか確認
        device = conn.execute('SELECT * FROM devices WHERE device_id = ?', (device_id,)).fetchone()
        if not device:
            conn.close()
            return jsonify({'success': False, 'message': 'デバイスが見つかりません。'}), 404

        # デバイス名のみ更新可能とする（必要に応じて他のフィールドも追加可能）
        conn.execute(
            "UPDATE devices SET device_name = ? WHERE device_id = ?",
            (data.get('device_name'), device_id)
        )
        conn.commit()
        conn.close()
        dm.load_devices_from_db()  # メモリ上のデバイスリストを再読み込み
        return jsonify({'success': True, 'message': 'デバイス情報を更新しました。'})
    except Exception as e:
        logger.error(f"デバイスの更新に失敗しました: {e}", exc_info=True)
        return jsonify({'success': False, 'message': f'デバイスの更新に失敗しました: {e}'}), 500


@devices_bp.route('/api/device/<sensor_id>/write-watering-profile', methods=['POST'])
@requires_auth
def api_write_watering_profile(sensor_id):
    """デバイスに水やりプロファイルを書き込むためのコマンドを送信します。"""

    logger.info(f"Received request to write watering profile for sensor_id: {sensor_id}")

    data = request.json
    conn = dm.get_db_connection()
    # sensor_idは、このアプリケーションではdevice_idと同じものとして扱います
    device = conn.execute('SELECT device_id FROM devices WHERE device_id = ?', (sensor_id,)).fetchone()
    conn.close()

    if not device:
        response_data = json.dumps({'success': False, 'message': '指定されたデバイスが見つかりません。'})
        return Response(response_data, status=404, mimetype='application/json')

    try:
        command = {
            "command": "set_watering_thresholds",
            "device_id": device['device_id'],
            "payload": {
                "dry_threshold": data.get('dry_threshold'),
                "wet_threshold": data.get('wet_threshold')
            }
        }
        # configからパイプのパスを読み込む
        with open(config.COMMAND_PIPE_PATH, "a") as f:
            f.write(json.dumps(command) + "\n")

        logger.info(f"デバイス {sensor_id} への水やり設定書き込みコマンドをキューに追加しました。")
        response_data = json.dumps({'success': True, 'message': 'デバイスへの書き込みコマンドを受け付けました。'})
        return Response(response_data, status=200, mimetype='application/json')

    except Exception as e:
        logger.error(f"コマンドのデーモンへの送信に失敗: {e}", exc_info=True)
        response_data = json.dumps({'success': False, 'message': f'サーバー内部でエラーが発生しました: {e}'})
        return Response(response_data, status=500, mimetype='application/json')


async def control_led_ble(mac_address, red, green, blue, brightness, duration_ms):
    """
    BLE経由でWS2812 LEDを制御する非同期関数
    CMD_CONTROL_LED (0x18) - 6バイト: R, G, B, brightness(0-100), duration_ms(uint16)
    """
    import struct

    COMMAND_UUID = "6A3B2C1D-4E5F-6A7B-8C9D-E0F123456791"
    RESPONSE_UUID = "6A3B2C1D-4E5F-6A7B-8C9D-E0F123456792"
    CMD_CONTROL_LED = 0x18

    response_data = {}

    def notification_handler(sender, data):
        if len(data) >= 5:
            response_data[data[0]] = data

    logger.info(f"Connecting to {mac_address} to control LED...")

    async with BleakClient(mac_address) as client:
        await client.start_notify(RESPONSE_UUID, notification_handler)

        try:
            led_data = struct.pack("<BBBBH",
                                   int(red), int(green), int(blue),
                                   int(brightness), int(duration_ms))
            packet = struct.pack("<BBH", CMD_CONTROL_LED, 1, len(led_data)) + led_data
            await client.write_gatt_char(COMMAND_UUID, packet, response=False)

            for _ in range(50):  # 5秒タイムアウト
                if CMD_CONTROL_LED in response_data:
                    break
                await asyncio.sleep(0.1)

            if CMD_CONTROL_LED not in response_data:
                raise Exception("Response timeout for CMD_CONTROL_LED")

            raw = response_data[CMD_CONTROL_LED]
            if raw[1] != 0x00:
                raise Exception(f"CMD_CONTROL_LED failed with status 0x{raw[1]:02X}")

        finally:
            await client.stop_notify(RESPONSE_UUID)

    return True


@devices_bp.route('/api/control-led', methods=['POST'])
@requires_auth
def api_control_led():
    """BLE経由でデバイスのLEDを制御します。"""
    logger.info("Received request to control LED")

    data = request.json
    device_id = data.get('device_id')
    red = data.get('red')
    green = data.get('green')
    blue = data.get('blue')
    brightness = data.get('brightness')
    duration_ms = data.get('duration_ms')

    if not all([device_id, red is not None, green is not None, blue is not None, brightness is not None, duration_ms is not None]):
        return jsonify({'success': False, 'message': 'Missing LED control parameters.'}), 400

    conn = dm.get_db_connection()
    device = conn.execute('SELECT * FROM devices WHERE device_id = ?', (device_id,)).fetchone()
    conn.close()

    if not device:
        return jsonify({'success': False, 'message': 'Device not found.'}), 404

    try:
        asyncio.run(control_led_ble(device['mac_address'], red, green, blue, brightness, duration_ms))
        return jsonify({'success': True, 'message': 'LED control command sent successfully.'})
    except Exception as e:
        logger.error(f"Failed to control LED: {e}", exc_info=True)
        return jsonify({'success': False, 'message': f'Communication error: {str(e)}'}), 500


@devices_bp.route('/api/device/<device_id>', methods=['DELETE'])
@requires_auth
def api_delete_device(device_id):
    """デバイスを削除します。"""
    try:
        conn = dm.get_db_connection()

        # デバイスが存在するか確認
        device = conn.execute('SELECT * FROM devices WHERE device_id = ?', (device_id,)).fetchone()
        if not device:
            conn.close()
            return jsonify({'success': False, 'message': 'デバイスが見つかりません。'}), 404

        # managed_plantsテーブルでこのデバイスを参照しているレコードをNULLに更新
        conn.execute('''
            UPDATE managed_plants
            SET assigned_plant_sensor_id = NULL
            WHERE assigned_plant_sensor_id = ?
        ''', (device_id,))

        conn.execute('''
            UPDATE managed_plants
            SET assigned_switchbot_id = NULL
            WHERE assigned_switchbot_id = ?
        ''', (device_id,))

        # センサーデータを削除
        conn.execute('DELETE FROM sensor_data WHERE device_id = ?', (device_id,))

        # デバイスを削除
        conn.execute('DELETE FROM devices WHERE device_id = ?', (device_id,))

        conn.commit()
        conn.close()

        # メモリ上のデバイスリストを再読み込み
        dm.load_devices_from_db()

        logger.info(f"デバイス {device_id} を削除しました。")
        return jsonify({'success': True, 'message': 'デバイスを削除しました。'})

    except Exception as e:
        logger.error(f"デバイスの削除に失敗しました: {e}", exc_info=True)
        return jsonify({'success': False, 'message': f'デバイスの削除に失敗しました: {e}'}), 500
