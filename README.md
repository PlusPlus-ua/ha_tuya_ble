# Home Assistant support for Tuya BLE devices

## Overview

This integration supports Tuya devices connected via BLE.

_Inspired by code of [@redphx](https://github.com/redphx/poc-tuya-ble-fingerbot)

## Installation

Place the `custom_components` folder in your configuration directory (or add its contents to an existing `custom_components` folder). Alternatively install via [HACS](https://hacs.xyz/).

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=PlusPlus-ua&repository=ha_tuya_ble&category=integration)

## Usage

After adding to Home Assistan integration should discover all supported Bluetooth devices, or you can add discoverable devices manually.

The integration works locally, but connection to Tuya BLE device requires device ID and encryption key from Tuya IOT cloud. It could be obtained using the same credentials as in official Tuya integration. To obtain the credentials, please refer to official Tuya integration [documentation](https://www.home-assistant.io/integrations/tuya/)

## Supported devices list

* Fingerbots (category_id 'szjqr')
  + Fingerbot (product_id 'yrnk7mnn'), original device, first in category, powered by CR2 battery.
  + Fingerbot Plus (product_ids 'blliqpsj', 'yiihr7zh'), almost same as original, has sensor button for manual control.
  + CubeTouch II (product_id 'xhf790if'), bult-in battery with USB type C charging.

  All features available in Home Assistant, except programming (series of actions) - it's not documented and looks useless because it could be implemented by Home Assistant scripts or automations.

* Temperature and humidity sensors (category_id 'wsdcg')
  + Soil moisture sensor (product_id 'ojzlzzsw').

* CO2 sensors (category_id 'co2bj')
  + CO2 Detector (product_id '59s19z5m').
