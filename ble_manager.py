# plant_dashboard/ble_manager.py

import asyncio
import logging
import struct
from datetime import datetime
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

logger = logging.getLogger(__name__)

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
        logger.info(f"[{self.device_id}] Attempting to connect to {self.mac_address}...")
        try:
            device = await BleakScanner.find_device_by_address(self.mac_address, timeout=5.0)
            if device is None:
                logger.error(f"[{self.device_id}] Device with address {self.mac_address} was not found during scan.")
                self.is_connected = False
                return False
            
            logger.info(f"[{self.device_id}] Device found, proceeding with connection.")
            await self.client.connect(timeout=10.0)
            self.is_connected = self.client.is_connected
            if self.is_connected:
                logger.info(f"[{self.device_id}] Connection successful.")
            else:
                logger.warning(f"[{self.device_id}] Connection attempt failed.")
            return self.is_connected
        except (BleakError, asyncio.TimeoutError) as e:
            logger.error(f"[{self.device_id}] Failed to connect: {e}")
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
    
    async def set_watering_thresholds(self, dry_threshold_mv, wet_threshold_mv):
        """
        水やり閾値をデバイスに書き込みます。
        """
        if not await self.ensure_connection():
            return False

        notification_received = asyncio.Event()
        success = False

        def notification_handler(sender: int, data: bytearray):
            nonlocal success
            logger.debug(f"[{self.device_id}] Write Response from {sender}: {data.hex()}")
            if len(data) >= 3:
                resp_id, status_code, resp_seq = struct.unpack('<BBB', data[:3])
                if resp_id == CMD_SET_WATERING_THRESHOLDS and status_code == 0 and resp_seq == self.sequence_num:
                    success = True
                    logger.info(f"[{self.device_id}] Successfully received confirmation for setting thresholds.")
            notification_received.set()

        try:
            await self.client.start_notify(RESPONSE_CHAR_UUID, notification_handler)

            self.sequence_num = (self.sequence_num + 1) % 256
            payload = struct.pack('<HH', int(dry_threshold_mv), int(wet_threshold_mv))
            command_packet = struct.pack('<BBH', CMD_SET_WATERING_THRESHOLDS, self.sequence_num, len(payload)) + payload
            
            logger.info(f"[{self.device_id}] Writing watering thresholds to {COMMAND_CHAR_UUID}: {command_packet.hex()}")
            await self.client.write_gatt_char(COMMAND_CHAR_UUID, command_packet)
            
            logger.debug(f"[{self.device_id}] Waiting for write confirmation...")
            await asyncio.wait_for(notification_received.wait(), timeout=10.0)
            
            return success

        except asyncio.TimeoutError:
            logger.error(f"[{self.device_id}] Timed out waiting for write response.")
            return False
        except BleakError as e:
            logger.error(f"[{self.device_id}] BLE error while writing thresholds: {e}")
            self.is_connected = False
            return False
        finally:
            if self.client.is_connected:
                await self.client.stop_notify(RESPONSE_CHAR_UUID)

    async def get_sensor_data(self):
        """
        コマンドを書き込み、別のキャラクタリスティックからの通知でレスポンスを受け取る。
        """
        if not await self.ensure_connection():
            return None

        notification_received = asyncio.Event()
        received_data = None

        def notification_handler(sender: int, data: bytearray):
            nonlocal received_data
            logger.debug(f"[{self.device_id}] Notification received from handle {sender}: {data.hex()}")
            received_data = data
            notification_received.set()

        try:
            logger.debug(f"[{self.device_id}] Starting notifications on {RESPONSE_CHAR_UUID}")
            await self.client.start_notify(RESPONSE_CHAR_UUID, notification_handler)

            self.sequence_num = (self.sequence_num + 1) % 256
            command_packet = struct.pack('<BBH', CMD_GET_SENSOR_DATA, self.sequence_num, 0)
            
            logger.debug(f"[{self.device_id}] Writing command to {COMMAND_CHAR_UUID}: {command_packet.hex()}")
            await self.client.write_gatt_char(COMMAND_CHAR_UUID, command_packet)
            
            logger.debug(f"[{self.device_id}] Waiting for notification...")
            await asyncio.wait_for(notification_received.wait(), timeout=10.0)

            if received_data is None:
                logger.warning(f"[{self.device_id}] Notification event was set, but no data was received.")
                return None

            if len(received_data) < 5:
                logger.warning(f"[{self.device_id}] Response header is too short: {len(received_data)} bytes")
                return None
            
            resp_id, status_code, resp_seq, data_len = struct.unpack('<BBBH', received_data[:5])
            
            logger.debug(f"[{self.device_id}] Parsed header: ID={resp_id}, Status={status_code}, Seq={resp_seq}, Len={data_len}")

            if resp_seq != self.sequence_num:
                logger.warning(f"[{self.device_id}] Sequence number mismatch. Expected {self.sequence_num}, got {resp_seq}")

            payload = received_data[5:]
            if len(payload) != data_len:
                logger.error(f"[{self.device_id}] Payload length mismatch. Header says {data_len}, but got {len(payload)}")
                return None

            if data_len == 56:
                unpacked_data = struct.unpack('<9i4f?3x', payload)
                
                tm_sec, tm_min, tm_hour, tm_mday, tm_mon, tm_year, tm_wday, tm_yday, tm_isdst, \
                lux, temp, humidity, soil, error = unpacked_data

                dt = datetime(tm_year + 1900, tm_mon + 1, tm_mday, tm_hour, tm_min, tm_sec)
                dt_str = dt.strftime("%Y-%m-%d %H:%M:%S")

            else:
                logger.error(f"[{self.device_id}] Unsupported data length in payload: {data_len}.")
                return None

            sensor_data = {
                'datetime': dt_str, 'light_lux': lux, 'temperature': temp,
                'humidity': humidity, 'soil_moisture': soil, 'sensor_error': error,
                'battery_level': None
            }
            
            logger.info(f"[{self.device_id}] Successfully parsed data from notification: {sensor_data}")
            return sensor_data

        except asyncio.TimeoutError:
            logger.error(f"[{self.device_id}] Timed out waiting for notification.")
            return None
        except BleakError as e:
            logger.error(f"[{self.device_id}] BLE communication failed: {e}")
            self.is_connected = False
            return None
        except struct.error as e:
            logger.error(f"[{self.device_id}] Failed to unpack response data: {e}. Payload was {payload.hex() if 'payload' in locals() else 'N/A'}")
            return None
        except Exception as e:
            logger.error(f"[{self.device_id}] An unexpected error occurred in get_sensor_data: {e}")
            self.is_connected = False
            return None
        finally:
            logger.debug(f"[{self.device_id}] Stopping notifications on {RESPONSE_CHAR_UUID}")
            try:
                if self.client.is_connected:
                    await self.client.stop_notify(RESPONSE_CHAR_UUID)
            except Exception as e:
                logger.warning(f"[{self.device_id}] Failed to stop notifications: {e}")


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

async def scan_devices():
    """周辺のBLEデバイスをスキャンして結果を返す"""
    logger.info("Scanning for devices...")
    found_devices = []
    try:
        devices = await BleakScanner.discover(timeout=10.0, return_adv=True)
        for address, (device, adv_data) in devices.items():
            if PLANT_SERVICE_UUID in adv_data.service_uuids:
                found_devices.append({'address': device.address, 'name': device.name or 'Unknown Plant Sensor', 'type': 'plant_sensor', 'rssi': device.rssi})
                continue
            switchbot_info = _parse_switchbot_adv_data(adv_data)
            if switchbot_info:
                device_name_map = {'switchbot_meter': 'SwitchBot Meter', 'switchbot_meter_plus': 'SwitchBot Meter Plus', 'switchbot_co2_meter': 'SwitchBot CO2 Meter'}
                found_devices.append({'address': device.address, 'name': device.name or device_name_map.get(switchbot_info['type'], 'Unknown SwitchBot'), 'type': switchbot_info['type'], 'rssi': device.rssi, 'data': switchbot_info.get('data')})
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
