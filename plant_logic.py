# plant_dashboard/plant_logic.py

import json
from datetime import datetime, date, timedelta
import logging

logger = logging.getLogger(__name__)

# --- Configuration Constants (future-proofing for external config) ---
GROWTH_STATE_STREAK_DAYS = {
    'fast_growth': 3,
    'slow_growth': 3,
    'hot_dormancy': 2,
    'cold_dormancy': 2
}
LETHAL_LIMIT_TRIGGER_COUNT = 3

class PlantStateAnalyzer:
    """Analyzes plant state and manages daily records."""

    def __init__(self, managed_plant, db_conn):
        self.conn = db_conn
        self.plant = managed_plant # This is a dict-like row from managed_plants
        self.plant_id = self.plant['managed_plant_id']
        self.thresholds = self._get_thresholds()
        self.temp_sensor_id = self.plant.get('assigned_plant_sensor_id') or self.plant.get('assigned_switchbot_id')

    def _get_thresholds(self):
        """Fetches and merges thresholds from the library (plants) and the specific instance (managed_plants)."""
        if not self.plant['library_plant_id']:
            return None

        # 1. Get general thresholds from the plants library
        library_thresholds_row = self.conn.execute(
            "SELECT * FROM plants WHERE plant_id = ?",
            (self.plant['library_plant_id'],)
        ).fetchone()
        
        if not library_thresholds_row:
            return None

        thresholds = dict(library_thresholds_row)

        # 2. The managed_plant object passed to the constructor already contains the instance-specific thresholds.
        # We can just update our thresholds dict with its values.
        thresholds.update(dict(self.plant))
        
        return thresholds

    def get_sensor_summary_for_date(self, target_date):
        """Aggregates sensor data for a specific date."""
        start_of_day = datetime.combine(target_date, datetime.min.time())
        end_of_day = datetime.combine(target_date, datetime.max.time())
        
        summary = {}
        
        if self.temp_sensor_id:
            query = """
                SELECT 
                    MAX(temperature) as daily_temp_max, MIN(temperature) as daily_temp_min, AVG(temperature) as daily_temp_ave,
                    MAX(humidity) as daily_humidity_max, MIN(humidity) as daily_humidity_min, AVG(humidity) as daily_humidity_ave
                FROM sensor_data WHERE device_id = ? AND timestamp BETWEEN ? AND ?
            """
            env_summary = self.conn.execute(query, (self.temp_sensor_id, start_of_day, end_of_day)).fetchone()
            if env_summary and env_summary['daily_temp_max'] is not None:
                summary.update(dict(env_summary))

        soil_sensor_id = self.plant.get('assigned_plant_sensor_id')
        if soil_sensor_id:
            soil_agg_query = """
                SELECT 
                    MAX(light_lux) as daily_light_max, MIN(light_lux) as daily_light_min, AVG(light_lux) as daily_light_ave,
                    MAX(soil_moisture) as daily_soil_moisture_max, MIN(soil_moisture) as daily_soil_moisture_min, AVG(soil_moisture) as daily_soil_moisture_ave
                FROM sensor_data WHERE device_id = ? AND timestamp BETWEEN ? AND ?
            """
            soil_summary = self.conn.execute(soil_agg_query, (soil_sensor_id, start_of_day, end_of_day)).fetchone()
            if soil_summary and soil_summary['daily_light_max'] is not None:
                summary.update(dict(soil_summary))

            latest_soil_query = "SELECT soil_moisture FROM sensor_data WHERE device_id = ? AND timestamp BETWEEN ? AND ? ORDER BY timestamp DESC LIMIT 1"
            latest_soil_row = self.conn.execute(latest_soil_query, (soil_sensor_id, start_of_day, end_of_day)).fetchone()
            if latest_soil_row and latest_soil_row['soil_moisture'] is not None:
                summary['soil_moisture_latest'] = latest_soil_row['soil_moisture']
            
            summary['daily_watering_events'] = 0

        return summary if summary else None

    def get_last_analysis(self, target_date):
        """Retrieves the most recent analysis record before a specific date."""
        row = self.conn.execute(
            "SELECT * FROM daily_plant_analysis WHERE managed_plant_id = ? AND analysis_date < ? ORDER BY analysis_date DESC LIMIT 1",
            (self.plant_id, target_date)
        ).fetchone()
        return dict(row) if row else None

    def run_analysis_for_date(self, target_date):
        """Runs the full analysis for a specific date and saves it to the database."""
        if not self.thresholds:
            logger.debug(f"Skipping analysis for '{self.plant['plant_name']}' due to missing library profile link.")
            return

        sensor_summary = self.get_sensor_summary_for_date(target_date)
        if not sensor_summary:
            logger.info(f"No sensor data for '{self.plant['plant_name']}' on {target_date}. Cannot perform analysis.")
            return

        last_analysis = self.get_last_analysis(target_date)
        
        new_growth_period, log_from_growth = self._determine_growth_period(sensor_summary, last_analysis)
        new_survival_status = self._determine_survival_limits(target_date)
        new_watering_advice, log_from_watering = self._determine_watering_advice(new_growth_period, sensor_summary, last_analysis)

        final_log = {**log_from_growth, **log_from_watering}

        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT INTO daily_plant_analysis (
                managed_plant_id, analysis_date, daily_temp_max, daily_temp_min, daily_temp_ave,
                daily_humidity_max, daily_humidity_min, daily_humidity_ave, daily_light_max, daily_light_min,
                daily_light_ave, daily_soil_moisture_max, daily_soil_moisture_min, daily_soil_moisture_ave,
                daily_watering_events, growth_period, survival_limit_status, watering_advice, analysis_log
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(managed_plant_id, analysis_date) DO UPDATE SET
                daily_temp_max=excluded.daily_temp_max, daily_temp_min=excluded.daily_temp_min, daily_temp_ave=excluded.daily_temp_ave,
                daily_humidity_max=excluded.daily_humidity_max, daily_humidity_min=excluded.daily_humidity_min, daily_humidity_ave=excluded.daily_humidity_ave,
                daily_light_max=excluded.daily_light_max, daily_light_min=excluded.daily_light_min, daily_light_ave=excluded.daily_light_ave,
                daily_soil_moisture_max=excluded.daily_soil_moisture_max, daily_soil_moisture_min=excluded.daily_soil_moisture_min, daily_soil_moisture_ave=excluded.daily_soil_moisture_ave,
                daily_watering_events=excluded.daily_watering_events, growth_period=excluded.growth_period, 
                survival_limit_status=excluded.survival_limit_status, watering_advice=excluded.watering_advice, analysis_log=excluded.analysis_log
        """, (
            self.plant_id, target_date.strftime('%Y-%m-%d'),
            sensor_summary.get('daily_temp_max'), sensor_summary.get('daily_temp_min'), sensor_summary.get('daily_temp_ave'),
            sensor_summary.get('daily_humidity_max'), sensor_summary.get('daily_humidity_min'), sensor_summary.get('daily_humidity_ave'),
            sensor_summary.get('daily_light_max'), sensor_summary.get('daily_light_min'), sensor_summary.get('daily_light_ave'),
            sensor_summary.get('daily_soil_moisture_max'), sensor_summary.get('daily_soil_moisture_min'), sensor_summary.get('daily_soil_moisture_ave'),
            sensor_summary.get('daily_watering_events', 0),
            new_growth_period, new_survival_status, new_watering_advice, json.dumps(final_log)
        ))
        self.conn.commit()
        logger.info(f"Analysis for '{self.plant['plant_name']}' on {target_date} completed. Growth: {new_growth_period}, Water: {new_watering_advice}")

    def _determine_growth_period(self, sensor_summary, last_analysis):
        if 'daily_temp_max' not in sensor_summary or 'daily_temp_min' not in sensor_summary:
            return (last_analysis['growth_period'] if last_analysis else 'unknown'), {}
        
        t = self.thresholds
        max_t, min_t = sensor_summary['daily_temp_max'], sensor_summary['daily_temp_min']
        last_log = json.loads(last_analysis['analysis_log']) if last_analysis and last_analysis.get('analysis_log') else {}
        new_log = { "fast_growth_streak": 0, "slow_growth_streak": 0, "hot_dormancy_streak": 0, "cold_dormancy_streak": 0 }

        conditions = {
            'fast_growth': t.get('growing_fast_temp_low') is not None and t['growing_fast_temp_low'] <= max_t <= t['growing_fast_temp_high'] and min_t > t['cold_dormancy_temp_high'],
            'slow_growth': t.get('growing_slow_temp_low') is not None and t['growing_slow_temp_low'] <= max_t <= t['growing_slow_temp_high'] and min_t > t['cold_dormancy_temp_high'],
            'hot_dormancy': t.get('hot_dormancy_temp_low') is not None and max_t > t['hot_dormancy_temp_low'],
            'cold_dormancy': t.get('cold_dormancy_temp_high') is not None and min_t < t['cold_dormancy_temp_high']
        }
        for state, met in conditions.items():
            if met: new_log[f"{state}_streak"] = last_log.get(f"{state}_streak", 0) + 1
        
        if new_log['hot_dormancy_streak'] >= GROWTH_STATE_STREAK_DAYS['hot_dormancy']: return 'hot_dormancy', new_log
        if new_log['cold_dormancy_streak'] >= GROWTH_STATE_STREAK_DAYS['cold_dormancy']: return 'cold_dormancy', new_log
        if new_log['fast_growth_streak'] >= GROWTH_STATE_STREAK_DAYS['fast_growth']: return 'fast_growth', new_log
        if new_log['slow_growth_streak'] >= GROWTH_STATE_STREAK_DAYS['slow_growth']: return 'slow_growth', new_log
        
        if last_analysis: return last_analysis['growth_period'], new_log
        
        if conditions['hot_dormancy']: return 'hot_dormancy', new_log
        if conditions['cold_dormancy']: return 'cold_dormancy', new_log
        if conditions['fast_growth']: return 'fast_growth', new_log
        if conditions['slow_growth']: return 'slow_growth', new_log
        
        return 'unknown', new_log

    def _determine_survival_limits(self, target_date):
        if not self.temp_sensor_id: return 'unknown'
        t = self.thresholds
        if t.get('lethal_temp_high') is None or t.get('lethal_temp_low') is None: return 'unknown'
        start_of_day, end_of_day = datetime.combine(target_date, datetime.min.time()), datetime.combine(target_date, datetime.max.time())
        high_triggers = self.conn.execute("SELECT COUNT(*) FROM sensor_data WHERE device_id = ? AND timestamp BETWEEN ? AND ? AND temperature > ?", (self.temp_sensor_id, start_of_day, end_of_day, t['lethal_temp_high'])).fetchone()[0]
        if high_triggers >= LETHAL_LIMIT_TRIGGER_COUNT: return 'lethal_high'
        low_triggers = self.conn.execute("SELECT COUNT(*) FROM sensor_data WHERE device_id = ? AND timestamp BETWEEN ? AND ? AND temperature < ?", (self.temp_sensor_id, start_of_day, end_of_day, t['lethal_temp_low'])).fetchone()[0]
        if low_triggers >= LETHAL_LIMIT_TRIGGER_COUNT: return 'lethal_low'
        return 'safe'
        
    def _determine_watering_advice(self, growth_period, sensor_summary, last_analysis):
        """Determines watering advice based on sensor data or growth period."""
        if not self.plant.get('assigned_plant_sensor_id') or 'soil_moisture_latest' not in sensor_summary:
            advice_map = {
                'fast_growth': self.thresholds.get('watering_growing', 'Check soil moisture.'),
                'slow_growth': self.thresholds.get('watering_slow_growing', 'Water when soil is dry.'),
                'hot_dormancy': self.thresholds.get('watering_hot_dormancy', 'Reduce watering.'),
                'cold_dormancy': self.thresholds.get('watering_cold_dormancy', 'Water sparingly.')
            }
            return advice_map.get(growth_period, 'N/A'), {}

        t = self.thresholds
        dry_thresh = t.get('soil_moisture_dry_threshold_voltage')
        wet_thresh = t.get('soil_moisture_wet_threshold_voltage')
        
        # Get the correct dry days threshold for the current growth period
        dry_days_map = {
            'fast_growth': t.get('watering_days_fast_growth'),
            'slow_growth': t.get('watering_days_slow_growth'),
            'hot_dormancy': t.get('watering_days_hot_dormancy'),
            'cold_dormancy': t.get('watering_days_cold_dormancy')
        }
        dry_days_thresh = dry_days_map.get(growth_period)
        
        if dry_thresh is None or wet_thresh is None or dry_days_thresh is None:
            return "Watering thresholds not set for this growth period.", {}
        
        current_voltage = sensor_summary['soil_moisture_latest']
        last_log = json.loads(last_analysis['analysis_log']) if last_analysis and last_analysis.get('analysis_log') else {}
        last_soil_state = last_log.get('soil_state', 'unknown')
        last_dry_streak = last_log.get('dry_streak_days', 0)
        
        new_soil_state = last_soil_state
        if last_soil_state in ('wet', 'optimal', 'unknown') and current_voltage > dry_thresh:
            new_soil_state = 'dry'
        elif last_soil_state in ('dry', 'optimal', 'unknown') and current_voltage < wet_thresh:
            new_soil_state = 'wet'
        elif wet_thresh <= current_voltage <= dry_thresh:
            new_soil_state = 'optimal'

        new_dry_streak = last_dry_streak + 1 if new_soil_state == 'dry' else 0
        
        advice = f"Soil is {new_soil_state}."
        if new_soil_state == 'dry' and new_dry_streak >= dry_days_thresh:
            advice = f"Watering needed (Dry for {new_dry_streak} days)"
            
        new_log = {"soil_state": new_soil_state, "dry_streak_days": new_dry_streak}
        return advice, new_log
