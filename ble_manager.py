# plant_dashboard/ble_manager.py

import asyncio
import logging
import struct
from pathlib import Path
from datetime import datetime
from functools import wraps
from bleak import BleakClient, BleakScanner
from bleak.exc import BleakError

import config

# --- UUID定義 ---
PLANT_SERVICE_UUID = config.TARGET_SERVICE_UUID
COMMAND_CHAR_UUID = "6a3b2c1d-4e5f-6a7b-8c9d-e0f123456791"
RESPONSE_CHAR_UUID = "6a3b2c1d-4e5f-6a7b-8c9d-e0f123456792"
SWITCHBOT_LEGACY_METER_UUID = "cba20d00-224d-11e6-9fb8-0002a5d5c51b"
SWITCHBOT_COMMON_SERVICE_UUID = "0000fd3d-0000-1000-8000-00805f9b34fb"

# --- コマンド定義 ---
CMD_GET_SENSOR_DATA = 0x01
CMD_SET_WATERING_THRESHOLDS = 0x02

# Ensure log directory exists
config.LOG_FILE_PATH = "/var/log/plant_dashboard/bluetooth_manager.log"
#config.DEBUG = True

log_dir = Path(config.LOG_FILE_PATH).parent
log_dir.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=config.LOG_LEVEL,
    format='%(asctime)s - [Ble_Manager] - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(config.LOG_FILE_PATH),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


def retry_on_failure(max_attempts=None, delay=None, exceptions=(BleakError, asyncio.TimeoutError)):
    """
    BLE操作の失敗時に自動リトライを行うデコレーター

    Args:
        max_attempts: リトライの最大試行回数（デフォルト: config.BLE_OPERATION_RETRY_ATTEMPTS）
        delay: リトライ間の待機時間（秒）（デフォルト: config.BLE_OPERATION_RETRY_DELAY）
        exceptions: リトライ対象の例外のタプル
    """
    if max_attempts is None:
        max_attempts = config.BLE_OPERATION_RETRY_ATTEMPTS
    if delay is None:
        delay = config.BLE_OPERATION_RETRY_DELAY

    def decorator(func):
        @wraps(func)
        async def wrapper(self, *args, **kwargs):
            last_exception = None
            for attempt in range(max_attempts):
                try:
                    result = await func(self, *args, **kwargs)
                    if attempt > 0:
                        logger.info(f"[{self.device_id}] 操作が {attempt + 1} 回目の試行で成功しました")
                    return result
                except exceptions as e:
                    last_exception = e
                    if attempt < max_attempts - 1:
                        logger.warning(
                            f"[{self.device_id}] {func.__name__} が失敗しました "
                            f"(試行 {attempt + 1}/{max_attempts}): {e}. "
                            f"{delay}秒後にリトライします..."
                        )
                        await asyncio.sleep(delay)
                    else:
                        logger.error(
                            f"[{self.device_id}] {func.__name__} が {max_attempts} 回の試行後も失敗しました: {e}"
                        )
            return None
        return wrapper
    return decorator

def _parse_tm_data_t(data, offset):
    """tm_data_t構造体をパース (36バイト)"""
    tm_format = "<9i"  # 9個のint (tm_sec, tm_min, tm_hour, tm_mday, tm_mon, tm_year, tm_wday, tm_yday, tm_isdst)
    tm_size = struct.calcsize(tm_format)
    tm_values = struct.unpack_from(tm_format, data, offset)

    tm_dict = {
        'tm_sec': tm_values[0],
        'tm_min': tm_values[1],
        'tm_hour': tm_values[2],
        'tm_mday': tm_values[3],
        'tm_mon': tm_values[4],
        'tm_year': tm_values[5],
        'tm_wday': tm_values[6],
        'tm_yday': tm_values[7],
        'tm_isdst': tm_values[8],
    }

    return tm_dict, offset + tm_size


