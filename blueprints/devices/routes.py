# blueprints/devices/routes.py
from flask import Blueprint, render_template, jsonify, request, Response
import asyncio
import json
import logging
import device_manager as dm
from ble_manager import scan_devices as ble_scan
from blueprints.dashboard.routes import requires_auth
import config  # configをインポート

devices_bp = Blueprint('devices', __name__, template_folder='../../templates')
logger = logging.getLogger(__name__)


def determine_data_version(device_name):
    """
    デバイス名からdata_versionを判定する

    PlantMonitor_XX_YYYY形式のデバイス名から、XXの部分(ハードウェアバージョン)を取得し、
    30以上ならdata_version=2、それ以外はdata_version=1を返す

    Args:
        device_name: デバイス名 (例: "PlantMonitor_30_B9B2", "PlantMonitor_20_DA06")

    Returns:
        int: data_version (1 or 2)
    """
    if not device_name:
        return 1

    # PlantMonitor_XX_YYYY形式のデバイス名からハードウェアバージョンを抽出
    if device_name.startswith('PlantMonitor_'):
        parts = device_name.split('_')
        if len(parts) >= 2:
            try:
                hw_version = int(parts[1])
                # ハードウェアバージョン30以上はdata_version=2
                if hw_version >= 30:
                    return 2
            except ValueError:
                # 数値に変換できない場合はデフォルト値を返す
                logger.warning(f"デバイス名 '{device_name}' からハードウェアバージョンを抽出できませんでした")

    # デフォルトはdata_version=1
    return 1


@devices_bp.route('/devices')
@requires_auth
def devices():
    """デバイス管理ページを表示します。"""
    conn = dm.get_db_connection()
    registered_devices = conn.execute('SELECT * FROM devices ORDER BY device_name').fetchall()
    conn.close()
    return render_template('devices.html', registered_devices=registered_devices)


@devices_bp.route('/devices/profiles')
@requires_auth
def devices_profiles():
    """デバイスプロファイル管理ページを表示します。"""
    conn = dm.get_db_connection()
    registered_devices = conn.execute('SELECT * FROM devices ORDER BY device_type, device_name').fetchall()

    # 各デバイスに最新のセンサーデータと関連する植物情報を追加
    devices_with_data = []
    for device in registered_devices:
        device_dict = dict(device)

        # 最新のセンサーデータを取得
        sensor_data = conn.execute("""
            SELECT temperature, humidity, light_lux, soil_moisture, timestamp
            FROM sensor_data
            WHERE device_id = ?
            ORDER BY timestamp DESC
            LIMIT 1
        """, (device['device_id'],)).fetchone()

        device_dict['sensor_data'] = dict(sensor_data) if sensor_data else {}

        # plant sensorの場合、関連する植物情報を取得
        if device['device_type'] == 'plant_sensor':
            plant_info = conn.execute("""
                SELECT
                    mp.managed_plant_id,
                    mp.plant_name,
                    p.genus,
                    p.species,
                    COALESCE(mp.image_url, p.image_url) as display_image_url
                FROM managed_plants mp
                LEFT JOIN plants p ON mp.library_plant_id = p.plant_id
                WHERE mp.assigned_plant_sensor_id = ?
            """, (device['device_id'],)).fetchone()

            device_dict['assigned_plant'] = dict(plant_info) if plant_info else None
        else:
            device_dict['assigned_plant'] = None

        devices_with_data.append(device_dict)

    conn.close()
    return render_template('devices_profiles.html', registered_devices=devices_with_data)


