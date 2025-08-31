# plant_dashboard/bluetooth_daemon.py
import asyncio
import logging
import json
from datetime import datetime
import os

import config
import device_manager as dm
from ble_manager import PlantDeviceBLE, get_switchbot_adv_data
from database import get_db_connection

# データ連携用の一時ファイルパス
DATA_PIPE_PATH = "/tmp/plant_dashboard_pipe.jsonl"

logging.basicConfig(
    level=config.LOG_LEVEL,
    format='%(asctime)s - [BluetoothDaemon] - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(config.LOG_FILE_PATH),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def get_devices_from_db():
    """DBからポーリング対象のデバイス情報を取得する"""
    conn = get_db_connection()
    devices = conn.execute('SELECT device_id, device_name, mac_address, device_type FROM devices').fetchall()
    conn.close()
    return [dict(row) for row in devices]

def write_to_pipe(data):
    """取得したデータを一時ファイルにJSON Lines形式で追記する"""
    try:
        with open(DATA_PIPE_PATH, "a") as f:
            f.write(json.dumps(data) + "\n")
    except Exception as e:
        logger.error(f"Failed to write to data pipe: {e}")

async def main_loop():
    """Bluetoothデバイスのポーリングに専念するメインループ"""
    logger.info("Starting Bluetooth daemon loop...")
    plant_sensor_connections = {}

    while True:
        devices_to_poll = get_devices_from_db()
        
        if not devices_to_poll:
            logger.info("No devices configured in the database. Waiting...")
            await asyncio.sleep(config.DATA_FETCH_INTERVAL)
            continue
        
        logger.info(f"Starting data collection cycle for {len(devices_to_poll)} devices.")
        
        for device in devices_to_poll:
            dev_id = device.get('device_id')
            device_type = device.get('device_type')
            mac_address = device.get('mac_address')
            sensor_data = None
            
            logger.info(f"Polling device: {device.get('device_name')} ({dev_id})")

            try:
                if device_type == 'plant_sensor':
                    if dev_id not in plant_sensor_connections:
                        plant_sensor_connections[dev_id] = PlantDeviceBLE(mac_address, dev_id)
                    ble_device = plant_sensor_connections[dev_id]
                    sensor_data = await ble_device.get_sensor_data()
                        
                elif device_type and device_type.startswith('switchbot_'):
                    sensor_data = await get_switchbot_adv_data(mac_address)
                
                # 取得結果をpipeファイルに書き出す
                pipe_data = {
                    "device_id": dev_id,
                    "timestamp": datetime.now().isoformat(),
                    "data": sensor_data # データがなくてもNoneとして記録
                }
                write_to_pipe(pipe_data)

            except Exception as e:
                logger.error(f"Unhandled error during data collection for {dev_id}: {e}", exc_info=True)
                # エラー情報もpipeに書き出す
                write_to_pipe({
                    "device_id": dev_id,
                    "timestamp": datetime.now().isoformat(),
                    "error": str(e)
                })
            
            await asyncio.sleep(2) # デバイス間のポーリングに短い遅延

        logger.info(f"Data collection cycle finished. Waiting for {config.DATA_FETCH_INTERVAL} seconds.")
        await asyncio.sleep(config.DATA_FETCH_INTERVAL)

if __name__ == "__main__":
    try:
        # 起動時に一時ファイルが残っていれば削除
        if os.path.exists(DATA_PIPE_PATH):
            os.remove(DATA_PIPE_PATH)
        asyncio.run(main_loop())
    except KeyboardInterrupt:
        logger.info("Bluetooth daemon stopped by user.")
    except Exception as e:
        logger.critical(f"Bluetooth daemon stopped due to a critical error: {e}", exc_info=True)