# plant_dashboard/switchbot_daemon.py

import asyncio
import logging
import time
from datetime import datetime

# プロジェクト内の既存モジュールをインポート
import config
from database import get_db_connection
from ble_manager import get_switchbot_adv_data

# このデーモン専用のロギング設定
logging.basicConfig(
    level=config.LOG_LEVEL,
    format='%(asctime)s - [SwitchBotDaemon] - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(config.LOG_FILE_PATH), # Webアプリと同じログファイルに出力
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def get_switchbot_devices_from_db():
    """データベースから登録済みのSwitchBotデバイス一覧を取得する"""
    conn = get_db_connection()
    # device_typeが 'switchbot_' で始まるものをすべて取得
    switchbots = conn.execute(
        "SELECT device_id, mac_address FROM devices WHERE device_type LIKE 'switchbot_%'"
    ).fetchall()
    conn.close()
    return switchbots

def save_data(device_id, data):
    """取得したセンサーデータをデータベースに保存・更新する"""
    if not data:
        return

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = get_db_connection()
    cursor = conn.cursor()

    # 1. sensor_dataテーブルに新しい記録を挿入
    cursor.execute(
        "INSERT INTO sensor_data (device_id, temperature, humidity) VALUES (?, ?, ?)",
        (device_id, data.get('temperature'), data.get('humidity'))
    )
    
    # 2. devicesテーブルの最終確認日時とバッテリーレベルを更新
    cursor.execute(
        "UPDATE devices SET last_seen = ?, battery_level = ? WHERE device_id = ?",
        (now, data.get('battery_level'), device_id)
    )
    
    conn.commit()
    conn.close()
    logger.info(f"Successfully saved data for {device_id}: Temp={data.get('temperature')}°C, Humid={data.get('humidity')}%")

async def main_task():
    """メインの非同期タスク"""
    logger.info("Fetching data for all registered SwitchBot devices...")
    devices = get_switchbot_devices_from_db()

    if not devices:
        logger.info("No SwitchBot devices registered in the database. Skipping cycle.")
        return

    # 登録されている全SwitchBotデバイスのデータを並行して取得
    tasks = [get_switchbot_adv_data(dev['mac_address']) for dev in devices]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    for device, result in zip(devices, results):
        if isinstance(result, Exception):
            logger.error(f"Failed to get data for {device['device_id']} ({device['mac_address']}): {result}")
        elif result is None:
            logger.warning(f"No data received for {device['device_id']} ({device['mac_address']})")
        else:
            save_data(device['device_id'], result)

def main_loop():
    """60秒ごとにメインタスクを実行する無限ループ"""
    logger.info("SwitchBot data collection daemon started.")
    while True:
        try:
            asyncio.run(main_task())
        except Exception as e:
            logger.critical(f"An unhandled error occurred in the main loop: {e}")
        
        logger.info(f"Cycle finished. Waiting for {config.DATA_FETCH_INTERVAL} seconds.")
        time.sleep(config.DATA_FETCH_INTERVAL)

if __name__ == "__main__":
    main_loop()
