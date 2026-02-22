#!/bin/bash
# =============================================================================
# Plant Dashboard ウォッチドッグスクリプト
#
# DBの最新センサーデータのタイムスタンプを監視し、
# 一定時間データが更新されていない場合に bluetooth daemon を再起動します。
#
# 通常サイクル: 60秒ごと
# 再起動閾値 : MAX_STALE_MINUTES 分以上データ更新なし → 再起動
# クールダウン: デーモン起動後 COOLDOWN_MINUTES 分は再起動しない
# =============================================================================

MAX_STALE_MINUTES=15
COOLDOWN_MINUTES=10
DB_PATH="/home/pi/plant_dashboard/data/plant_monitor.db"
SERVICE="plant_dashboard-daemon"
LOG_TAG="plant-watchdog"

# ─── デーモンの起動時刻チェック（起動直後は監視をスキップ）───
ACTIVE_SINCE=$(systemctl show "$SERVICE" --property=ActiveEnterTimestamp --value 2>/dev/null)
if [ -n "$ACTIVE_SINCE" ]; then
    ACTIVE_EPOCH=$(date -d "$ACTIVE_SINCE" +%s 2>/dev/null)
    if [ -n "$ACTIVE_EPOCH" ]; then
        UPTIME_SECONDS=$(( $(date +%s) - ACTIVE_EPOCH ))
        UPTIME_MINUTES=$(( UPTIME_SECONDS / 60 ))
        if [ "$UPTIME_MINUTES" -lt "$COOLDOWN_MINUTES" ]; then
            logger -t "$LOG_TAG" "INFO: デーモン起動後 ${UPTIME_MINUTES}分 (クールダウン中 ${COOLDOWN_MINUTES}分)。スキップします。"
            exit 0
        fi
    fi
fi

# ─── DBから最新タイムスタンプを取得 ───
LATEST=$(sqlite3 "$DB_PATH" "SELECT MAX(timestamp) FROM sensor_data;" 2>/dev/null)

if [ -z "$LATEST" ] || [ "$LATEST" = "NULL" ]; then
    logger -t "$LOG_TAG" "WARNING: sensor_data にデータがありません。スキップします。"
    exit 0
fi

# ─── 経過時間を計算 ───
NOW=$(date +%s)
LATEST_EPOCH=$(date -d "$LATEST" +%s 2>/dev/null)

if [ -z "$LATEST_EPOCH" ]; then
    logger -t "$LOG_TAG" "ERROR: タイムスタンプの解析に失敗しました: $LATEST"
    exit 1
fi

STALE_SECONDS=$(( NOW - LATEST_EPOCH ))
STALE_MINUTES=$(( STALE_SECONDS / 60 ))

# ─── 判定・再起動 ───
if [ "$STALE_MINUTES" -ge "$MAX_STALE_MINUTES" ]; then
    logger -t "$LOG_TAG" "ALERT: ${STALE_MINUTES}分間データ更新なし (閾値: ${MAX_STALE_MINUTES}分)。${SERVICE} を再起動します。"
    systemctl restart "$SERVICE"
    logger -t "$LOG_TAG" "INFO: ${SERVICE} を再起動しました。"
else
    logger -t "$LOG_TAG" "OK: 最終データ更新 ${STALE_MINUTES}分前 (${LATEST})"
fi
