# plant_dashboard

## 概要

このプロジェクトは、カスタムBLEセンサーデバイス（ESP32等）やSwitchBot製品から植物の環境データを収集し、Webダッシュボードでリアルタイムに可視化・管理するアプリケーションです。

## 主な機能

- **リアルタイムモニタリング**: BLE経由で植物センサーのデータ（土壌水分、照度、温度、湿度）を定期的に取得し、ダッシュボードに表示します。
- **環境履歴**: SwitchBot温湿度計などから取得した環境データをグラフで表示し、過去のトレンドを確認できます。
- **植物ライブラリ**: AI（Google Gemini）を活用して植物の最適な育成情報を検索し、データベース化できます。
- **画像管理**: Web上の画像URLまたはローカルからのファイルアップロードにより、植物の画像を登録できます。
- **デバイス管理**: 周辺のBLEデバイスをスキャンし、管理対象として簡単に登録できます。

## セットアップ手順

### 1. リポジトリのクローン

```bash
git clone <your-repository-url>
cd plant_dashboard
```

### 2. 環境変数の設定

Gemini API を使用するために、APIキーを設定する必要があります。

```bash
cp .env.example .env
```

作成した `.env` ファイルを開き、`YOUR_GEMINI_API_KEY_HERE` を実際のAPIキーに置き換えます。

```
GEMINI_API_KEY="AIzaSy...your...actual...key"
```

### 3. インストールと初期設定

```bash
bash scripts/install.sh
```

インストール完了後、仮想環境を有効化してデータベースを初期化します。

```bash
source .venv/bin/activate
flask init-db
```

### 4. アプリケーションの起動

```bash
gunicorn --workers=1 --threads=4 --bind 0.0.0.0:8000 wsgi:app
```

起動後、Webブラウザで `http://<RaspberryPiのIPアドレス>:8000` にアクセスしてください。

---

## MCPサーバーセットアップ（外部AI連携）

SQLiteデータベースをMCP（Model Context Protocol）経由で外部のAIクライアント（Claude Desktopなど）に公開できます。

### 構成

| サービス | プロトコル | ポート | 用途 |
|---|---|---|---|
| `plant-mcp.service` | REST API (mcpo) | 8765 | REST経由のデータアクセス |
| `plant-mcp-proxy.service` | SSE (mcp-proxy) | 8766 | Claude Desktop接続用 |

### セットアップ

以下のスクリプトを実行すると、必要なパッケージのインストールからサービスの起動まで自動で行います。

```bash
sudo bash scripts/setup_mcp_server.sh
```

スクリプトが行う処理：
1. `mcp-server-sqlite`, `mcpo`, `mcp-proxy` のインストール
2. systemdサービスファイルの作成
3. サービスの有効化・起動
4. 接続確認

### Claude Desktopへの接続

`%APPDATA%\Claude\claude_desktop_config.json`（Windows）に以下を追加します。

```json
"mcpServers": {
  "plant-monitor-db": {
    "command": "npx",
    "args": ["-y", "mcp-remote", "http://<RaspberryPiのIPアドレス>:8766/sse", "--allow-http"]
  }
}
```

> **注意**: `mcp-remote` の使用にはNode.js（npx）が必要です。

### サービスの状態確認

```bash
sudo systemctl status plant-mcp
sudo systemctl status plant-mcp-proxy
```

### 接続テスト（REST API）

```bash
curl -H "Authorization: Bearer plant-monitor" http://localhost:8765/list_tables
```

### サンプルプロンプト（Claude Desktop）

```
各デバイスの直近の土壌水分と温度を一覧で見せてください。

過去24時間でcapacitanceが最も低かったデバイスはどれですか？

全植物の現在の健康状態をまとめたレポートを作成してください。
```

---

## 技術スタック

| カテゴリ | 技術 |
|---|---|
| バックエンド | Python, Flask, Gunicorn |
| フロントエンド | HTML, CSS, JavaScript, Bootstrap, Chart.js |
| BLE通信 | Bleak (Pythonライブラリ) |
| データベース | SQLite |
| AI | Google Gemini API |
| MCP | mcp-server-sqlite, mcpo, mcp-proxy |
