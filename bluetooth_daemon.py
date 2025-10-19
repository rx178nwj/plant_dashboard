# plant_dashboard/bluetooth_daemon.py
import asyncio
import logging
import json
from datetime import datetime
import os

import config
import device_manager as dm
from ble_manager import PlantDeviceBLE
from bleak import BleakScanner
from bleak.exc import BleakError
from database import get_db_connection

# データ連携用の一時ファイルパス
DATA_PIPE_PATH = "/tmp/plant_dashboard_pipe.jsonl"
# コマンド用パイプのパスをconfigから読み込む
COMMAND_PIPE_PATH = config.COMMAND_PIPE_PATH

logging.basicConfig(
    level=config.LOG_LEVEL,
    format='%(asctime)s - [BluetoothDaemon] - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(config.LOG_FILE_PATH),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


# --- ble_manager.pyから移動した関数群 ---

SWITCHBOT_LEGACY_METER_UUID = "cba20d00-224d-11e6-9fb8-0002a5d5c51b"
SWITCHBOT_COMMON_SERVICE_UUID = "0000fd3d-0000-1000-8000-00805f9b34fb"

def _parse_switchbot_adv_data(adv_data):
    """SwitchBotのAdvertisingデータを解析する内部ヘルパー関数"""
    if SWITCHBOT_COMMON_SERVICE_UUID in adv_data.service_data:
        service_data = adv_data.service_data[SWITCHBOT_COMMON_SERVICE_UUID]
        model = service_data[0] & 0b01111111
        battery = service_data[1] & 0b01111111
        if model == 0x69: # SwitchBot Meter Plus
            temperature = (service_data[3] & 0b00001111) / 10.0 + (service_data[4] & 0b01111111)
            if not (service_data[4] & 0b10000000):
                temperature = -temperature
            humidity = service_data[5] & 0b01111111
            return {'type': 'switchbot_meter_plus', 'data': {'temperature': temperature, 'humidity': humidity, 'battery_level': battery}}
        elif model == 0x63: # SwitchBot CO2 Meter
            temperature = (service_data[5] & 0b01111111) + (service_data[4] / 10.0)
            humidity = service_data[6] & 0b01111111
            co2 = int.from_bytes(service_data[7:9], 'little')
            return {'type': 'switchbot_co2_meter', 'data': {'temperature': temperature, 'humidity': humidity, 'co2': co2, 'battery_level': battery}}
    elif SWITCHBOT_LEGACY_METER_UUID in adv_data.service_data: # SwitchBot Meter (Legacy)
        service_data = adv_data.service_data[SWITCHBOT_LEGACY_METER_UUID]
        battery = service_data[2] & 0b01111111
        is_temp_above_freezing = service_data[4] & 0b10000000
        temp_val = service_data[4] & 0b01111111
        temperature = temp_val + (service_data[3] / 10.0)
        if not is_temp_above_freezing:
            temperature = -temperature
        humidity = service_data[5] & 0b01111111
        return {'type': 'switchbot_meter', 'data': {'temperature': temperature, 'humidity': humidity, 'battery_level': battery}}
    return None

async def get_switchbot_adv_data(mac_address: str):
    """指定されたMACアドレスのSwitchBotデバイスのアドバタイズデータをスキャンして取得する"""
    logger.debug(f"{mac_address} を見つけるために5秒間スキャンします...")
    try:
        devices = await BleakScanner.discover(timeout=5.0, return_adv=True)
        target_device_info = devices.get(mac_address.upper())
        if target_device_info:
            _device, adv_data = target_device_info
            if adv_data:
                switchbot_info = _parse_switchbot_adv_data(adv_data)
                if switchbot_info:
                    logger.debug(f"{mac_address} のデータを正常に解析しました")
                    return switchbot_info.get('data')
                else:
                    logger.warning(f"{mac_address} を見つけましたが、アドバタイズデータからSwitchBotのデータを解析できませんでした。")
            else:
                logger.warning(f"{mac_address} を見つけましたが、アドバタイズデータがありませんでした。")
        else:
            logger.warning(f"5秒間のスキャンでデバイス {mac_address} が見つかりませんでした。")
        return None
    except BleakError as e:
        logger.error(f"{mac_address} のスキャン中にBleakErrorが発生しました: {e}")
        return None
    except Exception as e:
        logger.error(f"get_switchbot_adv_data ({mac_address}) で予期せぬエラーが発生しました: {e}")
        return None

# --- 移動した関数の終わり ---


def get_devices_from_db():
    """DBからポーリング対象のデバイス情報を取得する"""
    conn = get_db_connection()
    devices = conn.execute('SELECT device_id, device_name, mac_address, device_type FROM devices').fetchall()
    conn.close()
    return [dict(row) for row in devices]

def write_to_pipe(data):
    """取得したデータを一時ファイルにJSON Lines形式で追記する"""
    try:
        with open(DATA_PIPE_PATH, "a") as f:
            f.write(json.dumps(data) + "\n")
    except Exception as e:
        logger.error(f"データパイプへの書き込みに失敗しました: {e}")

async def process_commands(plant_connections):
    """コマンドパイプを処理してBLE操作を実行する"""
    logger.debug("コマンドパイプ内のコマンドを確認しています...")
    
    if not os.path.exists(COMMAND_PIPE_PATH):
        return

    # ファイルをリネームしてアトミックに処理
    processing_path = COMMAND_PIPE_PATH + f".processing_{os.getpid()}"
    try:
        os.rename(COMMAND_PIPE_PATH, processing_path)
    except FileNotFoundError:
        return # 他のプロセスが先にリネームした場合

    with open(processing_path, "r") as f:
        for line in f:
            try:
                command_data = json.loads(line.strip())
                command = command_data.get("command")
                device_id = command_data.get("device_id")
                payload = command_data.get("payload")

                logger.info(f"コマンド '{command}' をデバイス {device_id} のために受信しました")

                if command == "set_watering_thresholds":
                    if device_id not in plant_connections:
                        logger.warning(f"{device_id} の有効な接続がないため、閾値を設定できません。接続を試みます。")
                        # データベースからこのデバイスのMACアドレスを再取得
                        conn = get_db_connection()
                        dev_info = conn.execute("SELECT mac_address FROM devices WHERE device_id = ?", (device_id,)).fetchone()
                        conn.close()
                        if dev_info:
                             plant_connections[device_id] = PlantDeviceBLE(dev_info['mac_address'], device_id)
                        else:
                             logger.error(f"コマンド実行のためにデバイス {device_id} がデータベースに見つかりません。")
                             continue
                    
                    ble_device = plant_connections[device_id]
                    dry_mv = payload.get('dry_threshold')
                    wet_mv = payload.get('wet_threshold')
                    
                    if dry_mv is not None and wet_mv is not None:
                        success = await ble_device.set_watering_thresholds(dry_mv, wet_mv)
                        if success:
                            logger.info(f"{device_id} に閾値を正常に送信しました。")
                        else:
                            logger.error(f"{device_id} への閾値の送信に失敗しました。")
                    else:
                        logger.error(f"set_watering_thresholds のペイロードが無効です: {payload}")

            except Exception as e:
                logger.error(f"コマンド処理中にエラーが発生しました: {line.strip()} - {e}")
    
    os.remove(processing_path)


async def main_loop():
    """Bluetoothデバイスのポーリングとコマンド処理を行うメインループ"""
    logger.info("Bluetoothデーモンループを開始します...")
    plant_sensor_connections = {}

    while True:
        # コマンド処理をループの最初に追加
        await process_commands(plant_sensor_connections)

        devices_to_poll = get_devices_from_db()
        
        if not devices_to_poll:
            logger.info("データベースに設定済みのデバイスがありません。待機します...")
            await asyncio.sleep(config.DATA_FETCH_INTERVAL)
            continue
        
        logger.info(f"{len(devices_to_poll)} 個のデバイスのデータ収集サイクルを開始します。")
        
        for device in devices_to_poll:
            dev_id = device.get('device_id')
            device_type = device.get('device_type')
            mac_address = device.get('mac_address')
            sensor_data = None
            
            logger.info(f"デバイスをポーリング中: {device.get('device_name')} ({dev_id})")

            try:
                if device_type == 'plant_sensor':
                    if dev_id not in plant_sensor_connections:
                        plant_sensor_connections[dev_id] = PlantDeviceBLE(mac_address, dev_id)
                    ble_device = plant_sensor_connections[dev_id]
                    sensor_data = await ble_device.get_sensor_data()
                        
                elif device_type and device_type.startswith('switchbot_'):
                    sensor_data = await get_switchbot_adv_data(mac_address)
                
                # 取得結果をpipeファイルに書き出す
                pipe_data = {
                    "device_id": dev_id,
                    "timestamp": datetime.now().isoformat(),
                    "data": sensor_data # データがなくてもNoneとして記録
                }
                write_to_pipe(pipe_data)

            except Exception as e:
                logger.error(f"{dev_id} のデータ収集中に未処理のエラーが発生しました: {e}", exc_info=True)
                # エラー情報もpipeに書き出す
                write_to_pipe({
                    "device_id": dev_id,
                    "timestamp": datetime.now().isoformat(),
                    "error": str(e)
                })
            
            await asyncio.sleep(2) # デバイス間のポーリングに短い遅延

        logger.info(f"データ収集サイクルが終了しました。{config.DATA_FETCH_INTERVAL} 秒間待機します。")
        await asyncio.sleep(config.DATA_FETCH_INTERVAL)

if __name__ == "__main__":
    try:
        # 起動時に一時ファイルが残っていれば削除
        if os.path.exists(DATA_PIPE_PATH):
            os.remove(DATA_PIPE_PATH)
        if os.path.exists(COMMAND_PIPE_PATH):
            os.remove(COMMAND_PIPE_PATH)
        asyncio.run(main_loop())
    except KeyboardInterrupt:
        logger.info("Bluetoothデーモンがユーザーによって停止されました。")
    except Exception as e:
        logger.critical(f"重大なエラーによりBluetoothデーモンが停止しました: {e}", exc_info=True)

