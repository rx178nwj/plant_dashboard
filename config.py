# plant_dashboard/config.py

import logging
import os

# --- 全般設定 ---
# プロジェクトのベースディレクトリ
BASE_DIR = os.path.abspath(os.path.dirname(__file__))

# --- Gemini APIキー ---
# 環境変数 'GEMINI_API_KEY' から読み込む
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')

# --- ログ設定 ---
LOG_LEVEL = logging.INFO # loggingモジュールの定数を使用
LOG_FILE_PATH = os.path.join(BASE_DIR, 'logs', 'plant_dashboard.log')
# ログディレクトリがなければ作成
os.makedirs(os.path.join(BASE_DIR, 'logs'), exist_ok=True)

# --- データベース設定 ---
DATABASE_PATH = os.path.join(BASE_DIR, 'data', 'plant_monitor.db')

# --- Webアプリケーション設定 ---
SECRET_KEY = os.environ.get('SECRET_KEY', 'a-very-secret-key-for-dev')
DEBUG = False

# Basic認証設定
BASIC_AUTH_USERNAME = 'admin'
BASIC_AUTH_PASSWORD = 'plant'
BASIC_AUTH_FORCE = True # アプリ全体でBasic認証を有効にする

# 画像アップロード設定
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'static', 'uploads', 'plant_images')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB

# --- BLE設定 ---
# 注意: このUUIDはカスタムプラントセンサーに合わせてください
TARGET_SERVICE_UUID = "6a3b2c1d-4e5f-6a7b-8c9d-e0f123456789"
RECONNECT_ATTEMPTS = 5
RECONNECT_DELAY_BASE = 2.0  # 秒単位、指数関数的に増加 (2, 4, 8...)

# --- デーモン設定 ---
# データ取得間隔（秒）。バッテリー消費を考慮し、5分(300秒)を推奨
DATA_FETCH_INTERVAL = 60
# 植物の状態分析デーモンの実行間隔（秒）
PLANT_ANALYZER_INTERVAL = 3600 # 1時間
# Webアプリからデーモンへのコマンド連携用パイプ
COMMAND_PIPE_PATH = "/tmp/plant_dashboard_cmd_pipe.jsonl"