def _parse_sensor_data_v2(payload, device_id):
    """
    data_version 2 のセンサーデータをパースする (PlantMonitor_30用)

    Args:
        payload: 79または84バイトのペイロードデータ
        device_id: ログ出力用のデバイスID

    Returns:
        dict: センサーデータ辞書

    Raises:
        struct.error: データ解析エラー
    """
    # data_version (1バイト) + struct tm (36バイト) + センサーデータ
    # 実デバイスから: 84バイト (79バイト + 5バイトパディング?)

    if len(payload) < 70:
        raise struct.error(f"ペイロードが短すぎます: {len(payload)} バイト (期待: 79以上)")

    # デバッグ: ペイロード全体を16進数で出力
    logger.debug(f"[{device_id}] ペイロード長: {len(payload)} バイト")
    logger.debug(f"[{device_id}] ペイロード(hex): {payload[:84].hex() if len(payload) >= 84 else payload.hex()}")

    # バイナリダンプ表示
    print("📄 バイナリダンプ:")
    for i in range(0, len(payload), 16):
        hex_part = ' '.join(f'{b:02x}' for b in payload[i:i+16])
        ascii_part = ''.join(chr(b) if 32 <= b < 127 else '.' for b in payload[i:i+16])
        print(f"   {i:04x}: {hex_part:<48} {ascii_part}")
    print()
    
    offset = 0
    # data_version (uint8_t) - 1バイト
    data_version = struct.unpack_from("<B", payload, offset)[0]
    print(f"   offset {hex(offset)}: data_version = {data_version}")
    offset += 1

    # 構造体アライメントのため3バイトのパディングがある
    offset += 3

    # datetime (tm_data_t - 36バイト = 9 x 4バイトint)
    datetime_dict, offset = _parse_tm_data_t(payload, offset)
    print(f"   offset after tm_data_t: {hex(offset)}")

    # センサーデータ (4 floats = 16バイト)
    lux, temperature, humidity, soil_moisture = struct.unpack_from("<4f", payload, offset)
    print(f"   offset {hex(offset)}: lux={lux}, temp={temperature}, hum={humidity}, soil_moist={soil_moisture}")
    offset += 16

    sensor_error = struct.unpack_from("<B", payload, offset)[0]
    print(f"   offset {hex(offset)}: sensor_error = {sensor_error}")
    offset += 4 # センサーエラーの後に3バイトのパディングがある

    # 土壌温度 (2 floats = 8バイト)
    soil_temperature1, soil_temperature2 = struct.unpack_from("<2f", payload, offset)
    print(f"   offset {hex(offset)}: soil_temp1={soil_temperature1}, soil_temp2={soil_temperature2}")
    offset += 8  # 2 floats (8バイト) + 3バイトパディング

    # FDC1004静電容量データ (4 floats = 16バイト)
    fdc1004_format = f"<{config.FDC1004_CHANNEL_COUNT}f"
    soil_moisture_capacitance = struct.unpack_from(fdc1004_format, payload, offset)
    print(f"   offset {hex(offset)}: capacitance={soil_moisture_capacitance}")
    offset += 4 * config.FDC1004_CHANNEL_COUNT

    print(f"   final offset: {hex(offset)} / {len(payload)}")
    # datetimeオブジェクト作成
    try:
        dt = datetime(datetime_dict['tm_year'] + 1900, datetime_dict['tm_mon'] + 1, datetime_dict['tm_mday'], datetime_dict['tm_hour'], datetime_dict['tm_min'], datetime_dict['tm_sec'])
        dt_str = dt.strftime("%Y-%m-%d %H:%M:%S")
    except (ValueError, OverflowError) as e:
        logger.warning(f"[{device_id}] 無効な日時データ: {e}. デフォルト値を使用します")
        dt_str = "1970-01-01 00:00:00"

    logger.info(f"[{device_id}] Parsed datetime: {dt_str}")

    sensor_data = {
        'data_version': data_version,
        'datetime': dt_str,
        'light_lux': lux,
        'temperature': temperature,
        'humidity': humidity,
        'soil_moisture': soil_moisture,
        'sensor_error': False,
        'soil_temperature1': soil_temperature1,
        'soil_temperature2': soil_temperature2,
        'capacitance_ch1': soil_moisture_capacitance[0],
        'capacitance_ch2': soil_moisture_capacitance[1],
        'capacitance_ch3': soil_moisture_capacitance[2],
        'capacitance_ch4': soil_moisture_capacitance[3],
        'battery_level': None
    }

    logger.info(
        f"[{device_id}] v2データ解析完了: "
        f"temp={temperature:.1f}°C, humidity={humidity:.1f}%, "
        f"soil_temp1={soil_temperature1:.1f}°C, soil_temp2={soil_temperature2:.1f}°C, "
        f"cap=[{soil_moisture_capacitance[0]:.1f}, {soil_moisture_capacitance[1]:.1f}, {soil_moisture_capacitance[2]:.1f}, {soil_moisture_capacitance[3]:.1f}]pF"
    )

    return sensor_data

