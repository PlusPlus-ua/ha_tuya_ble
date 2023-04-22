"""The Tuya BLE integration."""
from __future__ import annotations

from homeassistant.backports.enum import StrEnum
from typing_extensions import Final

DOMAIN: Final = "tuya_ble"

DEVICE_METADATA_UUIDS: Final = "uuids"

DEVICE_DEF_MANUFACTURER: Final = "Tuya"
SET_DISCONNECTED_DELAY = 10 * 60

CONF_UUID: Final = "uuid"
CONF_LOCAL_KEY: Final = "local_key"
CONF_DEVICE_ID: Final = "device_id"
CONF_CATEGORY: Final = "category"
CONF_PRODUCT_ID: Final = "product_id"
CONF_DEVICE_NAME: Final = "device_name"
CONF_PRODUCT_NAME: Final = "product_name"

TUYA_API_FACTORY_INFO_URL: Final = "/v1.0/iot-03/devices/factory-infos?device_ids"
TUYA_FACTORY_INFO_MAC: Final = "mac"

BATTERY_STATE_LOW: Final = "low"
BATTERY_STATE_NORMAL: Final = "normal"
BATTERY_STATE_HIGH: Final = "high"

BATTERY_NOT_CHARGING: Final = "not_charging"
BATTERY_CHARGING: Final = "charging"
BATTERY_CHARGED: Final = "charged"

CO2_LEVEL_NORMAL: Final = "normal"
CO2_LEVEL_ALARM: Final = "alarm"

FINGERBOT_MODE_PUSH: Final = "push"
FINGERBOT_MODE_SWITCH: Final = "switch"