@devices_bp.route('/devices/profile/<device_id>')
@requires_auth
def device_profile_detail(device_id):
    """デバイス詳細ページを表示します。"""
    conn = dm.get_db_connection()

    # デバイス情報を取得
    device = conn.execute('SELECT * FROM devices WHERE device_id = ?', (device_id,)).fetchone()

    if not device:
        conn.close()
        return "Device not found", 404

    device_dict = dict(device)

    # 最新のセンサーデータを取得
    sensor_data = conn.execute("""
        SELECT temperature, humidity, light_lux, soil_moisture, timestamp
        FROM sensor_data
        WHERE device_id = ?
        ORDER BY timestamp DESC
        LIMIT 1
    """, (device_id,)).fetchone()

    device_dict['sensor_data'] = dict(sensor_data) if sensor_data else {}

    # plant sensorの場合、関連する植物情報を取得
    if device['device_type'] == 'plant_sensor':
        plant_info = conn.execute("""
            SELECT
                mp.managed_plant_id,
                mp.plant_name,
                p.genus,
                p.species,
                COALESCE(mp.image_url, p.image_url) as display_image_url
            FROM managed_plants mp
            LEFT JOIN plants p ON mp.library_plant_id = p.plant_id
            WHERE mp.assigned_plant_sensor_id = ?
        """, (device_id,)).fetchone()

        device_dict['assigned_plant'] = dict(plant_info) if plant_info else None
    else:
        device_dict['assigned_plant'] = None

    conn.close()
    return render_template('device_detail.html', device=device_dict)


@devices_bp.route('/devices/threshold/<device_id>')
@requires_auth
def device_threshold_config(device_id):
    """デバイスの閾値設定ページを表示します。"""
    conn = dm.get_db_connection()

    # デバイス情報を取得
    device = conn.execute('SELECT * FROM devices WHERE device_id = ?', (device_id,)).fetchone()

    if not device:
        conn.close()
        return "Device not found", 404

    device_dict = dict(device)

    # plant sensorの場合、関連する植物情報を取得
    if device['device_type'] == 'plant_sensor':
        plant_info = conn.execute("""
            SELECT
                mp.managed_plant_id,
                mp.plant_name,
                mp.library_plant_id,
                p.genus,
                p.species,
                COALESCE(mp.image_url, p.image_url) as display_image_url
            FROM managed_plants mp
            LEFT JOIN plants p ON mp.library_plant_id = p.plant_id
            WHERE mp.assigned_plant_sensor_id = ?
        """, (device_id,)).fetchone()

        device_dict['assigned_plant'] = dict(plant_info) if plant_info else None
    else:
        device_dict['assigned_plant'] = None

    conn.close()
    return render_template('device_threshold.html', device=device_dict)


@devices_bp.route('/api/ble-scan', methods=['POST'])
@requires_auth
def api_ble_scan():
    """周辺のBLEデバイスをスキャンして結果を返します。"""
    try:
        # 非同期関数であるble_scanを実行し、結果を待つ
        devices = asyncio.run(ble_scan())
        return jsonify({'success': True, 'devices': devices})
    except Exception as e:
        logger.error(f"BLEスキャンに失敗しました: {e}", exc_info=True)
        return jsonify({'success': False, 'message': str(e)}), 500


@devices_bp.route('/api/add-device', methods=['POST'])
@requires_auth
def api_add_device():
    """新しいデバイスをデータベースに登録します。"""
    data = request.json
    try:
        conn = dm.get_db_connection()
        # device_typeを先頭に使用してユニークなIDを生成
        # MACアドレスの末尾6桁を追加
        device_type = data['device_type']
        mac_suffix = data['mac_address'].replace(':', '')[-6:].lower()
        device_id = f"{device_type}_{mac_suffix}"

        # デバイス名からdata_versionを自動判定
        device_name = data['device_name']
        data_version = determine_data_version(device_name)
        logger.info(f"デバイス '{device_name}' のdata_versionを {data_version} として登録します")

        conn.execute(
            "INSERT INTO devices (device_id, device_name, mac_address, device_type, data_version) VALUES (?, ?, ?, ?, ?)",
            (device_id, device_name, data['mac_address'], data['device_type'], data_version)
        )
        conn.commit()
        conn.close()
        dm.load_devices_from_db()  # メモリ上のデバイスリストを再読み込み
        return jsonify({'success': True, 'message': 'デバイスが正常に追加されました。'})
    except Exception as e:
        logger.error(f"デバイスの追加に失敗しました: {e}", exc_info=True)
        # データベースの一意性制約エラーなどを考慮
        return jsonify({'success': False, 'message': f'デバイスの追加に失敗しました: {e}'}), 500


