#!/bin/bash

# プロジェクトルートに移動
cd "$(dirname "$0")/.."

echo "--- Stopping and disabling systemd services ---"

# Web Appサービス
echo "Stopping Plant Dashboard Web App..."
sudo systemctl stop plant_dashboard.service
sudo systemctl disable plant_dashboard.service

# BLE Daemonサービス
echo "Stopping Plant Dashboard BLE Daemon..."
sudo systemctl stop plant_dashboard-daemon.service
sudo systemctl disable plant_dashboard-daemon.service

echo "--- Services stopped. ---"
