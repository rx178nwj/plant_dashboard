# plant_dashboard/plant_analyzer_daemon.py
import logging
import time
import json
import os
from datetime import datetime, date, timedelta

import config
import device_manager as dm
from database import init_db, get_db_connection
from plant_logic import PlantStateAnalyzer

DATA_PIPE_PATH = "/tmp/plant_dashboard_pipe.jsonl"
# データ取り込みの間隔（秒）
DATA_FETCH_INTERVAL_SECONDS = 60  # 1分
# 1時間ごとに分析を実行
ANALYSIS_INTERVAL_SECONDS = 3600

logging.basicConfig(
    level=config.LOG_LEVEL,
    format='%(asctime)s - [AnalyzerDaemon] - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(config.LOG_FILE_PATH),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)
# ★★★ デバッグログを表示するためのおまじない ★★★
#logger.setLevel(logging.DEBUG)
# ★★★ ここまで ★★★
def process_data_pipe():
    """一時ファイルを処理してDBに保存する"""
    if not os.path.exists(DATA_PIPE_PATH):
        return
    
    # 複数のアナライザープロセスが同時に動くことを想定し、一意なファイル名で処理
    processing_path = DATA_PIPE_PATH + f".processing_{os.getpid()}"
    try:
        os.rename(DATA_PIPE_PATH, processing_path)
    except FileNotFoundError:
        return # 他のプロセスが先にリネームした場合

    lines_processed = 0
    with open(processing_path, "r") as f:
        for line in f:
            try:
                record = json.loads(line.strip())
                device_id = record.get("device_id")
                timestamp = record.get("timestamp")
                sensor_data = record.get("data")
                data_version = record.get("data_version", 1)  # デフォルトは1
                
                logger.info(f"Processing data for device {device_id} at {timestamp}, data_version={data_version}")

                if record.get("error"):
                    dm.update_device_status(device_id, 'error')
                elif sensor_data:
                    # data_versionを渡してデータを保存
                    dm.save_sensor_data(device_id, timestamp, sensor_data, data_version)
                    dm.update_device_status(device_id, 'connected', sensor_data.get('battery_level'))
                else:
                    dm.update_device_status(device_id, 'disconnected')
                lines_processed += 1
            except Exception as e:
                logger.error(f"Error processing record: {line.strip()} - {e}")
    
    os.remove(processing_path)
    if lines_processed > 0:
        logger.info(f"Processed {lines_processed} records from the data pipe.")

def run_full_analysis(target_date):
    """指定された日付の分析をすべての管理植物に対して実行する"""
    conn = get_db_connection()
    try:
        managed_plants = conn.execute("SELECT * FROM managed_plants").fetchall()
        logger.info(f"Found {len(managed_plants)} managed plants to analyze for {target_date}.")
        for plant_row in managed_plants:
            analyzer = PlantStateAnalyzer(dict(plant_row), conn)
            analyzer.run_analysis_for_date(target_date)
    except Exception as e:
        logger.error(f"An error occurred during the analysis for {target_date}: {e}", exc_info=True)
    finally:
        if conn:
            conn.close()

def main_loop():
    logger.info("Starting Plant Analyzer Daemon loop...")
    last_processed_date = None
    
    init_db()

    # --- 設定値 ---
    # データ取り込みの間隔（秒）
    #DATA_FETCH_INTERVAL_SECONDS = 60  # 1分
    # 分析実行の間隔（秒）
    #ANALYSIS_INTERVAL_SECONDS = 3600 # 1時間

    # 最後に分析処理を実行した時刻を記録する変数
    # プログラム起動後、すぐに初回の分析が実行されるように初期値は0にしておきます
    last_analysis_execution_time = 0

    while True:
        # ループの開始時刻を記録
        loop_start_time = time.time()

        # --- ① Bluetoothデーモンからのデータを取り込む (毎分実行) ---
        logger.info("Processing data from pipe...")
        process_data_pipe()

        # --- ② 前回の分析から1時間以上経過したかチェック ---
        current_time = time.time()
        if (current_time - last_analysis_execution_time) >= ANALYSIS_INTERVAL_SECONDS:
            logger.info("Starting hourly analysis process...")
            
            # 最後に分析を実行した時刻を現在時刻に更新
            last_analysis_execution_time = current_time
            
            current_date = date.today()
            
            # --- ③ 日付が変わり、最初の実行かチェック ---
            if last_processed_date != current_date:
                yesterday = current_date - timedelta(days=1)
                # 初回起動時以外は、前日分の分析を最終確定させる
                if last_processed_date is not None:
                    logger.info(f"New day detected. Finalizing analysis for {yesterday}...")
                    run_full_analysis(yesterday)
                last_processed_date = current_date

            # --- ④ 1時間ごとに当日の暫定分析を実行 ---
            logger.info(f"Running hourly analysis for {current_date}...")
            run_full_analysis(current_date)
            
            logger.info("Hourly analysis finished.")

        # --- 次のデータ取り込みまで待機 ---
        # 処理にかかった時間を差し引いて、ループ全体が約1分間隔になるよう調整
        elapsed_time = time.time() - loop_start_time
        sleep_time = DATA_FETCH_INTERVAL_SECONDS - elapsed_time
        if sleep_time > 0:
            logger.info(f"Waiting for {sleep_time:.2f} seconds until next data fetch.")
            time.sleep(sleep_time)

if __name__ == "__main__":
    try:
        main_loop()
    except KeyboardInterrupt:
        logger.info("Analyzer daemon stopped by user.")
    except Exception as e:
        logger.critical(f"Analyzer daemon stopped due to a critical error: {e}", exc_info=True)

