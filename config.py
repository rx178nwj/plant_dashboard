# plant_dashboard/config.py

import os

# プロジェクトのベースディレクトリ
BASE_DIR = os.path.abspath(os.path.dirname(__file__))

# --- Gemini APIキー ---
# 環境変数 'GEMINI_API_KEY' から読み込む (wsgi.pyでロード済み)
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')

# --- 画像アップロード設定 ---
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'static', 'uploads', 'plant_images')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

# データベース設定
DATABASE_PATH = os.path.join(BASE_DIR, 'data', 'plant_monitor.db')

# ログ設定
LOG_FILE_PATH = os.path.join(BASE_DIR, 'logs', 'app.log')
LOG_LEVEL = 'INFO'

# Webアプリケーション設定
SECRET_KEY = os.environ.get('SECRET_KEY', 'a-very-secret-key-for-dev')
DEBUG = False

# Basic認証設定
BASIC_AUTH_USERNAME = 'admin'
BASIC_AUTH_PASSWORD = 'plant'
BASIC_AUTH_FORCE = True

# BLE設定
TARGET_SERVICE_UUID = "59462f12-9543-9999-12c8-58b459a2712d"
DATA_FETCH_INTERVAL = 60
RECONNECT_ATTEMPTS = 5
RECONNECT_DELAY_BASE = 2

