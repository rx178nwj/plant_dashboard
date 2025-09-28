#!/bin/bash

# プロジェクトルートに移動
cd "$(dirname "$0")/.."

echo "--- copy services ---"
sudo cp system_env/plant_dashboard.service /etc/systemd/system
sudo cp system_env/plant_dashboard-daemon.service /etc/systemd/system
sudo cp system_env/plant_analyzer_daemon.service /etc/systemd/system

echo "--- Enabling and starting systemd services ---"

# 既存のデーモンを停止
sudo systemctl stop plant_dashboard-daemon.service
sudo systemctl stop plant_dashboard.service
 
# systemdに設定の変更を通知
sudo systemctl daemon-reload

# Bluetoothデーモンを起動・有効化
sudo systemctl start plant_dashboard-daemon.service
sudo systemctl enable plant_dashboard-daemon.service

# 新しい分析デーモンを起動・有効化
sudo systemctl start plant_analyzer_daemon.service
sudo systemctl enable plant_analyzer_daemon.service

# 両方のサービスの稼働状態を確認
echo "--- Bluetooth Daemon Status ---"
sudo systemctl status plant_dashboard-daemon.service
echo "--- Analyzer Daemon Status ---"
sudo systemctl status plant_analyzer_daemon.service

# Web Appサービス
echo "Starting Plant Dashboard Web App..."
sudo systemctl enable plant_dashboard.service
sudo systemctl start plant_dashboard.service
