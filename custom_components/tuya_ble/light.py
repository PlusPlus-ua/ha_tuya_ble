"""The Tuya BLE integration."""
from __future__ import annotations

from dataclasses import dataclass, field

import logging
from typing import Any, Callable

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_EFFECT,
    ATTR_RGB_COLOR,
    ATTR_WHITE,
    ATTR_HS_COLOR,
    ATTR_COLOR_MODE,
    ColorMode,
    LightEntity,
    LightEntityFeature,
    LightEntityDescription,
)

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import DOMAIN
from .devices import TuyaBLEData, TuyaBLEEntity, TuyaBLEProductInfo
from .tuya_ble import TuyaBLEDataPointType, TuyaBLEDevice

_LOGGER = logging.getLogger(__name__)

# supported known ids for Tuya Lights
SWITCH_ID = "switch"
MODE_ID = "mode"
BRIGHTNESS_ID = "brightness"
COLOR_HSB_ID = "color"


@dataclass
class TuyaBLELightMapping:
    description: LightEntityDescription
    dp_ids: dict[str, int]


@dataclass
class TuyaBLECategoryLightMapping:
    products: dict[str, list[TuyaBLELightMapping]] | None = None
    mapping: list[TuyaBLELightMapping] | None = None


mapping: dict[str, TuyaBLECategoryLightMapping] = {
    "dd": TuyaBLECategoryLightMapping(
        products={
            "nvfrtxlq": [  # Strip Lights
                TuyaBLELightMapping(
                    dp_ids = {
                        SWITCH_ID: 1,
                        MODE_ID: 2,
                        BRIGHTNESS_ID: 3,
                        COLOR_HSB_ID: 5,
                    },
                    description = LightEntityDescription(
                        key = "rgb_light_bar",
                        entity_registry_enabled_default = True,
                    ),
                ),
            ],
        },
    ),
}


def get_mapping_by_device(device: TuyaBLEDevice) -> list[TuyaBLECategoryLightMapping]:
    category = mapping.get(device.category)
    if category is not None and category.products is not None:
        product_mapping = category.products.get(device.product_id)
        if product_mapping is not None:
            return product_mapping
        if category.mapping is not None:
            return category.mapping
        else:
            return []
    else:
        return []


