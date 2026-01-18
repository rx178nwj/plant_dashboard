#!/usr/bin/env python3
"""
Test script for data_version pipeline integration
"""
import json
import os
import sys
sys.path.insert(0, '/home/pi/plant_dashboard')

from database import get_db_connection

# テスト用のパイプデータを作成
test_pipe_data = [
    # v1デバイス (PlantMonitor_20)
    {
        "device_id": "plant_sensor_efda06",
        "timestamp": "2026-01-04T16:00:00",
        "data_version": 1,
        "data": {
            "datetime": "2026-01-04 16:00:00",
            "light_lux": 1500.5,
            "temperature": 25.3,
            "humidity": 60.2,
            "soil_moisture": 2.5,
            "sensor_error": False,
            "battery_level": 85
        }
    },
    # v2デバイス (PlantMonitor_30)
    {
        "device_id": "plant_sensor_f2b9b2",
        "timestamp": "2026-01-04T16:00:00",
        "data_version": 2,
        "data": {
            "data_version": 2,
            "datetime": "2026-01-04 16:00:00",
            "light_lux": 1800.0,
            "temperature": 26.5,
            "humidity": 58.0,
            "soil_moisture": 2.8,
            "sensor_error": False,
            "soil_temperature1": 24.5,
            "soil_temperature2": 24.8,
            "capacitance_ch1": 12.5,
            "capacitance_ch2": 13.2,
            "capacitance_ch3": 12.8,
            "capacitance_ch4": 13.0,
            "battery_level": 90
        }
    }
]

print("=" * 70)
print("data_version対応パイプラインのテスト")
print("=" * 70)

# テスト用のパイプファイルを作成
test_pipe_path = "/tmp/test_plant_dashboard_pipe.jsonl"
with open(test_pipe_path, "w") as f:
    for record in test_pipe_data:
        f.write(json.dumps(record) + "\n")

print(f"\n✓ テスト用パイプファイルを作成しました: {test_pipe_path}")
print(f"  {len(test_pipe_data)} 件のレコードを書き込みました\n")

# パイプデータの内容を表示
print("パイプデータ内容:")
print("-" * 70)
for i, record in enumerate(test_pipe_data, 1):
    print(f"{i}. Device: {record['device_id']}")
    print(f"   data_version: {record['data_version']}")
    if record['data_version'] == 2:
        print(f"   v2追加データ: soil_temp1={record['data'].get('soil_temperature1')}°C, "
              f"cap_ch1={record['data'].get('capacitance_ch1')}pF")
    print()

# データベースからdevicesテーブルのdata_versionを確認
print("-" * 70)
print("データベースのdevicesテーブル確認:")
print("-" * 70)
conn = get_db_connection()
cursor = conn.cursor()
cursor.execute("SELECT device_id, device_name, data_version FROM devices WHERE device_id IN (?, ?)",
               ("plant_sensor_efda06", "plant_sensor_f2b9b2"))
devices = cursor.fetchall()
for device in devices:
    print(f"  {device['device_name']}: data_version={device['data_version']}")
conn.close()

print("\n" + "=" * 70)
print("テスト準備完了")
print("=" * 70)
print("\n次のステップ:")
print("1. plant_analyzer_daemon.py の process_data_pipe() を手動実行")
print("2. データベースのsensor_dataテーブルを確認")
print(f"\n実行例:")
print(f"  python3 -c 'import sys; sys.path.insert(0, \"/home/pi/plant_dashboard\"); from plant_analyzer_daemon import process_data_pipe; process_data_pipe()'")
print(f"\nまたは、以下のスクリプトを使用:")
print(f"  python3 /home/pi/plant_dashboard/test_process_pipe.py")
