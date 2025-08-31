import asyncio
import sqlite3
import time
import logging
import struct
from datetime import datetime
from bleak import BleakClient, BleakError

# -----------------------------------------------------------------------------
# 設定
# -----------------------------------------------------------------------------
DATABASE_PATH = 'data/plant_monitor.db'
# 計測間隔（秒）。本番環境では900秒（15分）などを推奨します。
MEASUREMENT_INTERVAL_SECONDS = 300
LOG_FILE_PATH = 'logs/plant_monitor_daemon.log'
# BLE接続のリトライ設定
RECONNECT_ATTEMPTS = 3
RECONNECT_DELAY_BASE = 2.0  # seconds

# -----------------------------------------------------------------------------
# ロギング設定
# -----------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE_PATH),
        logging.StreamHandler()
    ]
)

# -----------------------------------------------------------------------------
# BLEデバイスの定数 (サンプルコードより参照)
# -----------------------------------------------------------------------------
PLANT_SERVICE_UUID = "59462f12-9543-9999-12c8-58b459a2712d"
COMMAND_CHAR_UUID = "6a3b2c1d-4e5f-6a7b-8c9d-e0f123456791"
RESPONSE_CHAR_UUID = "6a3b2c1d-4e5f-6a7b-8c9d-e0f123456792"
CMD_GET_SENSOR_DATA = 0x01

# グローバルなシーケンス番号
sequence_num = 0

# -----------------------------------------------------------------------------
# データベース関連の関数
# -----------------------------------------------------------------------------
def get_db_connection():
    """データベース接続を取得します。"""
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        conn.row_factory = sqlite3.Row
        return conn
    except sqlite3.Error as e:
        logging.error(f"Database connection error: {e}")
        return None

def load_devices_from_db():
    """データベースから'plant_sensor'タイプのデバイス情報を読み込みます。"""
    conn = get_db_connection()
    if not conn:
        return []
    try:
        devices = conn.execute(
            "SELECT device_id as id, device_name as name, mac_address, device_type FROM devices WHERE device_type = 'plant_sensor'"
        ).fetchall()
        conn.close()
        return [dict(row) for row in devices]
    except sqlite3.Error as e:
        logging.error(f"Failed to load devices from DB: {e}")
        if conn:
            conn.close()
        return []

def add_sensor_reading(device_id, temperature, humidity, light_lux, soil_moisture):
    """センサーデータをデータベースに保存します。"""
    conn = get_db_connection()
    if not conn:
        return
    try:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn.execute(
            'INSERT INTO sensor_data (device_id, temperature, humidity, light_lux, soil_moisture, timestamp) VALUES (?, ?, ?, ?, ?, ?)',
            (device_id, temperature, humidity, light_lux, soil_moisture, timestamp)
        )
        conn.commit()
        logging.info(f"Sensor data for device_id {device_id} has been successfully saved.")
    except sqlite3.Error as e:
        logging.error(f"Database error when adding sensor reading for device_id {device_id}: {e}")
    finally:
        if conn:
            conn.close()

