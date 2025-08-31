from flask import Blueprint, render_template, request, jsonify, Response
from datetime import date
import json
import time
import device_manager as dm
from functools import wraps

# Blueprintオブジェクトを作成
dashboard_bp = Blueprint('dashboard', __name__, template_folder='../../templates', static_folder='../../static')

# --- 認証デコレーター ---
from config import BASIC_AUTH_USERNAME, BASIC_AUTH_PASSWORD

def check_auth(username, password):
    return username == BASIC_AUTH_USERNAME and password == BASIC_AUTH_PASSWORD

def authenticate():
    return Response('Could not verify your access level for that URL.\nYou have to login with proper credentials', 401, {'WWW-Authenticate': 'Basic realm="Login Required"'})

def requires_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth or not check_auth(auth.username, auth.password):
            return authenticate()
        return f(*args, **kwargs)
    return decorated

# --- データ取得関数 ---
def get_plant_centric_data(selected_date_str):
    """
    管理されている植物を中心としたダッシュボード用のデータを集約して取得する。
    Soil Sensorが割り当てられている場合は、そのデータを優先的に使用する。
    """
    conn = dm.get_db_connection()
    
    managed_plants_rows = conn.execute("""
        SELECT
            mp.managed_plant_id, mp.plant_name, mp.library_plant_id,
            mp.assigned_plant_sensor_id, mp.assigned_switchbot_id,
            p.genus, p.species, p.image_url
        FROM managed_plants mp
        LEFT JOIN plants p ON mp.library_plant_id = p.plant_id
        ORDER BY mp.plant_name
    """).fetchall()

    dashboard_data = []
    for row in managed_plants_rows:
        plant_data = dict(row)
        end_of_day_str = f"{selected_date_str} 23:59:59"

        # 分析結果を取得
        analysis = conn.execute("""
            SELECT growth_period, watering_advice, survival_limit_status
            FROM daily_plant_analysis
            WHERE managed_plant_id = ? AND analysis_date <= ?
            ORDER BY analysis_date DESC LIMIT 1
        """, (plant_data['managed_plant_id'], selected_date_str)).fetchone()
        plant_data['analysis'] = dict(analysis) if analysis else {}

        # センサーデータを取得
        plant_data['sensors'] = {}
        sensor_data = None

        # 土壌センサーが割り当てられている場合、それを最優先
        if plant_data['assigned_plant_sensor_id']:
            sensor_data = conn.execute("""
                SELECT s.temperature, s.humidity, s.light_lux, s.soil_moisture, d.battery_level, s.timestamp
                FROM sensor_data s JOIN devices d ON s.device_id = d.device_id
                WHERE s.device_id = ? AND s.timestamp <= ?
                ORDER BY s.timestamp DESC LIMIT 1
            """, (plant_data['assigned_plant_sensor_id'], end_of_day_str)).fetchone()
            plant_data['sensors']['source'] = 'soil_sensor'

        # 土壌センサーのデータがない、または割り当てられていない場合、環境センサーをフォールバックとして使用
        if not sensor_data and plant_data['assigned_switchbot_id']:
            sensor_data = conn.execute("""
                SELECT s.temperature, s.humidity, d.battery_level, s.timestamp
                FROM sensor_data s JOIN devices d ON s.device_id = d.device_id
                WHERE s.device_id = ? AND s.timestamp <= ?
                ORDER BY s.timestamp DESC LIMIT 1
            """, (plant_data['assigned_switchbot_id'], end_of_day_str)).fetchone()
            plant_data['sensors']['source'] = 'environment_sensor'
        
        plant_data['sensors']['primary'] = dict(sensor_data) if sensor_data else {}
        
        dashboard_data.append(plant_data)
        
    conn.close()
    return dashboard_data

# --- ルート定義 ---

@dashboard_bp.route('/')
@requires_auth
def dashboard():
    """メインダッシュボードページ"""
    selected_date_str = request.args.get('date', date.today().isoformat())
    today_str = date.today().isoformat()

    plants_data = get_plant_centric_data(selected_date_str)

    conn = dm.get_db_connection()
    switchbots = conn.execute("SELECT device_id, device_name FROM devices WHERE device_type LIKE 'switchbot_%'").fetchall()
    conn.close()

    return render_template('dashboard.html', 
                           plants_data=plants_data, 
                           switchbots_for_chart=switchbots,
                           active_page='dashboard',
                           selected_date=selected_date_str,
                           is_today=(selected_date_str == today_str))

@dashboard_bp.route('/api/history/<device_id>')
@requires_auth
def api_history(device_id):
    """デバイスの履歴データを返すAPI"""
    period = request.args.get('period', '24h')
    end_date_str = request.args.get('date', date.today().isoformat())
    
    conn = dm.get_db_connection()
    
    if period == '24h':
        query = "SELECT timestamp, temperature, humidity FROM sensor_data WHERE device_id = ? AND date(timestamp) = ? ORDER BY timestamp ASC"
        history = conn.execute(query, (device_id, end_date_str)).fetchall()
    else:
        period_map = { '7d': "'-7 days'", '30d': "'-1 month'", '1y': "'-1 year'" }
        time_modifier = period_map.get(period, "'-7 days'")
        end_datetime = f"{end_date_str} 23:59:59"
        query = f"SELECT timestamp, temperature, humidity FROM sensor_data WHERE device_id = ? AND timestamp BETWEEN datetime(?, {time_modifier}) AND ? ORDER BY timestamp ASC"
        history = conn.execute(query, (device_id, end_datetime, end_datetime)).fetchall()
        
    conn.close()
    return jsonify([dict(row) for row in history])

@dashboard_bp.route('/stream')
@requires_auth
def stream():
    """リアルタイムデータ配信用エンドポイント"""
    def event_stream():
        last_data_json = ""
        while True:
            today_str = date.today().isoformat()
            plants_data = get_plant_centric_data(today_str)
            
            current_data_json = json.dumps(plants_data, default=str)
            
            if current_data_json != last_data_json:
                yield f"data: {current_data_json}\n\n"
                last_data_json = current_data_json
            
            time.sleep(5)
            
    return Response(event_stream(), mimetype='text/event-stream')

