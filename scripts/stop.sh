#!/bin/bash

# プロジェクトルートに移動
cd "$(dirname "$0")/.."

PID_FILE="logs/gunicorn.pid"

if [ -f "$PID_FILE" ]; then
    echo "--- Stopping Gunicorn server (PID: $(cat $PID_FILE)) ---"
    # PIDファイルからプロセスIDを読み取り、プロセスを停止
    kill $(cat $PID_FILE)
    # PIDファイルを削除
    rm $PID_FILE
    echo "Server stopped."
else
    echo "Gunicorn is not running (PID file not found)."
fi