# -----------------------------------------------------------------------------
# BLE通信関連の関数
# -----------------------------------------------------------------------------
async def get_sensor_data_from_device(mac_address: str, device_id: str):
    """
    カスタムプラントセンサーからデータを非同期に読み取ります。
    コマンドを書き込み、別のキャラクタリスティックからの通知でレスポンスを受け取る方式です。
    """
    global sequence_num
    try:
        async with BleakClient(mac_address, timeout=20.0) as client:
            if not client.is_connected:
                logging.error(f"[{device_id}] Failed to connect to device {mac_address}")
                return None
            
            logging.info(f"[{device_id}] Connected to {mac_address}")
            notification_received = asyncio.Event()
            received_data = None

            def notification_handler(sender: int, data: bytearray):
                nonlocal received_data
                logging.debug(f"[{device_id}] Notification received from handle {sender}: {data.hex()}")
                received_data = data
                notification_received.set()

            await client.start_notify(RESPONSE_CHAR_UUID, notification_handler)
            
            sequence_num = (sequence_num + 1) % 256
            command_packet = struct.pack('<BBH', CMD_GET_SENSOR_DATA, sequence_num, 0)
            
            logging.debug(f"[{device_id}] Writing command to {COMMAND_CHAR_UUID}: {command_packet.hex()}")
            await client.write_gatt_char(COMMAND_CHAR_UUID, command_packet)
            
            logging.debug(f"[{device_id}] Waiting for notification...")
            await asyncio.wait_for(notification_received.wait(), timeout=10.0)

            if received_data is None:
                logging.warning(f"[{device_id}] Notification event was set, but no data was received.")
                return None

            if len(received_data) < 5:
                logging.warning(f"[{device_id}] Response header is too short: {len(received_data)} bytes")
                return None
            
            resp_id, status_code, resp_seq, data_len = struct.unpack('<BBBH', received_data[:5])
            
            logging.debug(f"[{device_id}] Parsed header: ID={resp_id}, Status={status_code}, Seq={resp_seq}, Len={data_len}")

            if resp_seq != sequence_num:
                logging.warning(f"[{device_id}] Sequence number mismatch. Expected {sequence_num}, got {resp_seq}")

            payload = received_data[5:]
            if len(payload) != data_len:
                logging.error(f"[{device_id}] Payload length mismatch. Header says {data_len}, but got {len(payload)}")
                return None

            if data_len == 56:
                unpacked_data = struct.unpack('<9i4f?3x', payload)
                
                tm_sec, tm_min, tm_hour, tm_mday, tm_mon, tm_year, _, _, _, \
                lux, temp, humidity, soil, error = unpacked_data
                
                # Cのtm構造体からPythonのdatetimeオブジェクトへ変換
                dt = datetime(tm_year + 1900, tm_mon + 1, tm_mday, tm_hour, tm_min, tm_sec)
                
                return {
                    "temperature": temp,
                    "moisture": soil,
                    "light_lux": lux,
                    "humidity": humidity,
                    "sensor_error": error,
                    "datetime": dt
                }
            else:
                logging.error(f"[{device_id}] Unsupported data length in payload: {data_len}.")
                return None

    except asyncio.TimeoutError:
        logging.error(f"[{device_id}] Timed out waiting for connection or notification from {mac_address}.")
        return None
    except BleakError as e:
        logging.error(f"[{device_id}] BleakError with device {mac_address}: {e}")
        return None
    except struct.error as e:
        logging.error(f"[{device_id}] Failed to unpack response data: {e}. Payload was {payload.hex() if 'payload' in locals() else 'N/A'}")
        return None
    except Exception as e:
        logging.error(f"[{device_id}] An unexpected error occurred with device {mac_address}: {e}", exc_info=True)
        return None

# -----------------------------------------------------------------------------
# デーモン本体
# -----------------------------------------------------------------------------
async def measure_and_store_data():
    """デバイスからデータを測定し、データベースに保存するメインの処理。"""
    logging.info("Starting measurement cycle...")
    devices = load_devices_from_db()

    if not devices:
        logging.warning("No 'plant_sensor' devices found in the database. Please add devices with this type via the web interface.")
        return

    logging.info(f"Found {len(devices)} plant_sensor devices to monitor.")

    for device in devices:
        device_id = device['id']
        mac_address = device['mac_address']
        
        logging.info(f"Reading data from '{device['name']}' (plant_sensor at {mac_address})")
        
        sensor_data = await get_sensor_data_from_device(mac_address, device_id)

        if sensor_data:
            logging.info(f"Successfully retrieved data for device {device_id}: {sensor_data}")
            add_sensor_reading(
                device_id=device_id,
                temperature=sensor_data.get('temperature'),
                humidity=sensor_data.get('humidity'),
                light_lux=sensor_data.get('light_lux'),
                soil_moisture=sensor_data.get('moisture'),
            )
        else:
            logging.warning(f"Could not retrieve data for device {device_id} at {mac_address}")
        
        await asyncio.sleep(5)

    logging.info("Measurement cycle finished.")

async def main():
    """デーモンのメインループ。"""
    logging.info("Plant Monitor Daemon started.")
    logging.info(f"Data will be collected every {MEASUREMENT_INTERVAL_SECONDS} seconds.")
    
    while True:
        try:
            await measure_and_store_data()
        except Exception as e:
            logging.error(f"An error occurred in the main loop: {e}", exc_info=True)
        
        logging.info(f"Waiting for {MEASUREMENT_INTERVAL_SECONDS} seconds until the next cycle.")
        await asyncio.sleep(MEASUREMENT_INTERVAL_SECONDS)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("Daemon stopped by user.")
    except Exception as e:
        logging.critical(f"Daemon stopped due to a critical error: {e}", exc_info=True)

