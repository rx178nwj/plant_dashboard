# plant_dashboard/database.py

import sqlite3
import os
from config import DATABASE_PATH

def get_db_connection():
    os.makedirs(os.path.dirname(DATABASE_PATH), exist_ok=True)
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()

    # --- 既存テーブル (一部変更) ---
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS devices (device_id TEXT PRIMARY KEY, device_name TEXT NOT NULL, mac_address TEXT UNIQUE NOT NULL, last_seen DATETIME, battery_level INTEGER, connection_status TEXT DEFAULT 'disconnected', device_type TEXT NOT NULL DEFAULT 'plant_sensor');
    """)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS sensor_data (id INTEGER PRIMARY KEY AUTOINCREMENT, device_id TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP, temperature REAL, humidity REAL, light_lux REAL, soil_moisture REAL, FOREIGN KEY (device_id) REFERENCES devices(device_id));
    """)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS system_logs (id INTEGER PRIMARY KEY AUTOINCREMENT, device_id TEXT, log_level TEXT, message TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP);
    """)
    
    # --- ▼▼▼ plantsテーブルにカラムを追加 ▼▼▼ ---
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS plants (
        plant_id TEXT PRIMARY KEY, genus TEXT, species TEXT, variety TEXT, 
        image_url TEXT, origin_country TEXT, origin_region TEXT, monthly_temps_json TEXT, 
        growing_fast_temp_high REAL, growing_fast_temp_low REAL, 
        growing_slow_temp_high REAL, growing_slow_temp_low REAL, 
        hot_dormancy_temp_high REAL, hot_dormancy_temp_low REAL, 
        cold_dormancy_temp_high REAL, cold_dormancy_temp_low REAL, 
        lethal_temp_high REAL, lethal_temp_low REAL, 
        watering_growing TEXT, watering_slow_growing TEXT, watering_hot_dormancy TEXT, watering_cold_dormancy TEXT,
        -- New columns for soil moisture based watering
        soil_moisture_dry_threshold_voltage REAL,
        soil_moisture_wet_threshold_voltage REAL,
        watering_dry_days_threshold INTEGER
    );
    """)
    # --- ▲▲▲ plantsテーブルにカラムを追加 ▲▲▲ ---
    
    cursor.execute("DROP TABLE IF EXISTS plant_profiles;")
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS managed_plants (
        managed_plant_id TEXT PRIMARY KEY,
        plant_name TEXT NOT NULL,
        library_plant_id TEXT, 
        assigned_plant_sensor_id TEXT,
        assigned_switchbot_id TEXT,    
        FOREIGN KEY (library_plant_id) REFERENCES plants(plant_id),
        FOREIGN KEY (assigned_plant_sensor_id) REFERENCES devices(device_id),
        FOREIGN KEY (assigned_switchbot_id) REFERENCES devices(device_id)
    );
    """)
    cursor.execute("DROP TABLE IF EXISTS hourly_plant_metrics;")
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS daily_plant_analysis (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        managed_plant_id TEXT NOT NULL,
        analysis_date DATE NOT NULL,
        daily_temp_max REAL,
        daily_temp_min REAL,
        growth_period TEXT,
        survival_limit_status TEXT,
        watering_advice TEXT,
        analysis_log TEXT,
        UNIQUE(managed_plant_id, analysis_date),
        FOREIGN KEY (managed_plant_id) REFERENCES managed_plants(managed_plant_id)
    );
    """)

    conn.commit()
    conn.close()
    print("Database for Plant-centric Management initialized successfully.")

if __name__ == '__main__':
    init_db()

