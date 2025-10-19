## Plant Dashboard 説明書

本書は Raspberry Pi 上で動作する Plant Dashboard のセットアップ、起動、運用、およびトラブルシューティング手順をまとめたドキュメントです。カスタム BLE 植物センサー（ESP32 等）や SwitchBot デバイスから環境データを収集し、Web ダッシュボードで可視化します。

### 機能概要
- **リアルタイムモニタリング**: 土壌水分・照度・温度・湿度を定期取得し、ダッシュボードで表示
- **履歴表示**: 日/週/月/年のトレンド集計とグラフ表示
- **植物ライブラリ**: 植物情報（生育温度範囲・灌水ガイダンス等）を登録・編集
- **画像管理**: Web からの URL またはローカルアップロードで画像登録
- **デバイス管理**: BLE スキャン、デバイス登録、状態監視
- **自動分析**: 収集データを元に 1 時間おき・日替わりで日次分析を実施

---

## 1. システム要件
- Raspberry Pi（ARM Linux）
- Python 3.9+（スクリプトは仮想環境上で実行）
- BlueZ（`libglib2.0-dev` 経由の依存有）
- ネットワーク接続（Gemini API を使う場合）

---

## 2. リポジトリ取得と初期セットアップ

```bash
git clone <your-repository-url>
cd /home/pi/plant_dashboard
bash scripts/install.sh
```

`scripts/install.sh` が行うこと:
- apt で依存パッケージを導入（`python3-venv`, `python3-pip`, `libglib2.0-dev`）
- Python 仮想環境 `.venv` 作成と有効化
- `requirements.txt` のパッケージをインストール

環境変数の設定:
1) `.env` を用意（`wsgi.py` が Gunicorn 起動時に読み込み）

```
GEMINI_API_KEY=<任意: Google Gemini API キー>
SECRET_KEY=<Flask セッション鍵（任意。未設定時はデフォルト）>
```

2) Basic 認証は `config.py` の以下で既定値が有効です（必要に応じて変更）。
```startLine:endLine:/home/pi/plant_dashboard/config.py
# Basic認証設定
BASIC_AUTH_USERNAME = 'admin'
BASIC_AUTH_PASSWORD = 'plant'
BASIC_AUTH_FORCE = True # アプリ全体でBasic認証を有効にする
```

---

## 3. データベース初期化

アプリ起動時に `init_db()` が自動実行されますが、手動でも初期化できます。

```bash
source /home/pi/plant_dashboard/.venv/bin/activate
flask --app app.py init-db
```

SQLite DB は `data/plant_monitor.db` に作成され、必要なテーブルとスキーママイグレーションが適用されます。

---

## 4. 起動方法

### 4.1 開発用（直接起動）
```bash
source /home/pi/plant_dashboard/.venv/bin/activate
python /home/pi/plant_dashboard/app.py
# ブラウザ: http://<RaspberryPiのIP>:8000/
```

### 4.2 本番用（Gunicorn + systemd）

サービスインストール・起動は以下のスクリプトでまとめて実施できます。

```bash
bash /home/pi/plant_dashboard/scripts/start.sh
```

主なサービス:
- `plant_dashboard.service`（Web アプリ）
- `plant_dashboard-daemon.service`（BLE データ収集デーモン）
- `plant_analyzer_daemon.service`（解析デーモン）

サービスの手動操作例:
```bash
sudo systemctl status plant_dashboard.service
sudo systemctl restart plant_dashboard-daemon.service
sudo systemctl enable plant_analyzer_daemon.service
```

Gunicorn を手動で起動する場合:
```bash
/home/pi/plant_dashboard/start_server.sh
```

---

## 5. アーキテクチャ概要

- Web アプリ: Flask（`app.py` → `create_app()`）
  - 主要 Blueprint: `dashboard`, `devices`, `plants`, `management`
  - WSGI エントリ: `wsgi.py`（`.env` 読み込み後に `create_app()` 実行）
- データベース: SQLite（`database.py`）
  - 初期化/マイグレーション: `init_db()`, `migrate_db_schema()`
- デバイス連携:
  - BLE 収集デーモン: `bluetooth_daemon.py`
    - 新規データを `/tmp/plant_dashboard_pipe.jsonl`（JSON Lines）へ追記
    - コマンドは `/tmp/plant_dashboard_cmd_pipe.jsonl` から読み取り
  - 解析デーモン: `plant_analyzer_daemon.py`
    - パイプを取り込み DB 保存、1時間おきに日次分析実行
  - BLE 操作ライブラリ: `ble_manager.py`（Bleak 使用）
  - デバイス/センサーデータ I/O: `device_manager.py`

