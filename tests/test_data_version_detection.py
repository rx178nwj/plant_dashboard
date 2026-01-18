#!/usr/bin/env python3
"""
Test script for data_version detection logic
"""
import sys
sys.path.insert(0, '/home/pi/plant_dashboard')

from blueprints.devices.routes import determine_data_version

# テストケース
test_cases = [
    ("PlantMonitor_30_B9B2", 2),
    ("PlantMonitor_30_AAAA", 2),
    ("PlantMonitor_35_1234", 2),
    ("PlantMonitor_20_DA06", 1),
    ("PlantMonitor_20_D94A", 1),
    ("PlantMonitor_10_ABCD", 1),
    ("SoilMonitorV1", 1),
    ("SoilMonitorV1_1", 1),
    ("SwitchBot Meter Plus", 1),
    ("SwitchBot Meter No.2", 1),
    ("PlantMonitor_ABC_1234", 1),  # 無効な形式
    ("", 1),  # 空文字列
    (None, 1),  # None
]

print("=" * 60)
print("data_version検出ロジックのテスト")
print("=" * 60)

passed = 0
failed = 0

for device_name, expected_version in test_cases:
    result = determine_data_version(device_name)
    status = "✓ PASS" if result == expected_version else "✗ FAIL"

    if result == expected_version:
        passed += 1
    else:
        failed += 1

    device_display = f"'{device_name}'" if device_name else "None/Empty"
    print(f"{status} | {device_display:<30} => data_version={result} (expected: {expected_version})")

print("=" * 60)
print(f"結果: {passed} passed, {failed} failed")
print("=" * 60)

if failed == 0:
    print("✓ すべてのテストが成功しました!")
    sys.exit(0)
else:
    print("✗ テストに失敗したケースがあります")
    sys.exit(1)
