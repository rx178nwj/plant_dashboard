# plant_dashboard/plant_logic.py

import json
from datetime import datetime, date, timedelta
import logging

logger = logging.getLogger(__name__)

# --- 予約設計: 将来的にDBや設定ファイルから読み込めるように定数化 ---
GROWTH_STATE_STREAK_DAYS = {
    'fast_growth': 3,
    'slow_growth': 3,
    'hot_dormancy': 2,
    'cold_dormancy': 2
}
LETHAL_LIMIT_TRIGGER_COUNT = 3

class PlantStateAnalyzer:
    """プラントの状態を分析し、日々の記録を管理するクラス"""

    def __init__(self, managed_plant, db_conn):
        self.conn = db_conn
        self.plant = managed_plant
        self.plant_id = self.plant['managed_plant_id']
        self.thresholds = self._get_thresholds()

    def _get_thresholds(self):
        """ライブラリから植物の閾値を取得し、辞書に変換する"""
        if not self.plant['library_plant_id']:
            return None
        row = self.conn.execute("SELECT * FROM plants WHERE plant_id = ?", (self.plant['library_plant_id'],)).fetchone()
        return dict(row) if row else None

    def get_sensor_summary_for_date(self, target_date):
        """指定された日付のセンサーデータ（最高・最低気温など）を集計する"""
        start_of_day = datetime.combine(target_date, datetime.min.time())
        end_of_day = datetime.combine(target_date, datetime.max.time())
        
        # 環境センサーの集計
        temp_summary = None
        if self.plant.get('assigned_switchbot_id'):
            query = "SELECT MAX(temperature) as temp_max, MIN(temperature) as temp_min FROM sensor_data WHERE device_id = ? AND timestamp BETWEEN ? AND ?"
            temp_summary = self.conn.execute(query, (self.plant['assigned_switchbot_id'], start_of_day, end_of_day)).fetchone()

        # 土壌センサーの集計 (最新の値を取得)
        soil_summary = None
        if self.plant.get('assigned_plant_sensor_id'):
            query = "SELECT soil_moisture FROM sensor_data WHERE device_id = ? AND timestamp BETWEEN ? AND ? ORDER BY timestamp DESC LIMIT 1"
            soil_summary = self.conn.execute(query, (self.plant['assigned_plant_sensor_id'], start_of_day, end_of_day)).fetchone()
        
        summary = {}
        if temp_summary and temp_summary['temp_max'] is not None:
            summary.update({'daily_temp_max': temp_summary['temp_max'], 'daily_temp_min': temp_summary['temp_min']})
        if soil_summary and soil_summary['soil_moisture'] is not None:
            summary['soil_moisture_latest'] = soil_summary['soil_moisture']
        
        return summary if summary else None

    def get_last_analysis(self, target_date):
        """指定日以前の最新の分析記録を取得する"""
        row = self.conn.execute(
            "SELECT * FROM daily_plant_analysis WHERE managed_plant_id = ? AND analysis_date < ? ORDER BY analysis_date DESC LIMIT 1",
            (self.plant_id, target_date)
        ).fetchone()
        return dict(row) if row else None

    def run_analysis_for_date(self, target_date):
        if not self.thresholds:
            logger.debug(f"Skipping analysis for '{self.plant['plant_name']}' due to missing thresholds.")
            return

        sensor_summary = self.get_sensor_summary_for_date(target_date)
        if not sensor_summary:
            logger.info(f"No sensor data for '{self.plant['plant_name']}' on {target_date}. Cannot perform analysis.")
            return

        last_analysis = self.get_last_analysis(target_date)
        
        new_growth_period, log_from_growth = self._determine_growth_period(sensor_summary, last_analysis)
        new_survival_status = self._determine_survival_limits(target_date)
        new_watering_advice, log_from_watering = self._determine_watering_advice(new_growth_period, sensor_summary, last_analysis)

        # 2つのログをマージ
        final_log = {**log_from_growth, **log_from_watering}

        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT INTO daily_plant_analysis (managed_plant_id, analysis_date, daily_temp_max, daily_temp_min, growth_period, survival_limit_status, watering_advice, analysis_log)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(managed_plant_id, analysis_date) DO UPDATE SET
            daily_temp_max = excluded.daily_temp_max, daily_temp_min = excluded.daily_temp_min, growth_period = excluded.growth_period, 
            survival_limit_status = excluded.survival_limit_status, watering_advice = excluded.watering_advice, analysis_log = excluded.analysis_log
        """, (
            self.plant_id, target_date.strftime('%Y-%m-%d'), sensor_summary.get('daily_temp_max'), sensor_summary.get('daily_temp_min'),
            new_growth_period, new_survival_status, new_watering_advice, json.dumps(final_log)
        ))
        self.conn.commit()
        logger.info(f"Analysis for '{self.plant['plant_name']}' on {target_date} completed. Growth: {new_growth_period}, Water: {new_watering_advice}")


    def _determine_growth_period(self, sensor_summary, last_analysis):
        """(変更なし) Growth Periodsの判定ロジック"""
        if 'daily_temp_max' not in sensor_summary or 'daily_temp_min' not in sensor_summary:
            return last_analysis['growth_period'] if last_analysis else 'unknown', {}
        
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
        """(変更なし) Survival Temperature Limitsの判定ロジック"""
        if not self.plant.get('assigned_switchbot_id'): return 'unknown'
        t = self.thresholds
        if t.get('lethal_temp_high') is None or t.get('lethal_temp_low') is None: return 'unknown'
        start_of_day, end_of_day = datetime.combine(target_date, datetime.min.time()), datetime.combine(target_date, datetime.max.time())
        high_triggers = self.conn.execute("SELECT COUNT(*) FROM sensor_data WHERE device_id = ? AND timestamp BETWEEN ? AND ? AND temperature > ?", (self.plant['assigned_switchbot_id'], start_of_day, end_of_day, t['lethal_temp_high'])).fetchone()[0]
        if high_triggers >= LETHAL_LIMIT_TRIGGER_COUNT: return 'lethal_high'
        low_triggers = self.conn.execute("SELECT COUNT(*) FROM sensor_data WHERE device_id = ? AND timestamp BETWEEN ? AND ? AND temperature < ?", (self.plant['assigned_switchbot_id'], start_of_day, end_of_day, t['lethal_temp_low'])).fetchone()[0]
        if low_triggers >= LETHAL_LIMIT_TRIGGER_COUNT: return 'lethal_low'
        return 'safe'
        
    def _determine_watering_advice(self, growth_period, sensor_summary, last_analysis):
        """土壌センサーの有無に基づき、水やり判定ロジックを分岐させる"""
        # 土壌センサーが割り当てられていない場合は、従来の成長期ベースの判定
        if not self.plant.get('assigned_plant_sensor_id') or 'soil_moisture_latest' not in sensor_summary:
            advice_map = {
                'fast_growth': self.thresholds.get('watering_growing', 'Check soil moisture.'),
                'slow_growth': self.thresholds.get('watering_slow_growing', 'Water when soil is dry.'),
                'hot_dormancy': self.thresholds.get('watering_hot_dormancy', 'Reduce watering.'),
                'cold_dormancy': self.thresholds.get('watering_cold_dormancy', 'Water sparingly.')
            }
            return advice_map.get(growth_period, 'N/A'), {}

        # --- 電圧ベースの判定 ---
        t = self.thresholds
        dry_thresh = t.get('soil_moisture_dry_threshold_voltage')
        wet_thresh = t.get('soil_moisture_wet_threshold_voltage')
        dry_days_thresh = t.get('watering_dry_days_threshold')
        
        if dry_thresh is None or wet_thresh is None or dry_days_thresh is None:
            return "Watering thresholds not set.", {}
        
        current_voltage = sensor_summary['soil_moisture_latest']
        last_log = json.loads(last_analysis['analysis_log']) if last_analysis and last_analysis.get('analysis_log') else {}
        last_soil_state = last_log.get('soil_state', 'unknown')
        last_dry_streak = last_log.get('dry_streak_days', 0)
        
        new_soil_state = last_soil_state
        # ヒステリシスロジック
        if last_soil_state == 'wet' and current_voltage > dry_thresh:
            new_soil_state = 'dry'
        elif last_soil_state == 'dry' and current_voltage < wet_thresh:
            new_soil_state = 'wet'
        elif last_soil_state == 'unknown': # 初期状態
            if current_voltage > dry_thresh: new_soil_state = 'dry'
            if current_voltage < wet_thresh: new_soil_state = 'wet'

        # 乾燥日数の更新
        new_dry_streak = last_dry_streak + 1 if new_soil_state == 'dry' else 0
        
        # アドバイスの生成
        advice = f"Soil is {new_soil_state} (Dry streak: {new_dry_streak} days)"
        if new_soil_state == 'dry' and new_dry_streak >= dry_days_thresh:
            advice = f"Watering needed (Dry for {new_dry_streak} days)"
            
        new_log = {"soil_state": new_soil_state, "dry_streak_days": new_dry_streak}
        return advice, new_log

