# blueprints/devices/routes.py
from flask import Blueprint, render_template, jsonify, request
import asyncio
import device_manager as dm
from ble_manager import scan_devices as ble_scan
from blueprints.dashboard.routes import requires_auth

devices_bp = Blueprint('devices', __name__, template_folder='../../templates', static_folder='../../static')

@devices_bp.route('/devices')
@requires_auth
def devices():
    """デバイス管理ページを表示します。"""
    conn = dm.get_db_connection()
    registered_devices = conn.execute('SELECT * FROM devices ORDER BY device_name').fetchall()
    conn.close()
    return render_template('devices.html', registered_devices=registered_devices)

@devices_bp.route('/api/ble-scan', methods=['POST'])
@requires_auth
def api_ble_scan():
    """周辺のBLEデバイスをスキャンして結果を返します。"""
    try:
        # 비동기 함수인 ble_scan을 실행하고 결과를 기다립니다.
        devices = asyncio.run(ble_scan())
        return jsonify({'success': True, 'devices': devices})
    except Exception as e:
        # logger.error(f"BLE scan failed: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

@devices_bp.route('/api/add-device', methods=['POST'])
@requires_auth
def api_add_device():
    """新しいデバイスをデータベースに登録します。"""
    data = request.json
    try:
        conn = dm.get_db_connection()
        # ユニークなIDを生成（MACアドレスの末尾6桁を使用）
        device_id = f"dev_{data['mac_address'].replace(':', '')[-6:].lower()}"
        conn.execute(
            "INSERT INTO devices (device_id, device_name, mac_address, device_type) VALUES (?, ?, ?, ?)",
            (device_id, data['device_name'], data['mac_address'], data['device_type'])
        )
        conn.commit()
        conn.close()
        dm.load_devices_from_db()  # メモリ上のデバイスリストを再読み込み
        return jsonify({'success': True, 'message': 'Device added successfully.'})
    except Exception as e:
        # logger.error(f"Failed to add device: {e}")
        # データベースの一意性制約エラーなどを考慮
        return jsonify({'success': False, 'message': f'Failed to add device: {e}'}), 500
