# plant_dashboard/database.py

import sqlite3
import os
import logging
from config import DATABASE_PATH

logger = logging.getLogger(__name__)

def get_db_connection():
    os.makedirs(os.path.dirname(DATABASE_PATH), exist_ok=True)
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def migrate_db_schema(cursor):
    """Ensures all tables have the latest schema by adding missing columns."""
    logger.info("Checking database schema...")
    
    # --- Migrate managed_plants table ---
    cursor.execute("PRAGMA table_info(managed_plants)")
    managed_columns = [row['name'] for row in cursor.fetchall()]
    
    managed_new_columns = {
        'soil_moisture_dry_threshold_voltage': 'REAL',
        'soil_moisture_wet_threshold_voltage': 'REAL',
        'watering_days_fast_growth': 'INTEGER',
        'watering_days_slow_growth': 'INTEGER',
        'watering_days_hot_dormancy': 'INTEGER',
        'watering_days_cold_dormancy': 'INTEGER'
    }
    
    for col_name, col_type in managed_new_columns.items():
        if col_name not in managed_columns:
            try:
                cursor.execute(f"ALTER TABLE managed_plants ADD COLUMN {col_name} {col_type}")
                logger.info(f"Added column '{col_name}' to 'managed_plants' table.")
            except sqlite3.OperationalError as e:
                logger.error(f"Failed to add column '{col_name}' to 'managed_plants' table: {e}")

    # --- Migrate daily_plant_analysis table ---
    cursor.execute("PRAGMA table_info(daily_plant_analysis)")
    analysis_columns = [row['name'] for row in cursor.fetchall()]
    if 'watering_status' not in analysis_columns:
        try:
            cursor.execute("ALTER TABLE daily_plant_analysis ADD COLUMN watering_status TEXT")
            logger.info("Added column 'watering_status' to 'daily_plant_analysis' table.")
        except sqlite3.OperationalError as e:
            logger.error(f"Failed to add column 'watering_status' to 'daily_plant_analysis' table: {e}")


def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()

    # --- Table Creations ---
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS devices (device_id TEXT PRIMARY KEY, device_name TEXT NOT NULL, mac_address TEXT UNIQUE NOT NULL, last_seen DATETIME, battery_level INTEGER, connection_status TEXT DEFAULT 'disconnected', device_type TEXT NOT NULL DEFAULT 'plant_sensor');
    """)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS sensor_data (id INTEGER PRIMARY KEY AUTOINCREMENT, device_id TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP, temperature REAL, humidity REAL, light_lux REAL, soil_moisture REAL, FOREIGN KEY (device_id) REFERENCES devices(device_id));
    """)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS system_logs (id INTEGER PRIMARY KEY AUTOINCREMENT, device_id TEXT, log_level TEXT, message TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP);
    """)
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS plants (
        plant_id TEXT PRIMARY KEY, genus TEXT, species TEXT, variety TEXT, 
        image_url TEXT, origin_country TEXT, origin_region TEXT, monthly_temps_json TEXT, 
        growing_fast_temp_high REAL, growing_fast_temp_low REAL, 
        growing_slow_temp_high REAL, growing_slow_temp_low REAL, 
        hot_dormancy_temp_high REAL, hot_dormancy_temp_low REAL, 
        cold_dormancy_temp_high REAL, cold_dormancy_temp_low REAL, 
        lethal_temp_high REAL, lethal_temp_low REAL, 
        watering_growing TEXT, watering_slow_growing TEXT, watering_hot_dormancy TEXT, watering_cold_dormancy TEXT
    );
    """)
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS managed_plants (
        managed_plant_id TEXT PRIMARY KEY,
        plant_name TEXT NOT NULL,
        library_plant_id TEXT, 
        assigned_plant_sensor_id TEXT,
        assigned_switchbot_id TEXT,
        soil_moisture_dry_threshold_voltage REAL,
        soil_moisture_wet_threshold_voltage REAL,
        watering_days_fast_growth INTEGER,
        watering_days_slow_growth INTEGER,
        watering_days_hot_dormancy INTEGER,
        watering_days_cold_dormancy INTEGER,
        FOREIGN KEY (library_plant_id) REFERENCES plants(plant_id),
        FOREIGN KEY (assigned_plant_sensor_id) REFERENCES devices(device_id),
        FOREIGN KEY (assigned_switchbot_id) REFERENCES devices(device_id)
    );
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS daily_plant_analysis (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        managed_plant_id TEXT NOT NULL,
        analysis_date DATE NOT NULL,
        daily_temp_max REAL,
        daily_temp_min REAL,
        daily_temp_ave REAL,
        daily_humidity_max REAL,
        daily_humidity_min REAL,
        daily_humidity_ave REAL,
        daily_light_max REAL,
        daily_light_min REAL,
        daily_light_ave REAL,
        daily_soil_moisture_max REAL,
        daily_soil_moisture_min REAL,
        daily_soil_moisture_ave REAL,
        daily_watering_events INTEGER,
        daily_watering_volume REAL,
        daily_watering_duration INTEGER,
        growth_period TEXT,
        survival_limit_status TEXT,
        watering_status TEXT,
        watering_advice TEXT,
        analysis_log TEXT,
        UNIQUE(managed_plant_id, analysis_date),
        FOREIGN KEY (managed_plant_id) REFERENCES managed_plants(managed_plant_id)
    );
    """)

    migrate_db_schema(cursor)

    conn.commit()
    conn.close()
    print("Database initialization and migration check completed.")

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    init_db()

