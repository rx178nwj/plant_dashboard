# plant_dashboard/device_manager.py

import sqlite3
import logging
from datetime import datetime
from datetime import datetime, timezone, timedelta
from database import get_db_connection

logger = logging.getLogger(__name__)

# --- ▼▼▼ ADD Timezone Definition ▼▼▼ ---
# 日本標準時(JST)のタイムゾーンを定義
JST = timezone(timedelta(hours=+9), 'JST')
# --- ▲▲▲ ADD Timezone Definition ▲▲▲ ---

# このインメモリキャッシュは、デーモンが動いていない開発時などに
# 直接は使われませんが、関連機能のために構造は残します。
device_states = {}

def load_devices_from_db():
    """データベースからデバイス情報を読み込み、インメモリの状態を初期化する"""
    conn = get_db_connection()
    devices = conn.execute('SELECT * FROM devices').fetchall()
    conn.close()
    device_states.clear()
    for device in devices:
        device_id = device['device_id']
        device_states[device_id] = {
            'device_id': device_id,
            'device_name': device['device_name'],
            'mac_address': device['mac_address'],
            'device_type': device['device_type'],
            'connection_status': 'initializing',
            'last_seen': device['last_seen'],
            'battery_level': device['battery_level'],
            'last_data': {},
            'button_pressed': False
        }
    logger.info(f"Loaded {len(device_states)} devices from database.")
    return device_states

def get_all_devices():
    """（現在メインでは未使用）インメモリのデバイス状態を返す"""
    return list(device_states.values())

def get_device_by_id(device_id):
    return device_states.get(device_id)

def update_device_status(device_id, status, battery=None):
    """（デーモン用）デバイスの接続状態をDBに書き込む"""
    if device_id in device_states:
        device_states[device_id]['connection_status'] = status
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        device_states[device_id]['last_seen'] = now
        conn = get_db_connection()
        cursor = conn.cursor()
        if battery is not None:
            device_states[device_id]['battery_level'] = battery
            cursor.execute('UPDATE devices SET connection_status = ?, last_seen = ?, battery_level = ? WHERE device_id = ?', (status, now, battery, device_id))
        else:
            cursor.execute('UPDATE devices SET connection_status = ?, last_seen = ? WHERE device_id = ?', (status, now, device_id))
        conn.commit()
        conn.close()

