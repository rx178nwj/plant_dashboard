# plant_dashboard/config.py

import os

# プロジェクトのベースディレクトリ
BASE_DIR = os.path.abspath(os.path.dirname(__file__))

# --- ▼▼▼ Gemini APIキーを追加 ▼▼▼ ---
# 環境変数 'GEMINI_API_KEY' から読み込むか、'YOUR_API_KEY_HERE' に直接キーを貼り付けてください
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY', 'AIzaSyBiTQezjbWRJKmKuu-AokZSU3DAkGgNaok')

# データベース設定
DATABASE_PATH = os.path.join(BASE_DIR, 'data', 'plant_monitor.db')

# ログ設定
LOG_FILE_PATH = os.path.join(BASE_DIR, 'logs', 'app.log')
LOG_LEVEL = 'INFO' # DEBUG, INFO, WARNING, ERROR, CRITICAL

# Webアプリケーション設定
SECRET_KEY = os.environ.get('SECRET_KEY', 'a-very-secret-key-for-dev')
DEBUG = False

# Basic認証設定
BASIC_AUTH_USERNAME = 'admin'
BASIC_AUTH_PASSWORD = 'plant'
BASIC_AUTH_FORCE = True

# BLE設定
TARGET_SERVICE_UUID = "59462f12-9543-9999-12c8-58b459a2712d"
DATA_FETCH_INTERVAL = 600
RECONNECT_ATTEMPTS = 5
RECONNECT_DELAY_BASE = 2
