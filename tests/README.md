# テストスクリプト

このフォルダにはPlant Dashboardのdata_version機能に関するテストスクリプトが含まれています。

## ファイル一覧

| ファイル名 | 説明 |
|-----------|------|
| `temp_update_data_version.py` | 既存デバイスのdata_versionを更新するマイグレーションスクリプト |
| `test_data_version_detection.py` | デバイス名からdata_versionを判定するロジックのテスト |
| `test_data_version_pipeline.py` | パイプラインにdata_versionが正しく伝播されるかのテスト |
| `test_process_pipe.py` | パイプデータの処理とDB保存のテスト |

---

## Raspberry Piでの使用方法

### 前提条件
- Python 3.7以上がインストールされていること
- Plant Dashboardが `/home/pi/plant_dashboard` に配置されていること
- 仮想環境が有効化されていること（推奨）

### 実行方法

```bash
# プロジェクトディレクトリに移動
cd /home/pi/plant_dashboard

# 仮想環境を有効化（使用している場合）
source venv/bin/activate

# 1. data_version判定ロジックのテスト
python3 tests/test_data_version_detection.py

# 2. パイプラインテスト（テストデータ作成）
python3 tests/test_data_version_pipeline.py

# 3. パイプデータ処理テスト
python3 tests/test_process_pipe.py

# 4. 既存デバイスのdata_version更新（マイグレーション）
python3 tests/temp_update_data_version.py
```

### テスト実行順序

1. **test_data_version_detection.py** - 最初に実行。判定ロジックの動作確認
2. **test_data_version_pipeline.py** - テスト用パイプファイルを作成
3. **test_process_pipe.py** - パイプデータを処理してDBに保存（2の後に実行）
4. **temp_update_data_version.py** - 本番環境で既存デバイスを更新する際に使用

---

## Windowsでの使用方法

### 前提条件
- Python 3.7以上がインストールされていること
- プロジェクトがローカルにクローンされていること

### セットアップ

```powershell
# プロジェクトディレクトリに移動
cd C:\path\to\plant_dashboard

# 仮想環境を作成（初回のみ）
python -m venv venv

# 仮想環境を有効化
.\venv\Scripts\Activate.ps1

# 依存パッケージをインストール
pip install -r requirements.txt
```

### 実行方法

```powershell
# 1. data_version判定ロジックのテスト
python tests\test_data_version_detection.py

# 2. パイプラインテスト（テストデータ作成）
python tests\test_data_version_pipeline.py

# 3. パイプデータ処理テスト
python tests\test_process_pipe.py

# 4. 既存デバイスのdata_version更新（マイグレーション）
python tests\temp_update_data_version.py
```

### 注意事項（Windows）

- パイプファイルのパスがLinux形式（`/tmp/...`）になっているため、Windowsで実行する場合はテストスクリプト内のパスを修正する必要があります
- `test_data_version_pipeline.py` と `test_process_pipe.py` のパス修正例：
  ```python
  # 変更前
  test_pipe_path = "/tmp/test_plant_dashboard_pipe.jsonl"

  # 変更後（Windows）
  import tempfile
  test_pipe_path = os.path.join(tempfile.gettempdir(), "test_plant_dashboard_pipe.jsonl")
  ```
- Bluetooth機能はRaspberry Pi専用のため、Windowsではセンサーデータ取得の実機テストはできません

---

## テスト結果の確認

### データベース確認

```bash
# Raspberry Pi
sqlite3 /home/pi/plant_dashboard/data/plant_monitor.db

# デバイスのdata_version確認
SELECT device_id, device_name, data_version FROM devices;

# センサーデータのdata_version確認
SELECT device_id, timestamp, data_version, soil_temperature1, capacitance_ch1
FROM sensor_data
ORDER BY timestamp DESC
LIMIT 10;
```

### 期待される結果

- `PlantMonitor_30_XXXX` 形式のデバイス → `data_version = 2`
- `PlantMonitor_20_XXXX` 形式のデバイス → `data_version = 1`
- その他のデバイス（SwitchBot等） → `data_version = 1`
