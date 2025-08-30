# blueprints/dashboard/routes.py

from flask import Blueprint, render_template, request, jsonify, Response
from datetime import date
import json
from queue import Queue
import device_manager as dm
from functools import wraps

# Blueprintオブジェクトを作成
dashboard_bp = Blueprint('dashboard', __name__, template_folder='../../templates', static_folder='../../static')

# Server-Sent Events用のキュー
sse_queue = Queue()

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
        devices_data = dm.get_all_devices()
    else:
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
    
    # ▼▼▼ 24Hグラフのデータ取得ロジックを修正 ▼▼▼
    if period == '24h':
        # 24Hの場合は、選択された日付の00:00から23:59までのデータを取得
        query = "SELECT timestamp, temperature, humidity FROM sensor_data WHERE device_id = ? AND date(timestamp) = ? ORDER BY timestamp ASC"
        history = conn.execute(query, (device_id, end_date_str)).fetchall()
    else:
        # 他期間の場合は、選択された日付の終わりを基準にした期間で取得
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
        while True:
            data = sse_queue.get()
            yield f"data: {json.dumps(data)}\n\n"
    return Response(event_stream(), mimetype='text/event-stream')
