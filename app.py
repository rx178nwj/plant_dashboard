# plant_dashboard/app.py

import logging
import os
from flask import Flask, current_app

# configモジュールをインポート
import config

from database import init_db
# device_managerはブループリントから利用されるためimportを維持
import device_manager as dm

# blueprintsから各ルートをインポート
from blueprints.dashboard.routes import dashboard_bp
from blueprints.devices.routes import devices_bp
from blueprints.plants.routes import plants_bp
from blueprints.management.routes import management_bp

logger = logging.getLogger(__name__)

def create_app():
    """Application Factory: Creates and configures the Flask app."""
    app = Flask(__name__)
    
    # config.pyから設定を読み込む
    app.config.from_object(config)

    # アプリケーションコンテキスト内でDB初期化とアップロードフォルダ作成
    # このブロックはアプリケーション起動時に一度だけ実行される
    with app.app_context():
        # データベースの初期化とスキーママイグレーションを自動実行
        init_db()
        
        upload_folder = current_app.config.get('UPLOAD_FOLDER')
        if upload_folder:
            os.makedirs(upload_folder, exist_ok=True)
            logger.info(f"Upload folder '{upload_folder}' is ready.")
        else:
            logger.error("UPLOAD_FOLDER is not configured in config.py")

    # Blueprintを登録
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(devices_bp)
    app.register_blueprint(plants_bp)
    app.register_blueprint(management_bp)

    @app.context_processor
    def inject_nav():
        return dict(nav_items=[
            {'url': 'dashboard.dashboard', 'icon': 'bi-grid-fill', 'text': 'Dashboard'},
            {'url': 'management.management', 'icon': 'bi-sliders', 'text': 'Management'},
            {'url': 'management.watering_profiles', 'icon': 'bi-droplet-half', 'text': 'Watering Profiles'},
            {'url': 'devices.devices', 'icon': 'bi-hdd-stack-fill', 'text': 'Devices'},
            {'url': 'devices.devices_profiles', 'icon': 'bi-sliders', 'text': 'Device Profiles'},
            {'url': 'plants.plants', 'icon': 'bi-book-half', 'text': 'Plant Library'}
        ])

    @app.cli.command('init-db')
    def init_db_command():
        init_db()

    return app

if __name__ == '__main__':
    logging.basicConfig(level=config.LOG_LEVEL, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', handlers=[logging.FileHandler(config.LOG_FILE_PATH), logging.StreamHandler()])
    app = create_app()
    app.run(host='0.0.0.0', port=8000, debug=False)

