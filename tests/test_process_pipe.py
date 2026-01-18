#!/usr/bin/env python3
"""
Test script to process the test pipe data and verify database storage
"""
import sys
import os
sys.path.insert(0, '/home/pi/plant_dashboard')

import json
import device_manager as dm
from database import get_db_connection

print("=" * 70)
print("パイプデータ処理テスト")
print("=" * 70)

# テストパイプファイルのパス
test_pipe_path = "/tmp/test_plant_dashboard_pipe.jsonl"

if not os.path.exists(test_pipe_path):
    print(f"\n✗ エラー: テストパイプファイルが見つかりません: {test_pipe_path}")
    print(f"  まず test_data_version_pipeline.py を実行してください")
    sys.exit(1)

print(f"\n✓ テストパイプファイルを読み込みます: {test_pipe_path}\n")

# パイプデータを手動で処理
lines_processed = 0
with open(test_pipe_path, "r") as f:
    for line in f:
        try:
            record = json.loads(line.strip())
            device_id = record.get("device_id")
            timestamp = record.get("timestamp")
            sensor_data = record.get("data")
            data_version = record.get("data_version", 1)

            print(f"処理中: {device_id} (data_version={data_version})")

            if sensor_data:
                dm.save_sensor_data(device_id, timestamp, sensor_data, data_version)
                dm.update_device_status(device_id, 'connected', sensor_data.get('battery_level'))
                print(f"  ✓ データを保存しました")
            else:
                print(f"  ✗ センサーデータがありません")

            lines_processed += 1
        except Exception as e:
            print(f"  ✗ エラー: {e}")

print(f"\n処理完了: {lines_processed} 件のレコードを処理しました")

# データベースからsensor_dataテーブルの最新データを確認
print("\n" + "=" * 70)
print("データベース確認: sensor_dataテーブルの最新レコード")
print("=" * 70)

conn = get_db_connection()
cursor = conn.cursor()

for device_id, device_name in [("plant_sensor_efda06", "PlantMonitor_20_DA06"),
                                ("plant_sensor_f2b9b2", "PlantMonitor_30_B9B2")]:
    print(f"\n{device_name} ({device_id}):")
    cursor.execute("""
        SELECT timestamp, temperature, humidity, soil_moisture, data_version,
               soil_temperature1, soil_temperature2,
               capacitance_ch1, capacitance_ch2, capacitance_ch3, capacitance_ch4
        FROM sensor_data
        WHERE device_id = ?
        ORDER BY timestamp DESC
        LIMIT 1
    """, (device_id,))

    row = cursor.fetchone()
    if row:
        print(f"  timestamp: {row['timestamp']}")
        print(f"  data_version: {row['data_version']}")
        print(f"  temperature: {row['temperature']}°C")
        print(f"  humidity: {row['humidity']}%")
        print(f"  soil_moisture: {row['soil_moisture']}")

        if row['data_version'] == 2:
            print(f"  [v2追加データ]")
            print(f"    soil_temperature1: {row['soil_temperature1']}°C")
            print(f"    soil_temperature2: {row['soil_temperature2']}°C")
            print(f"    capacitance_ch1: {row['capacitance_ch1']}pF")
            print(f"    capacitance_ch2: {row['capacitance_ch2']}pF")
            print(f"    capacitance_ch3: {row['capacitance_ch3']}pF")
            print(f"    capacitance_ch4: {row['capacitance_ch4']}pF")
    else:
        print(f"  ✗ データが見つかりません")

conn.close()

print("\n" + "=" * 70)
print("テスト完了")
print("=" * 70)

# テストファイルを削除
os.remove(test_pipe_path)
print(f"\n✓ テストパイプファイルを削除しました: {test_pipe_path}")
