# plant_dashboard/device_manager.py

import sqlite3
import logging
from datetime import datetime
from database import get_db_connection

logger = logging.getLogger(__name__)

device_states = {}

def load_devices_from_db():
    # (この関数は変更なし)
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
    return list(device_states.values())

def get_device_by_id(device_id):
    return device_states.get(device_id)

def update_device_status(device_id, status, battery=None):
    # (この関数は変更なし)
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

def save_sensor_data(device_id, data):
    # (この関数は変更なし)
    if device_id in device_states and data:
        device_states[device_id]['last_data'] = data
        device_states[device_id]['button_pressed'] = data.get('button_pressed', False)
        conn = get_db_connection()
        conn.execute(
            "INSERT INTO sensor_data (device_id, temperature, humidity, light_lux, soil_moisture) VALUES (?, ?, ?, ?, ?)",
            (device_id, data.get('temperature'), data.get('humidity'), data.get('light_lux'), data.get('soil_moisture'))
        )
        conn.commit()
        conn.close()
        logger.info(f"Saved sensor data for {device_id}")

def log_system_event(message, level='INFO', device_id=None):
    # (この関数は変更なし)
    try:
        conn = get_db_connection()
        conn.execute('INSERT INTO system_logs (device_id, log_level, message) VALUES (?, ?, ?)', (device_id, level, message))
        conn.commit()
        conn.close()
    except sqlite3.Error as e:
        logger.error(f"Failed to write to system_logs: {e}")

def get_devices_latest_on_date(date_str):
    """指定された日付における、各デバイスの最後の状態を取得する"""
    conn = get_db_connection()
    devices = conn.execute('SELECT * FROM devices').fetchall()
    
    end_of_day = f"{date_str} 23:59:59"
    
    device_data = []
    for device in devices:
        device_id = device['device_id']
        
        # 選択された日の終わり以前の最後のセンサー記録を取得
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
            'battery_level': device['battery_level'], # DBに履歴がないため最新の値を表示
            'last_data': dict(last_reading) if last_reading else {}
        }
        device_data.append(data)
        
    conn.close()
    return device_data