class PlantDeviceBLE:
    """
    プラントモニターデバイスとのBLE通信を管理するクラス。
    """
    def __init__(self, mac_address, device_id):
        self.mac_address = mac_address
        self.device_id = device_id
        self.client = BleakClient(mac_address)
        self.is_connected = False
        self.sequence_num = 0

    async def connect(self):
        """デバイスへの接続を試みる"""
        logger.info(f"[{self.device_id}] {self.mac_address} への接続を試みています...")
        try:
            device = await BleakScanner.find_device_by_address(
                self.mac_address,
                timeout=config.BLE_SCAN_TIMEOUT
            )
            if device is None:
                logger.error(
                    f"[{self.device_id}] スキャン中にアドレス {self.mac_address} のデバイスが見つかりませんでした "
                    f"(タイムアウト: {config.BLE_SCAN_TIMEOUT}秒)"
                )
                self.is_connected = False
                return False

            logger.info(f"[{self.device_id}] デバイスが見つかりました。接続を開始します。")
            await self.client.connect(timeout=config.BLE_CONNECT_TIMEOUT)
            self.is_connected = self.client.is_connected
            if self.is_connected:
                logger.info(f"[{self.device_id}] 接続に成功しました。")
            else:
                logger.warning(f"[{self.device_id}] 接続の試行に失敗しました。")
            return self.is_connected
        except (BleakError, asyncio.TimeoutError) as e:
            logger.error(
                f"[{self.device_id}] 接続に失敗しました "
                f"(タイムアウト: {config.BLE_CONNECT_TIMEOUT}秒): {e}"
            )
            self.is_connected = False
            return False

    async def disconnect(self):
        """デバイスから切断する"""
        if self.client.is_connected:
            try:
                await self.client.disconnect()
                logger.info(f"[{self.device_id}] Disconnected.")
            except BleakError as e:
                logger.error(f"[{self.device_id}] Error during disconnection: {e}")
        self.is_connected = False

    async def ensure_connection(self):
        """接続状態を確認し、切断されていれば再接続を試みる"""
        if self.client.is_connected:
            return True
        logger.info(f"[{self.device_id}] Connection lost. Attempting to reconnect...")
        self.is_connected = False
        for attempt in range(config.RECONNECT_ATTEMPTS):
            delay = config.RECONNECT_DELAY_BASE ** attempt
            logger.info(f"[{self.device_id}] Reconnect attempt {attempt + 1}/{config.RECONNECT_ATTEMPTS} in {delay:.1f}s...")
            await asyncio.sleep(delay)
            if await self.connect():
                return True
        logger.error(f"[{self.device_id}] Failed to reconnect after {config.RECONNECT_ATTEMPTS} attempts.")
        return False
    
    @retry_on_failure()
    async def set_watering_thresholds(self, dry_threshold_mv, wet_threshold_mv):
        """
        水やり閾値をデバイスに書き込みます。
        リトライ機能とタイムアウト設定を含む。
        """
        if not await self.ensure_connection():
            raise BleakError(f"デバイス {self.device_id} への接続を確立できませんでした")

        notification_received = asyncio.Event()
        success = False

        def notification_handler(sender: int, data: bytearray):
            nonlocal success
            logger.debug(f"[{self.device_id}] 書き込み応答を受信 from {sender}: {data.hex()}")
            if len(data) >= 3:
                resp_id, status_code, resp_seq = struct.unpack('<BBB', data[:3])
                if resp_id == CMD_SET_WATERING_THRESHOLDS and status_code == 0 and resp_seq == self.sequence_num:
                    success = True
                    logger.info(f"[{self.device_id}] 閾値設定の確認応答を受信しました")
            notification_received.set()

        try:
            await self.client.start_notify(RESPONSE_CHAR_UUID, notification_handler)

            self.sequence_num = (self.sequence_num + 1) % 256
            payload = struct.pack('<HH', int(dry_threshold_mv), int(wet_threshold_mv))
            command_packet = struct.pack('<BBH', CMD_SET_WATERING_THRESHOLDS, self.sequence_num, len(payload)) + payload

            logger.info(
                f"[{self.device_id}] 水やり閾値を {COMMAND_CHAR_UUID} へ書き込み中: "
                f"Dry={dry_threshold_mv}mV, Wet={wet_threshold_mv}mV"
            )
            await self.client.write_gatt_char(COMMAND_CHAR_UUID, command_packet)

            logger.debug(
                f"[{self.device_id}] 書き込み確認を待機中 "
                f"(タイムアウト: {config.BLE_OPERATION_TIMEOUT}秒)..."
            )
            await asyncio.wait_for(notification_received.wait(), timeout=config.BLE_OPERATION_TIMEOUT)

            if not success:
                raise BleakError("閾値設定の確認応答が正しく受信されませんでした")

            return True

        except asyncio.TimeoutError:
            logger.error(
                f"[{self.device_id}] 書き込み応答の待機中にタイムアウトしました "
                f"(タイムアウト: {config.BLE_OPERATION_TIMEOUT}秒)"
            )
            self.is_connected = False
            raise
        except BleakError as e:
            logger.error(f"[{self.device_id}] 閾値書き込み中にBLEエラーが発生: {e}")
            self.is_connected = False
            raise
        finally:
            if self.client.is_connected:
                await self.client.stop_notify(RESPONSE_CHAR_UUID)

    @retry_on_failure()
    async def get_sensor_data(self):
        """
        コマンドを書き込み、別のキャラクタリスティックからの通知でレスポンスを受け取る。
        リトライ機能とタイムアウト設定を含む。
        """
        if not await self.ensure_connection():
            raise BleakError(f"デバイス {self.device_id} への接続を確立できませんでした")

        notification_received = asyncio.Event()
        received_data = None

        def notification_handler(sender: int, data: bytearray):
            nonlocal received_data
            logger.debug(f"[{self.device_id}] Notification received from handle {sender}: {data.hex()}")
            received_data = data
            notification_received.set()

        try:
            logger.debug(f"[{self.device_id}] {RESPONSE_CHAR_UUID} で通知を開始します")
            await self.client.start_notify(RESPONSE_CHAR_UUID, notification_handler)

            self.sequence_num = (self.sequence_num + 1) % 256
            command_packet = struct.pack('<BBH', CMD_GET_SENSOR_DATA, self.sequence_num, 0)

            logger.debug(f"[{self.device_id}] {COMMAND_CHAR_UUID} へコマンドを送信: {command_packet.hex()}")
            await self.client.write_gatt_char(COMMAND_CHAR_UUID, command_packet)

            logger.debug(
                f"[{self.device_id}] 通知を待機中 "
                f"(タイムアウト: {config.BLE_OPERATION_TIMEOUT}秒)..."
            )
            await asyncio.wait_for(notification_received.wait(), timeout=config.BLE_OPERATION_TIMEOUT)

            if received_data is None:
                logger.warning(f"[{self.device_id}] 通知イベントがセットされましたが、データが受信されませんでした")
                raise BleakError("通知データが受信されませんでした")

            if len(received_data) < 5:
                logger.warning(f"[{self.device_id}] レスポンスヘッダーが短すぎます: {len(received_data)} バイト")
                raise BleakError(f"レスポンスヘッダーが短すぎます: {len(received_data)} バイト")

            resp_id, status_code, resp_seq, data_len = struct.unpack('<BBBH', received_data[:5])

            logger.debug(f"[{self.device_id}] 解析されたヘッダー: ID={resp_id}, Status={status_code}, Seq={resp_seq}, Len={data_len}")

            if resp_seq != self.sequence_num:
                logger.warning(f"[{self.device_id}] シーケンス番号の不一致。期待値: {self.sequence_num}, 受信: {resp_seq}")

            payload = received_data[5:]
            if len(payload) != data_len:
                logger.error(f"[{self.device_id}] ペイロード長の不一致。ヘッダー: {data_len}, 実際: {len(payload)}")
                raise BleakError(f"ペイロード長の不一致: 期待 {data_len}, 実際 {len(payload)}")

            # v1デバイス処理 (既存コード - 変更なし)
            if data_len == 56:
                unpacked_data = struct.unpack('<9i4f?3x', payload)

                tm_sec, tm_min, tm_hour, tm_mday, tm_mon, tm_year, tm_wday, tm_yday, tm_isdst, \
                lux, temp, humidity, soil, error = unpacked_data

                dt = datetime(tm_year + 1900, tm_mon + 1, tm_mday, tm_hour, tm_min, tm_sec)
                dt_str = dt.strftime("%Y-%m-%d %H:%M:%S")

                sensor_data = {
                    'datetime': dt_str, 'light_lux': lux, 'temperature': temp,
                    'humidity': humidity, 'soil_moisture': soil, 'sensor_error': error,
                    'battery_level': None
                }

                logger.info(f"[{self.device_id}] v1センサーデータの解析に成功: {sensor_data}")
                return sensor_data

            # v2デバイス処理 (PlantMonitor_30用 - 新規追加)
            elif data_len > 70:
                logger.info(f"[{self.device_id}] data_version 2 形式のデータを検出しました ({data_len}バイト)")
                try:
                    sensor_data = _parse_sensor_data_v2(payload, self.device_id)
                    logger.info(f"[{self.device_id}] v2センサーデータの解析に成功")
                    return sensor_data
                except struct.error as e:
                    logger.error(f"[{self.device_id}] v2データの解析に失敗: {e}")
                    raise BleakError(f"v2データ解析エラー: {e}")

            else:
                logger.error(f"[{self.device_id}] サポートされていないペイロード長: {data_len}")
                raise BleakError(f"サポートされていないペイロード長: {data_len}")

        except asyncio.TimeoutError as e:
            logger.error(
                f"[{self.device_id}] 通知の待機中にタイムアウトしました "
                f"(タイムアウト: {config.BLE_OPERATION_TIMEOUT}秒)"
            )
            self.is_connected = False
            raise
        except BleakError as e:
            logger.error(f"[{self.device_id}] BLE通信に失敗しました: {e}")
            self.is_connected = False
            raise
        except struct.error as e:
            logger.error(f"[{self.device_id}] レスポンスデータの解析に失敗: {e}. ペイロード: {payload.hex() if 'payload' in locals() else 'N/A'}")
            raise BleakError(f"データ解析エラー: {e}")
        except Exception as e:
            logger.error(f"[{self.device_id}] get_sensor_data で予期しないエラーが発生: {e}", exc_info=True)
            self.is_connected = False
            raise
        finally:
            logger.debug(f"[{self.device_id}] {RESPONSE_CHAR_UUID} の通知を停止します")
            try:
                if self.client.is_connected:
                    await self.client.stop_notify(RESPONSE_CHAR_UUID)
            except Exception as e:
                logger.warning(f"[{self.device_id}] 通知の停止に失敗しました: {e}")


