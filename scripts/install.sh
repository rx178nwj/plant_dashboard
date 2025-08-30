#!/bin/bash

# スクリプトが失敗したら即座に終了
set -e

echo "--- Updating package list ---"
sudo apt-get update

echo "--- Installing system dependencies for Python and Bleak ---"
# python3-pip: pipをインストール
# python3-venv: 仮想環境を作成するために推奨
# libglib2.0-dev: Bleakが内部で使用するBlueZライブラリの依存関係
sudo apt-get install -y python3-pip python3-venv libglib2.0-dev

# プロジェクトルートに移動 (スクリプトがどこから実行されても良いように)
cd "$(dirname "$0")/.."

echo "--- Creating Python virtual environment ---"
python3 -m venv .venv
# 仮想環境をアクティベート
source .venv/bin/activate

echo "--- Installing Python packages from requirements.txt ---"
pip install -r requirements.txt

echo "--- Installation complete! ---"
echo "To activate the virtual environment, run: source .venv/bin/activate"
echo "To initialize the database, run: flask init-db"
echo "To start the application, run: ./scripts/start.sh"