class TuyaBLELight(TuyaBLEEntity, LightEntity):
    """Representation of a Tuya BLE Light."""

    _attr_supported_color_modes = {ColorMode.HS, ColorMode.WHITE }
    _attr_has_entity_name = True
    _attr_name = None

    def __init__(
        self,
        hass: HomeAssistant,
        coordinator: DataUpdateCoordinator,
        device: TuyaBLEDevice,
        product: TuyaBLEProductInfo,
        mapping: TuyaBLELightMapping,
    ) -> None:
        super().__init__(hass, coordinator, device, product, mapping.description)
        self._mapping = mapping

        color_modes = {ColorMode.HS, ColorMode.WHITE}

        self._attr_supported_color_modes = color_modes
        self._attr_color_mode = ColorMode.HS

        self._white = 0
        self._attr_brightness = 0
        self._attr_hs_color = (0, 0)
        self._attr_is_on = False

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""

        dpid = self._mapping.dp_ids[BRIGHTNESS_ID]
        if dpid:
            datapoint = self._device.datapoints[dpid]
            if datapoint:
                self._attr_brightness = float(datapoint.value) * 255 / 1000
                self._attr_color_mode = ColorMode.WHITE

        dpid = self._mapping.dp_ids[COLOR_HSB_ID]
        if dpid:
            datapoint = self._device.datapoints[dpid]
            if datapoint:
                # from Tuya doc:
                # color format :
                # Value: 000011112222
                # 0000: H (chromaticity: 0-360, 0X0000-0X0168)
                # 1111: S (saturation: 0-1000, 0X0000-0X03E8)
                # 2222: V (Brightness: 0-1000, 0X0000-0X03E8)

                hsl_string = datapoint.value
                if len(hsl_string) == 12:
                    h = float(int(hsl_string[:4], 16))
                    s = float(int(hsl_string[4:8], 16)) * 100 / 1000
                    b = float(int(hsl_string[8:], 16)) * 255 / 1000
                    self._attr_color_mode = ColorMode.HS
                    self._attr_hs_color = (h,s)
                    self._attr_brightness = b


        dpid = self._mapping.dp_ids[SWITCH_ID]
        if dpid:
            datapoint = self._device.datapoints[dpid]
            if datapoint:
                self._attr_is_on = datapoint.value

        self.async_write_ha_state()

    @property
    def is_on(self) -> bool:
        """Return true if light is on."""

        if self._mapping.dp_ids and self._mapping.dp_ids[SWITCH_ID]:
            datapoint = self._device.datapoints[self._mapping.dp_ids[SWITCH_ID]]
            if datapoint:
                return bool(datapoint.value)
        return False

    def turn_on(self, **kwargs: Any) -> None:
        """Turn the light on."""

        color_mode = self._attr_color_mode
        if ATTR_COLOR_MODE in kwargs:
            color_mode =  kwargs[ATTR_COLOR_MODE]

        brightness = self._attr_brightness
        if ATTR_BRIGHTNESS in kwargs:
            brightness =  kwargs[ATTR_BRIGHTNESS]

        if ATTR_WHITE in kwargs:
            brightness =  kwargs[ATTR_WHITE]
            color_mode = ColorMode.WHITE

        hs_color = self._attr_hs_color
        if ATTR_HS_COLOR in kwargs:
            hs_color =  kwargs[ATTR_HS_COLOR]
            color_mode = ColorMode.HS

        if hs_color == None:
            color_mode = ColorMode.WHITE

        if color_mode == ColorMode.WHITE:
            self.send_brightness(brightness)

        if color_mode == ColorMode.HS:
            self.send_hsb(hs_color, brightness)

        self.send_onoff(True)

    def turn_off(self, **kwargs: Any) -> None:
        """Turn the light off."""

        self.send_onoff(False)

    # brightness is 0..255
    def send_brightness(self, brightness : Int) -> None:

        _LOGGER.debug("Send Brightness %d", brightness)

        if self._attr_color_mode != ColorMode.WHITE:
            self.send_dp_value(MODE_ID, TuyaBLEDataPointType.DT_ENUM, 0)

        new_value = brightness * 1000 / 255
        self.send_dp_value(BRIGHTNESS_ID, TuyaBLEDataPointType.DT_VALUE, new_value)



    def send_hsb(self, hs : float[2], brightness: Int) -> None:

        _LOGGER.debug("Send HSB %f %f %f", hs[0], hs[1], float(brightness))

        if self._attr_color_mode != ColorMode.HS:
            self.send_dp_value(MODE_ID, TuyaBLEDataPointType.DT_ENUM, 1)

        h = int(hs[0])
        s = int(hs[1] * 1000 / 100)
        b = int(brightness * 1000 / 255)

        new_value = ("%04X" % h) + ("%04X" % s) + ("%04X" % b)
        self.send_dp_value(COLOR_HSB_ID, TuyaBLEDataPointType.DT_STRING, new_value)


    def send_onoff(self, onoff: bool) -> None:

        self.send_dp_value(SWITCH_ID, TuyaBLEDataPointType.DT_BOOL, onoff)

    def send_dp_value(self,
        key: Any,
        type: TuyaBLEDataPointType,
        value: bytes | bool | int | str | None = None) -> None:

        dpid = self._mapping.dp_ids[key]
        if dpid:
            datapoint = self._device.datapoints.get_or_create(
                    dpid,
                    type,
                    value,
            )
            if datapoint:
                self._hass.create_task(datapoint.set_value(value))


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Tuya BLE sensors."""
    data: TuyaBLEData = hass.data[DOMAIN][entry.entry_id]
    mappings = get_mapping_by_device(data.device)
    entities: list[TuyaBLELight] = []
    for mapping in mappings:
        entities.append(
            TuyaBLELight(
                    hass,
                    data.coordinator,
                    data.device,
                    data.product,
                    mapping,
            )
        )
    async_add_entities(entities)