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
                device_id, sensor_data = record.get("device_id"), record.get("data")
                
                if record.get("error"):
                    dm.update_device_status(device_id, 'error')
                elif sensor_data:
                    dm.save_sensor_data(device_id, sensor_data)
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

    while True:
        # --- ① Bluetoothデーモンからのデータを取り込む ---
        process_data_pipe()

        current_date = date.today()
        
        # --- ② 日付が変わり、最初の実行かチェック ---
        if last_processed_date != current_date:
            yesterday = current_date - timedelta(days=1)
            # 初回起動時以外は、前日分の分析を最終確定させる
            if last_processed_date is not None:
                 logger.info(f"New day detected. Finalizing analysis for {yesterday}...")
                 run_full_analysis(yesterday)
            last_processed_date = current_date

        # --- ③ 1時間ごとに当日の暫定分析を実行 ---
        logger.info(f"Running hourly analysis for {current_date}...")
        run_full_analysis(current_date)
        
        logger.info(f"Analysis cycle finished. Waiting for {ANALYSIS_INTERVAL_SECONDS} seconds.")
        time.sleep(ANALYSIS_INTERVAL_SECONDS)

if __name__ == "__main__":
    try:
        main_loop()
    except KeyboardInterrupt:
        logger.info("Analyzer daemon stopped by user.")
    except Exception as e:
        logger.critical(f"Analyzer daemon stopped due to a critical error: {e}", exc_info=True)

