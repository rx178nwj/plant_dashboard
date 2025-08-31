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

# --- ルート定義 ---

@dashboard_bp.route('/')
@requires_auth
def dashboard():
    """メインダッシュボードページ"""
    selected_date_str = request.args.get('date', date.today().isoformat())
    today_str = date.today().isoformat()

    conn = dm.get_db_connection()
    switchbots = conn.execute("SELECT device_id, device_name FROM devices WHERE device_type LIKE 'switchbot_%'").fetchall()
    conn.close()

    if selected_date_str == today_str:
        # DBから最新のセンサーデータ付きでデバイスリストを取得
        devices_data = dm.get_devices_with_latest_sensor_data()
    else:
        # 過去の日付の場合は既存のロジックをそのまま使用
        devices_data = dm.get_devices_latest_on_date(selected_date_str)

    return render_template('dashboard.html', 
                           devices=devices_data, 
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
        period_map = {
            '7d': "'-7 days'",
            '30d': "'-1 month'",
            '1y': "'-1 year'"
        }
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
            # DBから直接最新データを取得
            devices_data_rows = dm.get_devices_with_latest_sensor_data()
            
            # DBのRowオブジェクトをJSONシリアライズ可能な辞書のリストに変換
            current_data_json = json.dumps([dict(row) for row in devices_data_rows], default=str)
            
            # データに変更があった場合のみクライアントに送信
            if current_data_json != last_data_json:
                yield f"data: {current_data_json}\n\n"
                last_data_json = current_data_json
            
            # 5秒待機してから再度チェック
            time.sleep(5)
            
    return Response(event_stream(), mimetype='text/event-stream')