通信フロー（概要）:
1) `bluetooth_daemon.py` が DB 登録済みデバイスをポーリング → センサーデータを一時パイプに書き出し
2) `plant_analyzer_daemon.py` がパイプを取り込み DB に保存 → 集計/分析を実施
3) Web UI は `sensor_data` と `daily_plant_analysis` を参照して可視化
4) 閾値等のデバイス書き込みは Web → コマンドパイプ → BLE デーモンの順で反映

---

## 6. ディレクトリ構成（主要）

```
/home/pi/plant_dashboard
  app.py            # Flask アプリのエントリ（開発）
  wsgi.py           # Gunicorn エントリ（本番）
  config.py         # 設定（ログ、DB、Basic 認証、BLE UUID 等）
  database.py       # DB 接続/初期化/マイグレーション
  device_manager.py # デバイス状態更新とセンサーデータ保存
  ble_manager.py    # BLE 通信（Bleak）
  bluetooth_daemon.py      # 収集デーモン
  plant_analyzer_daemon.py # 解析デーモン
  requirements.txt
  scripts/
    install.sh, start.sh, stop.sh
  system_env/
    plant_dashboard.service
    plant_dashboard-daemon.service
    plant_analyzer_daemon.service
  templates/       # Flask テンプレート
  static/          # CSS/JS/画像
  docs/README.md   # 本ドキュメント
```

---

## 7. 主要設定

- ログ出力先: `logs/plant_dashboard.log`
- DB パス: `data/plant_monitor.db`
- アップロード先: `static/uploads/plant_images`
- BLE 関連:
  - `config.TARGET_SERVICE_UUID`: カスタムセンサーの Service UUID
  - 再接続設定: `RECONNECT_ATTEMPTS`, `RECONNECT_DELAY_BASE`
- デーモン間 I/O:
  - データパイプ: `/tmp/plant_dashboard_pipe.jsonl`
  - コマンドパイプ: `/tmp/plant_dashboard_cmd_pipe.jsonl`

---

## 8. 画面と API の概要

### 8.1 画面
- `GET /` ダッシュボード: 植物中心の現在値＋日次分析要約、履歴グラフ
- `GET /devices` デバイス管理: 登録一覧、BLE スキャン、追加
- `GET /plants` 植物ライブラリ: 植物情報の一覧・登録・編集、画像登録
- `GET /management` 管理: 管理対象植物とセンサー紐付け、水やり閾値の設定

### 8.2 代表 API（抜粋）
- `POST /api/ble-scan` 近傍 BLE デバイスをスキャン
- `POST /api/add-device` デバイス登録
- `GET/POST /api/managed-plants` 管理対象植物の取得/保存
- `GET/POST /api/managed-plant-watering-profile/<id>` 水やりプロファイル取得/更新
- `POST /api/device/<id>/write-watering-profile` 閾値書き込みコマンド送信（コマンドパイプへ）
- `GET /api/history/<device_id>` センサ履歴（集計オプション: 24h/7d/30d/1y）
- `GET /api/plant-analysis-history/<managed_plant_id>` 日別集計履歴

すべての画面/API は Basic 認証が必要です。

---

## 9. 運用 Tips

- サービスログの確認:
```bash
journalctl -u plant_dashboard.service -f
journalctl -u plant_dashboard-daemon.service -f
journalctl -u plant_analyzer_daemon.service -f
```

- BLE が不安定な場合:
  - 電源管理や距離、干渉を確認
  - `RECONNECT_ATTEMPTS` と `RECONNECT_DELAY_BASE` を調整
  - `sudo systemctl restart plant_dashboard-daemon.service`

- 解析遅延/負荷:
  - `plant_analyzer_daemon.py` の `DATA_FETCH_INTERVAL_SECONDS` / `ANALYSIS_INTERVAL_SECONDS` を調整

---

## 10. トラブルシューティング

- Web にアクセスできない
  - `sudo systemctl status plant_dashboard.service`
  - `.env` が存在し、`wsgi.py` が読み込めているか確認
  - ポート `8000` を他プロセスが使用していないか

- センサーデータが表示されない
  - `bluetooth_daemon` のログを確認
  - デバイスが DB に登録済みか、MAC アドレスが正しいか
  - 一時パイプ `/tmp/plant_dashboard_pipe.jsonl` が生成/更新されているか

- 閾値書き込みが反映されない
  - コマンドパイプ `/tmp/plant_dashboard_cmd_pipe.jsonl` の書き込み可否
  - 対象デバイスが起動・接続可能か（再接続リトライのログ）

---

## 11. セキュリティ

- 既定の Basic 認証は変更を推奨
- 画像アップロードの拡張子制限と 16MB 上限あり
- `SECRET_KEY` は本番では必ず強固な値を設定

---

## 12. ライセンス / 謝辞

- 本プロジェクトは Flask, Bleak, httpx, Gunicorn ほかに依存しています。


