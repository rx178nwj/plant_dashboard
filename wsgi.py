# wsgi.py
import threading
from dotenv import load_dotenv

# -------------------------------------------------------------------
# ▼▼▼ 最重要修正点 ▼▼▼
# Gunicornワーカーが起動する際に、他のどのモジュールよりも先に
# .envファイルから環境変数を読み込むようにします。
load_dotenv()
# -------------------------------------------------------------------

from app import create_app, run_async_loop, init_db

# データベースを初期化
init_db()

# Flaskアプリケーションインスタンスを作成
app = create_app()

# バックグラウンドのデータ収集スレッドを開始
bg_thread = threading.Thread(target=run_async_loop, daemon=True)
bg_thread.start()