def save_sensor_data(device_id, timestamp, data, data_version=1):
    """
    センサーデータをDBに保存します。
    data_versionに応じてv1/v2/v3デバイスのデータに対応。

    Args:
        device_id: デバイスID
        timestamp: タイムスタンプ (ISO形式文字列)
        data: センサーデータ辞書
        data_version: データバージョン (1=Rev1/Rev2, 2=Rev3, 3=Rev4)
    """
    if not data:
        return

    logging.info(f"Saving sensor data for device {device_id} with data_version {data_version}")

    conn = get_db_connection()
    formatted_timestamp = ""

    if timestamp:
        # ISO形式の文字列をdatetimeオブジェクトにパースし、指定の形式に再フォーマット
        try:
            dt_object = datetime.fromisoformat(timestamp)
            formatted_timestamp = dt_object.strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            # 既に正しい形式の場合や、他の形式で来た場合のエラーハンドリング
            formatted_timestamp = timestamp
    else:
        # タイムスタンプが提供されていなければ、現在時刻を生成
        formatted_timestamp = datetime.now(JST).strftime("%Y-%m-%d %H:%M:%S")

    try:

        # v3デバイスのカラム (Rev4: v2 + ex_temperature)
        if data_version == 3:
            columns = "(device_id, timestamp, temperature, humidity, light_lux, soil_moisture, data_version, soil_temperature1, soil_temperature2, soil_temperature3, soil_temperature4, ex_temperature, capacitance_ch1, capacitance_ch2, capacitance_ch3, capacitance_ch4)"
            values = "?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?"
            row_data = (
                device_id,
                formatted_timestamp,
                data.get('temperature'),
                data.get('humidity'),
                data.get('light_lux'),
                data.get('soil_moisture'),
                data_version,
                data.get('soil_temperature1'),
                data.get('soil_temperature2'),
                data.get('soil_temperature3'),
                data.get('soil_temperature4'),
                data.get('ex_temperature'),
                data.get('capacitance_ch1'),
                data.get('capacitance_ch2'),
                data.get('capacitance_ch3'),
                data.get('capacitance_ch4')
            )

            conn.execute(
                f"INSERT INTO sensor_data {columns} VALUES ({values})",
                row_data
            )
            logger.info(f"Saved v3 sensor data for {device_id} at {formatted_timestamp}")

        # v2デバイスのカラム (Rev3: soil_temperature1-4 + capacitance)
        elif data_version == 2:
            extended_columns = "(device_id, timestamp, temperature, humidity, light_lux, soil_moisture, data_version, soil_temperature1, soil_temperature2, soil_temperature3, soil_temperature4, capacitance_ch1, capacitance_ch2, capacitance_ch3, capacitance_ch4)"
            extended_values = "?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?"
            extended_data = (
                device_id,
                formatted_timestamp,
                data.get('temperature'),
                data.get('humidity'),
                data.get('light_lux'),
                data.get('soil_moisture'),
                data_version,
                data.get('soil_temperature1'),
                data.get('soil_temperature2'),
                data.get('soil_temperature3'),
                data.get('soil_temperature4'),
                data.get('capacitance_ch1'),
                data.get('capacitance_ch2'),
                data.get('capacitance_ch3'),
                data.get('capacitance_ch4')
            )

            conn.execute(
                f"INSERT INTO sensor_data {extended_columns} VALUES ({extended_values})",
                extended_data
            )
            logger.info(f"Saved v2 sensor data for {device_id} at {formatted_timestamp}")
        else:
            # v1デバイスのカラム
            base_columns = "(device_id, timestamp, temperature, humidity, light_lux, soil_moisture, data_version)"
            base_values = "?, ?, ?, ?, ?, ?, ?"
            base_data = (
                device_id,
                formatted_timestamp,
                data.get('temperature'),
                data.get('humidity'),
                data.get('light_lux'),
                data.get('soil_moisture'),
                data_version
            )

            # v1デバイス
            conn.execute(
                f"INSERT INTO sensor_data {base_columns} VALUES ({base_values})",
                base_data
            )
            logger.info(f"Saved v1 sensor data for {device_id} at {formatted_timestamp}")

        conn.commit()
    except sqlite3.Error as e:
        logger.error(f"Failed to save sensor data for {device_id}: {e}")
    finally:
        if conn:
            conn.close()

def log_system_event(message, level='INFO', device_id=None):
    try:
        conn = get_db_connection()
        conn.execute('INSERT INTO system_logs (device_id, log_level, message) VALUES (?, ?, ?)', (device_id, level, message))
        conn.commit()
        conn.close()
    except sqlite3.Error as e:
        logger.error(f"Failed to write to system_logs: {e}")

def get_devices_with_latest_sensor_data():
    """
    すべてのデバイス情報と、それぞれに対応する最新のセンサーデータをDBから直接取得する
    """
    conn = get_db_connection()
    devices = conn.execute('SELECT * FROM devices ORDER BY device_name').fetchall()
    
    devices_with_data = []
    for device in devices:
        device_dict = dict(device)
        
        latest_data = conn.execute(
            """
            SELECT * FROM sensor_data
            WHERE device_id = ?
            ORDER BY timestamp DESC
            LIMIT 1
            """, (device['device_id'],)
        ).fetchone()
        
        device_dict['last_data'] = dict(latest_data) if latest_data else {}
        devices_with_data.append(device_dict)
            
    conn.close()
    return devices_with_data

def get_devices_latest_on_date(date_str):
    """指定された日付における、各デバイスの最後の状態を取得する"""
    conn = get_db_connection()
    devices = conn.execute('SELECT * FROM devices').fetchall()
    
    end_of_day = f"{date_str} 23:59:59"
    
    device_data = []
    for device in devices:
        device_id = device['device_id']
        
        last_reading = conn.execute(
            """
            SELECT * FROM sensor_data 
            WHERE device_id = ? AND timestamp <= ? 
            ORDER BY timestamp DESC 
            LIMIT 1
            """, (device_id, end_of_day)
        ).fetchone()

        data = {
            'device_id': device['device_id'],
            'device_name': device['device_name'],
            'mac_address': device['mac_address'],
            'device_type': device['device_type'],
            'connection_status': 'historical' if last_reading else 'no_data',
            'battery_level': device['battery_level'],
            'last_data': dict(last_reading) if last_reading else {}
        }
        device_data.append(data)
        
    conn.close()
    return device_data
