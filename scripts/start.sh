#!/bin/bash

# プロジェクトルートに移動
cd "$(dirname "$0")/.."

echo "--- Enabling and starting systemd services ---"

# Web Appサービス
echo "Starting Plant Dashboard Web App..."
sudo systemctl enable plant_dashboard.service
sudo systemctl start plant_dashboard.service

# BLE Daemonサービス
echo "Starting Plant Dashboard BLE Daemon..."
sudo systemctl enable plant_dashboard-daemon.service
sudo systemctl start plant_dashboard-daemon.service

echo ""
echo "--- Services started. ---"
echo "You can check the status with:"
echo "sudo systemctl status plant_dashboard.service"
echo "sudo systemctl status plant_dashboard-daemon.service"
echo ""
echo "You can view the logs with:"
echo "sudo journalctl -u plant_dashboard.service -f"
echo "sudo journalctl -u plant_dashboard-daemon.service -f"