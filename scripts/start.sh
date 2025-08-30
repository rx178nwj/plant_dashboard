#!/bin/bash

# プロジェクトルートに移動
cd "$(dirname "$0")/.."

# 仮想環境が存在するか確認し、アクティベート
if [ -d ".venv" ]; then
  echo "--- Activating virtual environment ---"
  source .venv/bin/activate
else
  echo "Virtual environment not found. Please run install.sh first."
  exit 1
fi

echo "--- Starting Gunicorn server ---"

# wsgi:app を使用してアプリケーションを起動します。
# workerを1に設定して、バックグラウンドスレッドの重複を防ぎます。
gunicorn \
    --workers=1 \
    --threads=4 \
    --bind 0.0.0.0:8000 \
    --log-level=info \
    --log-file=logs/gunicorn.log \
    --access-logfile=logs/access.log \
    --error-logfile=logs/error.log \
    --pid logs/gunicorn.pid \
    --daemon \
    wsgi:app

echo "Gunicorn has been started in the background."
echo "Check logs/gunicorn.log for status."
echo "To stop the server, run: kill \`cat logs/gunicorn.pid\`"
