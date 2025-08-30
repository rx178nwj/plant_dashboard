# plant_dashboard/app.py

import asyncio, logging, threading, time
from queue import Queue
from flask import Flask, request
import config
from database import init_db
from device_manager import load_devices_from_db
from ble_manager import PlantDeviceBLE, get_switchbot_adv_data
import device_manager as dm

# blueprintsから各ルートをインポート
from blueprints.dashboard.routes import dashboard_bp, sse_queue
from blueprints.devices.routes import devices_bp
from blueprints.plants.routes import plants_bp
from blueprints.management.routes import management_bp

logger = logging.getLogger(__name__)

def create_app():
    """Application Factory: Creates and infigures the Flask app."""
    app = Flask(__name__)
    app.config.from_object(config)

    # Blueprintを登録
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(devices_bp)
    app.register_blueprint(plants_bp)
    app.register_blueprint(management_bp)

    # ▼▼▼ context_processorをアプリ全体に登録 ▼▼▼
    @app.context_processor
    def inject_nav():
        """ナビゲーションバーの項目を全てのテンプレートに渡す"""
        return dict(nav_items=[
            {'url': 'dashboard.dashboard', 'icon': 'bi-grid-fill', 'text': 'Dashboard'},
            {'url': 'management.management', 'icon': 'bi-sliders', 'text': 'Management'},
            {'url': 'devices.devices', 'icon': 'bi-hdd-stack-fill', 'text': 'Devices'},
            {'url': 'plants.plants', 'icon': 'bi-book-half', 'text': 'Plant Library'}
        ])

    @app.cli.command('init-db')
    def init_db_command():
        init_db()

    return app

async def data_collection_loop():
    """バックグラウンドでデバイスデータを収集する非同期ループ"""
    logger.info("Starting data collection loop...")
    plant_sensor_connections = {}
    while True:
        devices_in_db = load_devices_from_db()
        if not devices_in_db:
            await asyncio.sleep(config.DATA_FETCH_INTERVAL)
            continue
        
        for dev_id, device_details in devices_in_db.items():
            device_type = device_details.get('device_type')
            mac_address = device_details.get('mac_address')
            sensor_data = None
            try:
                if device_type == 'plant_sensor':
                    if dev_id not in plant_sensor_connections:
                        plant_sensor_connections[dev_id] = PlantDeviceBLE(mac_address, dev_id)
                    ble_device = plant_sensor_connections[dev_id]
                    if await ble_device.ensure_connection():
                        sensor_data = await ble_device.get_sensor_data()
                elif device_type.startswith('switchbot_'):
                    sensor_data = await get_switchbot_adv_data(mac_address)
                
                if sensor_data:
                    dm.save_sensor_data(dev_id, sensor_data)
                    dm.update_device_status(dev_id, 'connected', sensor_data.get('battery_level'))
                else:
                    dm.update_device_status(dev_id, 'disconnected')
            except Exception as e:
                logger.error(f"Unhandled error in data collection for {dev_id}: {e}")
                dm.update_device_status(dev_id, 'error')
            
        # SSEキューに最新のデバイス状態をまとめて送信
        sse_queue.put(dm.get_all_devices())
        await asyncio.sleep(config.DATA_FETCH_INTERVAL)

def run_async_loop():
    asyncio.run(data_collection_loop())

if __name__ == '__main__':
    # 直接実行された場合のみ、ロギング設定とサーバー起動を行う
    logging.basicConfig(level=config.LOG_LEVEL, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', handlers=[logging.FileHandler(config.LOG_FILE_PATH), logging.StreamHandler()])
    app = create_app()
    init_db()
    bg_thread = threading.Thread(target=run_async_loop, daemon=True)
    bg_thread.start()
    app.run(host='0.0.0.0', port=8000, debug=False)
