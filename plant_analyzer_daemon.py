# plant_dashboard/plant_analyzer_daemon.py
import asyncio
import logging
import time
from datetime import datetime, timedelta

import config
import device_manager as dm
from ble_manager import PlantDeviceBLE, get_switchbot_adv_data
from database import init_db, get_db_connection

logging.basicConfig(
    level=config.LOG_LEVEL,
    format='%(asctime)s - [AnalyzerDaemon] - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(config.LOG_FILE_PATH),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def analyze_plant_status(conn, managed_plant_id, library_plant_id, current_temp):
    """過去のデータと現在の温度から成長期間と生存限界を判定する"""
    plant_thresholds = conn.execute("SELECT * FROM plants WHERE plant_id = ?", (library_plant_id,)).fetchone()
    if not plant_thresholds:
        return 'unknown', 'unknown'

    # 生存限界温度の判定
    survival_status = 'safe'
    if plant_thresholds['lethal_temp_high'] is not None and current_temp > plant_thresholds['lethal_temp_high']:
        survival_status = 'lethal_high'
    elif plant_thresholds['lethal_temp_low'] is not None and current_temp < plant_thresholds['lethal_temp_low']:
        survival_status = 'lethal_low'

    # 成長期間の判定（過去1週間の平均気温に基づく）
    one_week_ago = datetime.now() - timedelta(days=7)
    # hourly_plant_metricsテーブルから過去1週間の平均気温を取得
    avg_temp_last_week_row = conn.execute(
        "SELECT AVG(temp_avg) as avg_temp FROM hourly_plant_metrics WHERE managed_plant_id = ? AND timestamp >= ?",
        (managed_plant_id, one_week_ago)
    ).fetchone()
    
    avg_temp_last_week = avg_temp_last_week_row['avg_temp'] if avg_temp_last_week_row and avg_temp_last_week_row['avg_temp'] is not None else current_temp
    
    growth_status = 'unknown'
    if plant_thresholds['growing_fast_temp_low'] is not None and plant_thresholds['growing_fast_temp_high'] is not None and \
       plant_thresholds['growing_fast_temp_low'] <= avg_temp_last_week <= plant_thresholds['growing_fast_temp_high']:
        growth_status = 'fast_growth'
    elif plant_thresholds['growing_slow_temp_low'] is not None and plant_thresholds['growing_slow_temp_high'] is not None and \
         plant_thresholds['growing_slow_temp_low'] <= avg_temp_last_week <= plant_thresholds['growing_slow_temp_high']:
        growth_status = 'slow_growth'
    elif plant_thresholds['hot_dormancy_temp_low'] is not None and avg_temp_last_week > plant_thresholds['hot_dormancy_temp_low']:
        growth_status = 'hot_dormancy'
    elif plant_thresholds['cold_dormancy_temp_high'] is not None and avg_temp_last_week < plant_thresholds['cold_dormancy_temp_high']:
        growth_status = 'cold_dormancy'
        
    return growth_status, survival_status

async def summarize_hourly_data():
    """1時間ごとにデータを集計し、分析する"""
    logger.info("Hourly summary and analysis task started.")
    conn = get_db_connection()
    
    try:
        managed_plants = conn.execute("SELECT * FROM managed_plants WHERE assigned_switchbot_id IS NOT NULL AND library_plant_id IS NOT NULL").fetchall()
        
        # 1時間前の時刻を取得
        target_hour_start = (datetime.now() - timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
        target_hour_end = target_hour_start + timedelta(hours=1)

        for plant in managed_plants:
            sensor_id = plant['assigned_switchbot_id'] # 環境センサーを基準とする
            
            # 1時間分のデータを集計
            query = """
                SELECT
                    AVG(temperature) as temp_avg, MAX(temperature) as temp_max, MIN(temperature) as temp_min,
                    AVG(humidity) as humidity_avg, MAX(humidity) as humidity_max, MIN(humidity) as humidity_min,
                    AVG(light_lux) as light_lux_avg, MAX(light_lux) as light_lux_max, MIN(light_lux) as light_lux_min
                FROM sensor_data
                WHERE device_id = ? AND timestamp >= ? AND timestamp < ?
            """
            summary = conn.execute(query, (sensor_id, target_hour_start, target_hour_end)).fetchone()

            if summary and summary['temp_avg'] is not None:
                # 判定処理
                growth_status, survival_status = analyze_plant_status(conn, plant['managed_plant_id'], plant['library_plant_id'], summary['temp_avg'])

                # 結果をDBに保存
                conn.execute("""
                    INSERT INTO hourly_plant_metrics (
                        managed_plant_id, timestamp, 
                        temp_avg, temp_max, temp_min, 
                        humidity_avg, humidity_max, humidity_min, 
                        light_lux_avg, light_lux_max, light_lux_min,
                        growth_period_status, survival_limit_status
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    plant['managed_plant_id'], target_hour_start,
                    summary['temp_avg'], summary['temp_max'], summary['temp_min'],
                    summary['humidity_avg'], summary['humidity_max'], summary['humidity_min'],
                    summary['light_lux_avg'], summary['light_lux_max'], summary['light_lux_min'],
                    growth_status, survival_status
                ))
                conn.commit()
                logger.info(f"Hourly metrics for '{plant['plant_name']}' have been saved.")
            else:
                logger.info(f"No sensor data found for '{plant['plant_name']}' in the last hour to summarize.")

    except Exception as e:
        logger.error(f"An error occurred during hourly summary: {e}", exc_info=True)
    finally:
        conn.close()


async def main_loop():
    logger.info("Starting Plant Analyzer Daemon loop...")
    plant_sensor_connections = {}
    last_summary_hour = -1

    init_db()

    while True:
        # --- データ収集 ---
        devices_to_poll = dm.load_devices_from_db()
        if not devices_to_poll:
            logger.info("No devices in DB. Waiting...")
            await asyncio.sleep(config.DATA_FETCH_INTERVAL)
            continue
        
        logger.info(f"Starting data collection for {len(devices_to_poll)} devices.")
        for device_id, device in devices_to_poll.items():
            try:
                sensor_data = None
                if device['device_type'] == 'plant_sensor':
                    if device_id not in plant_sensor_connections:
                        plant_sensor_connections[device_id] = PlantDeviceBLE(device['mac_address'], device_id)
                    ble_device = plant_sensor_connections[device_id]
                    if await ble_device.ensure_connection():
                        sensor_data = await ble_device.get_sensor_data()
                elif device['device_type'].startswith('switchbot_'):
                    sensor_data = await get_switchbot_adv_data(device['mac_address'])
                
                if sensor_data:
                    dm.save_sensor_data(device_id, sensor_data)
                    dm.update_device_status(device_id, 'connected', sensor_data.get('battery_level'))
                else:
                    dm.update_device_status(device_id, 'disconnected')
            except Exception as e:
                logger.error(f"Error collecting data for {device_id}: {e}", exc_info=True)
                dm.update_device_status(device_id, 'error')
            await asyncio.sleep(2)

        # --- 1時間ごとの集計・分析タスク ---
        current_hour = datetime.now().hour
        if current_hour != last_summary_hour:
            await summarize_hourly_data()
            last_summary_hour = current_hour

        logger.info(f"Cycle finished. Waiting for {config.DATA_FETCH_INTERVAL} seconds.")
        await asyncio.sleep(config.DATA_FETCH_INTERVAL)

if __name__ == "__main__":
    try:
        asyncio.run(main_loop())
    except KeyboardInterrupt:
        logger.info("Daemon stopped by user.")
    except Exception as e:
        logger.critical(f"Daemon stopped due to a critical error: {e}", exc_info=True)