def _parse_switchbot_adv_data(address, adv_data):
    """SwitchBotのAdvertisingデータを解析する内部ヘルパー関数"""
    if SWITCHBOT_COMMON_SERVICE_UUID in adv_data.service_data:
        service_data = adv_data.service_data[SWITCHBOT_COMMON_SERVICE_UUID]
        model = service_data[0] & 0b01111111
        
        if model == 0x69: # SwitchBot Meter Plus
            battery = service_data[2] & 0b01111111
            temperature = (service_data[3] & 0b00001111) / 10.0 + (service_data[4] & 0b01111111)
            if not (service_data[4] & 0b10000000):
                temperature = -temperature
            humidity = service_data[5] & 0b01111111
            return {'type': 'switchbot_meter_plus', 'data': {'temperature': temperature, 'humidity': humidity, 'battery_level': battery}}
        if model == 0x54: # SwitchBot Meter
            logger.debug(f"Address {address}:")
            logger.debug(f"SwitchBot Meter detected.")
            logger.debug(f"service_data: {service_data[0:].hex()}")
            battery = service_data[2] & 0b01111111
            temperature = (service_data[3] & 0b00001111) / 10.0 + (service_data[4] & 0b01111111)
            if not (service_data[4] & 0b10000000):
                temperature = -temperature
            humidity = service_data[5] & 0b01111111
            logger.debug(f"Parsed Temperature: {temperature}, Humidity: {humidity}, Battery: {battery}")
            return {'type': 'switchbot_meter', 'data': {'temperature': temperature, 'humidity': humidity, 'battery_level': battery}}
        if model == 0x25: # SwitchBot Mini Hub
            logger.info(f"Address {address}:")
            logger.info(f"SwitchBot Mini Hub detected. No sensor data available.")
            return None
        elif model == 0x63: # SwitchBot CO2 Meter
            battery = service_data[2] & 0b01111111
            temperature = (service_data[5] & 0b01111111) + (service_data[4] / 10.0)
            humidity = service_data[6] & 0b01111111
            co2 = int.from_bytes(service_data[7:9], 'little')
            return {'type': 'switchbot_co2_meter', 'data': {'temperature': temperature, 'humidity': humidity, 'co2': co2, 'battery_level': battery}}
        else:
            logger.info(f"Address {address}:")
            logger.info(f"Unknown SwitchBot model: {hex(model)}")
            logger.info(f"Service data: {service_data.hex()}") 
            logger.info(f"Advertisement data: {adv_data}")

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

