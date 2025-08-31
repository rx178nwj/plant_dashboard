# plant_dashboard/bluetooth_daemon.py

import asyncio
import logging
import time

# プロジェクトのモジュールをインポート
import config
import device_manager as dm
from ble_manager import PlantDeviceBLE, get_switchbot_adv_data
from database import init_db

# ロギング設定
logging.basicConfig(
    level=config.LOG_LEVEL,
    format='%(asctime)s - [BLE_Daemon] - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(config.LOG_FILE_PATH),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

async def main_loop():
    """
    バックグラウンドでデバイスデータを収集する統合Bluetoothデーモンループ。
    データベースへのデータ保存に専念する。
    """
    logger.info("Starting Bluetooth daemon loop...")
    plant_sensor_connections = {}
    
    # 起動時にDBを初期化
    init_db()

    while True:
        devices_to_poll = dm.load_devices_from_db()
        
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
                    
                    if await ble_device.ensure_connection():
                        sensor_data = await ble_device.get_sensor_data()
                        
                elif device_type and device_type.startswith('switchbot_'):
                    sensor_data = await get_switchbot_adv_data(mac_address)
                
                if sensor_data:
                    dm.save_sensor_data(dev_id, sensor_data)
                    dm.update_device_status(dev_id, 'connected', sensor_data.get('battery_level'))
                else:
                    dm.update_device_status(dev_id, 'disconnected')

            except Exception as e:
                logger.error(f"Unhandled error during data collection for {dev_id}: {e}", exc_info=True)
                dm.update_device_status(dev_id, 'error')
            
            # デバイス間のポーリングに短い遅延を入れる
            await asyncio.sleep(2)

        logger.info(f"Data collection cycle finished. Waiting for {config.DATA_FETCH_INTERVAL} seconds.")
        await asyncio.sleep(config.DATA_FETCH_INTERVAL)

if __name__ == "__main__":
    try:
        asyncio.run(main_loop())
    except KeyboardInterrupt:
        logger.info("Bluetooth daemon stopped by user.")
    except Exception as e:
        logger.critical(f"Bluetooth daemon stopped due to a critical error: {e}", exc_info=True)
