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
        """ライブラリから植物の閾値を取得"""
        if not self.plant['library_plant_id']:
            return None
        return self.conn.execute("SELECT * FROM plants WHERE plant_id = ?", (self.plant['library_plant_id'],)).fetchone()

    def get_sensor_summary_for_date(self, target_date):
        """指定された日付のセンサーデータ（最高・最低気温など）を集計する"""
        start_of_day = datetime.combine(target_date, datetime.min.time())
        end_of_day = datetime.combine(target_date, datetime.max.time())
        
        query = """
            SELECT MAX(temperature) as temp_max, MIN(temperature) as temp_min
            FROM sensor_data
            WHERE device_id = ? AND timestamp BETWEEN ? AND ?
        """
        summary = self.conn.execute(query, (self.plant['assigned_switchbot_id'], start_of_day, end_of_day)).fetchone()
        
        if summary and summary['temp_max'] is not None:
            return {'daily_temp_max': summary['temp_max'], 'daily_temp_min': summary['temp_min']}
        return None

    def get_last_analysis(self, target_date):
        """指定日以前の最新の分析記録を取得する"""
        row = self.conn.execute(
            "SELECT * FROM daily_plant_analysis WHERE managed_plant_id = ? AND analysis_date < ? ORDER BY analysis_date DESC LIMIT 1",
            (self.plant_id, target_date)
        ).fetchone()
        return dict(row) if row else None

    def run_analysis_for_date(self, target_date):
        """指定された日付の状態を分析・判定し、DBに保存する"""
        if not self.thresholds or not self.plant['assigned_switchbot_id']:
            logger.debug(f"Skipping analysis for '{self.plant['plant_name']}' due to missing thresholds or sensor assignment.")
            return

        sensor_summary = self.get_sensor_summary_for_date(target_date)
        if not sensor_summary:
            logger.info(f"No sensor data found for '{self.plant['plant_name']}' on {target_date}. Cannot perform analysis.")
            return

        last_analysis = self.get_last_analysis(target_date)
        
        # --- 新しい状態を計算 ---
        new_growth_period, new_log = self._determine_growth_period(sensor_summary, last_analysis)
        new_survival_status = self._determine_survival_limits(target_date, sensor_summary)
        new_watering_advice = self._determine_watering_advice(new_growth_period)

        # --- DBに保存 ---
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT INTO daily_plant_analysis (managed_plant_id, analysis_date, daily_temp_max, daily_temp_min, growth_period, survival_limit_status, watering_advice, analysis_log)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(managed_plant_id, analysis_date) DO UPDATE SET
            daily_temp_max = excluded.daily_temp_max,
            daily_temp_min = excluded.daily_temp_min,
            growth_period = excluded.growth_period,
            survival_limit_status = excluded.survival_limit_status,
            watering_advice = excluded.watering_advice,
            analysis_log = excluded.analysis_log
        """, (
            self.plant_id, target_date, sensor_summary['daily_temp_max'], sensor_summary['daily_temp_min'],
            new_growth_period, new_survival_status, new_watering_advice, json.dumps(new_log)
        ))
        self.conn.commit()
        logger.info(f"Analysis for '{self.plant['plant_name']}' on {target_date} completed. Growth Period: {new_growth_period}")


    def _determine_growth_period(self, sensor_summary, last_analysis):
        """Growth Periodsの判定ロジック"""
        t = self.thresholds
        max_t, min_t = sensor_summary['daily_temp_max'], sensor_summary['daily_temp_min']
        
        last_log = json.loads(last_analysis['analysis_log']) if last_analysis and last_analysis['analysis_log'] else {}
        new_log = {
            "fast_growth_streak": 0, "slow_growth_streak": 0,
            "hot_dormancy_streak": 0, "cold_dormancy_streak": 0
        }
        
        # --- 各状態の条件判定 ---
        conditions = {
            'fast_growth': t['growing_fast_temp_low'] <= max_t <= t['growing_fast_temp_high'] and min_t > t['cold_dormancy_temp_high'],
            'slow_growth': t['growing_slow_temp_low'] <= max_t <= t['growing_slow_temp_high'] and min_t > t['cold_dormancy_temp_high'],
            'hot_dormancy': max_t > t['hot_dormancy_temp_low'],
            'cold_dormancy': min_t < t['cold_dormancy_temp_high'] # ユーザーの指定からタイポを修正
        }

        # --- 継続日数を更新 ---
        for state, met in conditions.items():
            if met:
                new_log[f"{state}_streak"] = last_log.get(f"{state}_streak", 0) + 1
        
        # --- 状態を確定 ---
        # 優先順位: 休眠 > 成長期
        if new_log['hot_dormancy_streak'] >= GROWTH_STATE_STREAK_DAYS['hot_dormancy']:
            return 'hot_dormancy', new_log
        if new_log['cold_dormancy_streak'] >= GROWTH_STATE_STREAK_DAYS['cold_dormancy']:
            return 'cold_dormancy', new_log
        if new_log['fast_growth_streak'] >= GROWTH_STATE_STREAK_DAYS['fast_growth']:
            return 'fast_growth', new_log
        if new_log['slow_growth_streak'] >= GROWTH_STATE_STREAK_DAYS['slow_growth']:
            return 'slow_growth', new_log
        
        # どの状態も確定しない場合は、前日の状態を維持
        if last_analysis:
            return last_analysis['growth_period'], new_log
        
        # 初回起動時は現在の温度で仮決定
        if conditions['hot_dormancy']: return 'hot_dormancy', new_log
        if conditions['cold_dormancy']: return 'cold_dormancy', new_log
        if conditions['fast_growth']: return 'fast_growth', new_log
        if conditions['slow_growth']: return 'slow_growth', new_log
        
        return 'unknown', new_log

    def _determine_survival_limits(self, target_date, sensor_summary):
        """Survival Temperature Limitsの判定ロジック"""
        t = self.thresholds
        
        # --- サンプリング回数での判定 (日次集計時に判定) ---
        start_of_day = datetime.combine(target_date, datetime.min.time())
        end_of_day = datetime.combine(target_date, datetime.max.time())
        
        high_triggers = self.conn.execute("SELECT COUNT(*) FROM sensor_data WHERE device_id = ? AND timestamp BETWEEN ? AND ? AND temperature > ?", (self.plant['assigned_switchbot_id'], start_of_day, end_of_day, t['lethal_temp_high'])).fetchone()[0]
        if high_triggers >= LETHAL_LIMIT_TRIGGER_COUNT:
            return 'lethal_high'
            
        low_triggers = self.conn.execute("SELECT COUNT(*) FROM sensor_data WHERE device_id = ? AND timestamp BETWEEN ? AND ? AND temperature < ?", (self.plant['assigned_switchbot_id'], start_of_day, end_of_day, t['lethal_temp_low'])).fetchone()[0]
        if low_triggers >= LETHAL_LIMIT_TRIGGER_COUNT:
            return 'lethal_low'

        return 'safe'
        
    def _determine_watering_advice(self, growth_period):
        """水やりタイミングの判定ロジック（簡易版）"""
        if growth_period == 'fast_growth':
            return self.thresholds.get('watering_growing', 'Check soil moisture regularly.')
        elif growth_period == 'slow_growth':
            return self.thresholds.get('watering_slow_growing', 'Water when soil is dry.')
        elif growth_period == 'hot_dormancy':
            return self.thresholds.get('watering_hot_dormancy', 'Reduce watering frequency.')
        elif growth_period == 'cold_dormancy':
            return self.thresholds.get('watering_cold_dormancy', 'Water sparingly, if at all.')
        return 'N/A'