async def scan_devices():
    """周辺のBLEデバイスをスキャンして結果を返す"""
    logger.info("Scanning for devices...")
    found_devices = []
    try:
        devices = await BleakScanner.discover(timeout=10.0, return_adv=True)
        for address, (device, adv_data) in devices.items():
            # AdvertisementData.rssi を使用 (BLEDevice.rssi は非推奨)
            rssi = adv_data.rssi
            device_name = device.name or ''

            logger.debug(f"Discovered device: {device_name} ({device.address}), RSSI: {rssi} dBm, UUIDs: {adv_data.service_uuids}")

            # PlantMonitor_xx_yyyy 形式のデバイス名をチェック
            if device_name.startswith('PlantMonitor_'):
                # デバイス名が一致する場合は、UUIDの有無に関わらず追加
                if PLANT_SERVICE_UUID in adv_data.service_uuids:
                    logger.info(f"Found PlantMonitor device with UUID: {device_name} at {device.address}")
                else:
                    logger.info(f"Found PlantMonitor device (no UUID advertised): {device_name} at {device.address}")
                found_devices.append({'address': device.address, 'name': device_name, 'type': 'plant_sensor', 'rssi': rssi})
                continue

            # PLANT_SERVICE_UUIDを持つデバイスをチェック（名前が一致しない場合）
            if PLANT_SERVICE_UUID in adv_data.service_uuids:
                logger.debug(f"Device has PLANT_SERVICE_UUID but name doesn't match PlantMonitor_ pattern: {device_name} at {device.address}")
                continue

            # SwitchBotデバイスをチェック
            switchbot_info = _parse_switchbot_adv_data(address, adv_data)
            if switchbot_info:
                device_name_map = {'switchbot_meter': 'SwitchBot Meter', 'switchbot_meter_plus': 'SwitchBot Meter Plus', 'switchbot_co2_meter': 'SwitchBot CO2 Meter'}
                found_devices.append({'address': device.address, 'name': device.name or device_name_map.get(switchbot_info['type'], 'Unknown SwitchBot'), 'type': switchbot_info['type'], 'rssi': rssi, 'data': switchbot_info.get('data')})
    except BleakError as e:
        logger.error(f"Error while scanning: {e}")
    return found_devices

async def get_switchbot_adv_data(mac_address: str):
    """指定されたMACアドレスのSwitchBotデバイスのアドバタイズデータをスキャンして取得する"""
    logger.debug(f"Scanning for 5 seconds to find {mac_address}...")
    try:
        devices = await BleakScanner.discover(timeout=5.0, return_adv=True)
        target_device_info = devices.get(mac_address.upper())
        if target_device_info:
            _device, adv_data = target_device_info
            if adv_data:
                switchbot_info = _parse_switchbot_adv_data(adv_data)
                if switchbot_info:
                    logger.debug(f"Successfully parsed data for {mac_address}")
                    return switchbot_info.get('data')
                else:
                    logger.warning(f"Found {mac_address}, but could not parse SwitchBot data from its advertisement.")
            else:
                logger.warning(f"Found {mac_address} but it had no advertisement data.")
        else:
            logger.warning(f"Device {mac_address} not found during the 5-second scan.")
        return None
    except BleakError as e:
        logger.error(f"A BleakError occurred while scanning for {mac_address}: {e}")
        return None
    except Exception as e:
        logger.error(f"An unexpected error occurred in get_switchbot_adv_data for {mac_address}: {e}")
        return None
