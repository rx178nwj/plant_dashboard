# plant_dashboard
Plant Dashboard概要このプロジェクトは、カスタムBLEセンサーデバイス（ESP32等）やSwitchBot製品から植物の環境データを収集し、Webダッシュボードでリアルタイムに可視化・管理するアプリケーションです。主な機能リアルタイムモニタリング: BLE経由で植物センサーのデータ（土壌水分、照度、温度、湿度）を定期的に取得し、ダッシュボードに表示します。環境履歴: SwitchBot温湿度計などから取得した環境データをグラフで表示し、過去のトレンドを確認できます。植物ライブラリ: AI（Google Gemini）を活用して植物の最適な育成情報を検索し、データベース化できます。画像管理: Web上の画像URLまたはローカルからのファイルアップロードにより、植物の画像を登録できます。デバイス管理: 周辺のBLEデバイスをスキャンし、管理対象として簡単に登録できます。セットアップ手順1. リポジトリのクローンgit clone <your-repository-url>
cd plant_dashboard
2. 環境変数の設定Gemini API を使用するために、APIキーを設定する必要があります。.env.example ファイルをコピーして .env という名前のファイルを作成します。cp .env.example .env
作成した .env ファイルをお好みのエディタで開き、プレースホルダー YOUR_GEMINI_API_KEY_HERE をご自身のAPIキーに置き換えます。GEMINI_API_KEY="AIzaSy...your...actual...key"
3. インストールと初期設定提供されている install.sh スクリプトを実行して、必要なパッケージのインストールとPython仮想環境のセットアップを行います。bash scripts/install.sh
インストールが完了したら、仮想環境を有効化し、データベースを初期化します。source .venv/bin/activate
flask init-db
4. アプリケーションの起動Gunicornを使用してWebサーバーを起動します。gunicorn --workers=1 --threads=4 --bind 0.0.0.0:8000 wsgi:app
起動後、Webブラウザで http://<RaspberryPiのIPアドレス>:8000 にアクセスしてください。技術スタックバックエンド: Python, Flask, Gunicornフロントエンド: HTML, CSS, JavaScript, Bootstrap, Chart.jsBLE通信: Bleak (Pythonライブラリ)データベース: SQLiteAI: Google Gemini API