@devices_bp.route('/api/device/<device_id>', methods=['PUT'])
@requires_auth
def api_update_device(device_id):
    """デバイス情報を更新します。"""
    data = request.json
    try:
        conn = dm.get_db_connection()
        # デバイスが存在するか確認
        device = conn.execute('SELECT * FROM devices WHERE device_id = ?', (device_id,)).fetchone()
        if not device:
            conn.close()
            return jsonify({'success': False, 'message': 'デバイスが見つかりません。'}), 404

        # デバイス名のみ更新可能とする（必要に応じて他のフィールドも追加可能）
        conn.execute(
            "UPDATE devices SET device_name = ? WHERE device_id = ?",
            (data.get('device_name'), device_id)
        )
        conn.commit()
        conn.close()
        dm.load_devices_from_db()  # メモリ上のデバイスリストを再読み込み
        return jsonify({'success': True, 'message': 'デバイス情報を更新しました。'})
    except Exception as e:
        logger.error(f"デバイスの更新に失敗しました: {e}", exc_info=True)
        return jsonify({'success': False, 'message': f'デバイスの更新に失敗しました: {e}'}), 500


@devices_bp.route('/api/device/<sensor_id>/write-watering-profile', methods=['POST'])
@requires_auth
def api_write_watering_profile(sensor_id):
    """デバイスに水やりプロファイルを書き込むためのコマンドを送信します。"""

    logger.info(f"Received request to write watering profile for sensor_id: {sensor_id}")

    data = request.json
    conn = dm.get_db_connection()
    # sensor_idは、このアプリケーションではdevice_idと同じものとして扱います
    device = conn.execute('SELECT device_id FROM devices WHERE device_id = ?', (sensor_id,)).fetchone()
    conn.close()

    if not device:
        response_data = json.dumps({'success': False, 'message': '指定されたデバイスが見つかりません。'})
        return Response(response_data, status=404, mimetype='application/json')

    try:
        command = {
            "command": "set_watering_thresholds",
            "device_id": device['device_id'],
            "payload": {
                "dry_threshold": data.get('dry_threshold'),
                "wet_threshold": data.get('wet_threshold')
            }
        }
        # configからパイプのパスを読み込む
        with open(config.COMMAND_PIPE_PATH, "a") as f:
            f.write(json.dumps(command) + "\n")

        logger.info(f"デバイス {sensor_id} への水やり設定書き込みコマンドをキューに追加しました。")
        response_data = json.dumps({'success': True, 'message': 'デバイスへの書き込みコマンドを受け付けました。'})
        return Response(response_data, status=200, mimetype='application/json')

    except Exception as e:
        logger.error(f"コマンドのデーモンへの送信に失敗: {e}", exc_info=True)
        response_data = json.dumps({'success': False, 'message': f'サーバー内部でエラーが発生しました: {e}'})
        return Response(response_data, status=500, mimetype='application/json')


@devices_bp.route('/api/device/<device_id>', methods=['DELETE'])
@requires_auth
def api_delete_device(device_id):
    """デバイスを削除します。"""
    try:
        conn = dm.get_db_connection()

        # デバイスが存在するか確認
        device = conn.execute('SELECT * FROM devices WHERE device_id = ?', (device_id,)).fetchone()
        if not device:
            conn.close()
            return jsonify({'success': False, 'message': 'デバイスが見つかりません。'}), 404

        # managed_plantsテーブルでこのデバイスを参照しているレコードをNULLに更新
        conn.execute('''
            UPDATE managed_plants
            SET assigned_plant_sensor_id = NULL
            WHERE assigned_plant_sensor_id = ?
        ''', (device_id,))

        conn.execute('''
            UPDATE managed_plants
            SET assigned_switchbot_id = NULL
            WHERE assigned_switchbot_id = ?
        ''', (device_id,))

        # センサーデータを削除
        conn.execute('DELETE FROM sensor_data WHERE device_id = ?', (device_id,))

        # デバイスを削除
        conn.execute('DELETE FROM devices WHERE device_id = ?', (device_id,))

        conn.commit()
        conn.close()

        # メモリ上のデバイスリストを再読み込み
        dm.load_devices_from_db()

        logger.info(f"デバイス {device_id} を削除しました。")
        return jsonify({'success': True, 'message': 'デバイスを削除しました。'})

    except Exception as e:
        logger.error(f"デバイスの削除に失敗しました: {e}", exc_info=True)
        return jsonify({'success': False, 'message': f'デバイスの削除に失敗しました: {e}'}), 500

