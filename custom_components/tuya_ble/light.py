"""The Tuya BLE integration."""
from __future__ import annotations

from dataclasses import dataclass, field

import logging
import json
import copy

from typing import Any, Callable, cast
from enum import IntEnum, StrEnum, Enum

from homeassistant.components.tuya.const import (
    DPCode,
    DPType,
    WorkMode,
)

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP,
    ATTR_HS_COLOR,
    ColorMode,
    LightEntity,
    LightEntityDescription,
)

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import DOMAIN
from .base import IntegerTypeData
from .util import remap_value
from .devices import TuyaBLEData, TuyaBLEEntity, TuyaBLEProductInfo
from .tuya_ble import (
    TuyaBLEDevice, 
    TuyaBLEEntityDescription,
)

_LOGGER = logging.getLogger(__name__)

# Most of the code here is identical to the one from the Tuya cloud Light component
@dataclass
class ColorTypeData:
    """Color Type Data."""

    h_type: IntegerTypeData
    s_type: IntegerTypeData
    v_type: IntegerTypeData


DEFAULT_COLOR_TYPE_DATA = ColorTypeData(
    h_type=IntegerTypeData(DPCode.COLOUR_DATA_HSV, min=1, scale=0, max=360, step=1),
    s_type=IntegerTypeData(DPCode.COLOUR_DATA_HSV, min=1, scale=0, max=255, step=1),
    v_type=IntegerTypeData(DPCode.COLOUR_DATA_HSV, min=1, scale=0, max=255, step=1),
)

DEFAULT_COLOR_TYPE_DATA_V2 = ColorTypeData(
    h_type=IntegerTypeData(DPCode.COLOUR_DATA_HSV, min=1, scale=0, max=360, step=1),
    s_type=IntegerTypeData(DPCode.COLOUR_DATA_HSV, min=1, scale=0, max=1000, step=1),
    v_type=IntegerTypeData(DPCode.COLOUR_DATA_HSV, min=1, scale=0, max=1000, step=1),
)


@dataclass
class ColorData:
    """Color Data."""

    type_data: ColorTypeData
    h_value: int
    s_value: int
    v_value: int

    @property
    def hs_color(self) -> tuple[float, float]:
        """Get the HS value from this color data."""
        return (
            self.type_data.h_type.remap_value_to(self.h_value, 0, 360),
            self.type_data.s_type.remap_value_to(self.s_value, 0, 100),
        )

    @property
    def brightness(self) -> int:
        """Get the brightness value from this color data."""
        return round(self.type_data.v_type.remap_value_to(self.v_value, 0, 255))

@dataclass
class TuyaLightEntityDescription(
            TuyaBLEEntityDescription, 
            LightEntityDescription
            ):
    """Describe an Tuya light entity."""

    brightness_max: DPCode | None = None
    brightness_min: DPCode | None = None
    brightness: DPCode | tuple[DPCode, ...] | None = None
    color_data: DPCode | tuple[DPCode, ...] | None = None
    color_mode: DPCode | None = None
    color_temp: DPCode | tuple[DPCode, ...] | None = None
    default_color_type: ColorTypeData = field(
        default_factory=lambda: DEFAULT_COLOR_TYPE_DATA
    ) 


# You can add here description for device for which automatic capabilities setting
# from the cloud data doesn't work - if "key" is "", then products descriptions
# defined fields override the category ones.
# Else the products descriptions are full descriptions and replace the category ones
#
# function/status range are array of dicts descriptions the DPs
# Values are added (replace for same DP) to what we get from the cloud
# ex: 
# key = ""
# functions = [
#   {"code": "switch_led", "dp_id": 1, "type": "Boolean", "values": {}},
#   {"code": "bright_value", "dp_id": 3, "type": "Integer", "values": {"min":10,"max":1000,"scale":0,"step":1}}, 
#   {"code": "colour_data", "dp_id": 5, "type": "Json", "values": {"h":{"min":0,"scale":0,"unit":"","max":360,"step":1},"s":{"min":0,"scale":0,"unit":"","max":1000,"step":1},"v":{"min":0,"scale":0,"unit":"","max":1000,"step":1}}}, 
# ]
# ex:
# <category> : { <productid> : [ TuyaLightEntityDescription(); ... ] },
# ...}
ProductsMapping: dict[str, dict[str, tuple[TuyaLightEntityDescription, ...]]] = {
    "dd": {
        "nvfrtxlq" : (
            TuyaLightEntityDescription(
                key= "", # just override the category description from these set keys 
                values_overrides={
                    # So we still get the right enum values if the product isn't set to DP mode in the cloud settings
                    DPCode.WORK_MODE : {
                        "range" : {
                            WorkMode.COLOUR,
                            "dynamic_mod",
                            "scene_mod",
                            WorkMode.MUSIC,
                        }
                    }
                }
            ),
        )
    }
}

# Copied from standard Tuya light component - we could add some default values here too
LIGHTS: dict[str, tuple[TuyaLightEntityDescription, ...]] = {
    # Curtain Switch
    # https://developer.tuya.com/en/docs/iot/category-clkg?id=Kaiuz0gitil39
    "clkg": (
        TuyaLightEntityDescription(
            key=DPCode.SWITCH_BACKLIGHT,
            translation_key="backlight",
            entity_category=EntityCategory.CONFIG,
        ),
    ),
    # String Lights
    # https://developer.tuya.com/en/docs/iot/dc?id=Kaof7taxmvadu
    "dc": (
        TuyaLightEntityDescription(
            key=DPCode.SWITCH_LED,
            name=None,
            color_mode=DPCode.WORK_MODE,
            brightness=DPCode.BRIGHT_VALUE,
            color_temp=DPCode.TEMP_VALUE,
            color_data=DPCode.COLOUR_DATA,
        ),
    ),
    # Strip Lights
    # https://developer.tuya.com/en/docs/iot/dd?id=Kaof804aibg2l
    "dd": (
        TuyaLightEntityDescription(
            key=DPCode.SWITCH_LED,
            name=None,
            color_mode=DPCode.WORK_MODE,
            brightness=DPCode.BRIGHT_VALUE,
            color_temp=DPCode.TEMP_VALUE,
            color_data=DPCode.COLOUR_DATA,
            default_color_type=DEFAULT_COLOR_TYPE_DATA_V2,
        ),
    ),
    # Light
    # https://developer.tuya.com/en/docs/iot/categorydj?id=Kaiuyzy3eheyy
    "dj": (
        TuyaLightEntityDescription(
            key=DPCode.SWITCH_LED,
            name=None,
            color_mode=DPCode.WORK_MODE,
            brightness=(DPCode.BRIGHT_VALUE_V2, DPCode.BRIGHT_VALUE),
            color_temp=(DPCode.TEMP_VALUE_V2, DPCode.TEMP_VALUE),
            color_data=(DPCode.COLOUR_DATA_V2, DPCode.COLOUR_DATA),
        ),
        # Not documented
        # Based on multiple reports: manufacturer customized Dimmer 2 switches
        TuyaLightEntityDescription(
            key=DPCode.SWITCH_1,
            translation_key="light",
            brightness=DPCode.BRIGHT_VALUE_1,
        ),
    ),
    # Ceiling Fan Light
    # https://developer.tuya.com/en/docs/iot/fsd?id=Kaof8eiei4c2v
    "fsd": (
        TuyaLightEntityDescription(
            key=DPCode.SWITCH_LED,
            name=None,
            color_mode=DPCode.WORK_MODE,
            brightness=DPCode.BRIGHT_VALUE,
            color_temp=DPCode.TEMP_VALUE,
            color_data=DPCode.COLOUR_DATA,
        ),
        # Some ceiling fan lights use LIGHT for DPCode instead of SWITCH_LED
        TuyaLightEntityDescription(
            key=DPCode.LIGHT,
            name=None,
        ),
    ),
    # Ambient Light
    # https://developer.tuya.com/en/docs/iot/ambient-light?id=Kaiuz06amhe6g
    "fwd": (
        TuyaLightEntityDescription(
            key=DPCode.SWITCH_LED,
            name=None,
            color_mode=DPCode.WORK_MODE,
            brightness=DPCode.BRIGHT_VALUE,
            color_temp=DPCode.TEMP_VALUE,
            color_data=DPCode.COLOUR_DATA,
        ),
    ),
    # Motion Sensor Light
    # https://developer.tuya.com/en/docs/iot/gyd?id=Kaof8a8hycfmy
    "gyd": (
        TuyaLightEntityDescription(
            key=DPCode.SWITCH_LED,
            name=None,
            color_mode=DPCode.WORK_MODE,
            brightness=DPCode.BRIGHT_VALUE,
            color_temp=DPCode.TEMP_VALUE,
            color_data=DPCode.COLOUR_DATA,
        ),
    ),
    # Humidifier Light
    # https://developer.tuya.com/en/docs/iot/categoryjsq?id=Kaiuz1smr440b
    "jsq": (
        TuyaLightEntityDescription(
            key=DPCode.SWITCH_LED,
            name=None,
            color_mode=DPCode.WORK_MODE,
            brightness=DPCode.BRIGHT_VALUE,
            color_data=DPCode.COLOUR_DATA_HSV,
        ),
    ),
    # Switch
    # https://developer.tuya.com/en/docs/iot/s?id=K9gf7o5prgf7s
    "kg": (
        TuyaLightEntityDescription(
            key=DPCode.SWITCH_BACKLIGHT,
            translation_key="backlight",
            entity_category=EntityCategory.CONFIG,
        ),
    ),
    # Air Purifier
    # https://developer.tuya.com/en/docs/iot/f?id=K9gf46h2s6dzm
    "kj": (
        TuyaLightEntityDescription(
            key=DPCode.LIGHT,
            translation_key="backlight",
            entity_category=EntityCategory.CONFIG,
        ),
    ),
    # Air conditioner
    # https://developer.tuya.com/en/docs/iot/categorykt?id=Kaiuz0z71ov2n
    "kt": (
        TuyaLightEntityDescription(
            key=DPCode.LIGHT,
            translation_key="backlight",
            entity_category=EntityCategory.CONFIG,
        ),
    ),
    # Unknown light product
    # Found as VECINO RGBW as provided by diagnostics
    # Not documented
    "mbd": (
        TuyaLightEntityDescription(
            key=DPCode.SWITCH_LED,
            name=None,
            color_mode=DPCode.WORK_MODE,
            brightness=DPCode.BRIGHT_VALUE,
            color_data=DPCode.COLOUR_DATA,
        ),
    ),
    # Unknown product with light capabilities
    # Fond in some diffusers, plugs and PIR flood lights
    # Not documented
    "qjdcz": (
        TuyaLightEntityDescription(
            key=DPCode.SWITCH_LED,
            name=None,
            color_mode=DPCode.WORK_MODE,
            brightness=DPCode.BRIGHT_VALUE,
            color_data=DPCode.COLOUR_DATA,
        ),
    ),
    # Heater
    # https://developer.tuya.com/en/docs/iot/categoryqn?id=Kaiuz18kih0sm
    "qn": (
        TuyaLightEntityDescription(
            key=DPCode.LIGHT,
            translation_key="backlight",
            entity_category=EntityCategory.CONFIG,
        ),
    ),
    # Smart Camera
    # https://developer.tuya.com/en/docs/iot/categorysp?id=Kaiuz35leyo12
    "sp": (
        TuyaLightEntityDescription(
            key=DPCode.FLOODLIGHT_SWITCH,
            brightness=DPCode.FLOODLIGHT_LIGHTNESS,
            name="Floodlight",
        ),
        TuyaLightEntityDescription(
            key=DPCode.BASIC_INDICATOR,
            name="Indicator light",
            entity_category=EntityCategory.CONFIG,
        ),
    ),
    # Dimmer Switch
    # https://developer.tuya.com/en/docs/iot/categorytgkg?id=Kaiuz0ktx7m0o
    "tgkg": (
        TuyaLightEntityDescription(
            key=DPCode.SWITCH_LED_1,
            translation_key="light",
            brightness=DPCode.BRIGHT_VALUE_1,
            brightness_max=DPCode.BRIGHTNESS_MAX_1,
            brightness_min=DPCode.BRIGHTNESS_MIN_1,
        ),
        TuyaLightEntityDescription(
            key=DPCode.SWITCH_LED_2,
            translation_key="light_2",
            brightness=DPCode.BRIGHT_VALUE_2,
            brightness_max=DPCode.BRIGHTNESS_MAX_2,
            brightness_min=DPCode.BRIGHTNESS_MIN_2,
        ),
        TuyaLightEntityDescription(
            key=DPCode.SWITCH_LED_3,
            translation_key="light_3",
            brightness=DPCode.BRIGHT_VALUE_3,
            brightness_max=DPCode.BRIGHTNESS_MAX_3,
            brightness_min=DPCode.BRIGHTNESS_MIN_3,
        ),
    ),
    # Dimmer
    # https://developer.tuya.com/en/docs/iot/tgq?id=Kaof8ke9il4k4
    "tgq": (
        TuyaLightEntityDescription(
            key=DPCode.SWITCH_LED,
            translation_key="light",
            brightness=(DPCode.BRIGHT_VALUE_V2, DPCode.BRIGHT_VALUE),
            brightness_max=DPCode.BRIGHTNESS_MAX_1,
            brightness_min=DPCode.BRIGHTNESS_MIN_1,
        ),
        TuyaLightEntityDescription(
            key=DPCode.SWITCH_LED_1,
            translation_key="light",
            brightness=DPCode.BRIGHT_VALUE_1,
        ),
        TuyaLightEntityDescription(
            key=DPCode.SWITCH_LED_2,
            translation_key="light_2",
            brightness=DPCode.BRIGHT_VALUE_2,
        ),
    ),
    # Wake Up Light II
    # Not documented
    "hxd": (
        TuyaLightEntityDescription(
            key=DPCode.SWITCH_LED,
            translation_key="light",
            brightness=(DPCode.BRIGHT_VALUE_V2, DPCode.BRIGHT_VALUE),
            brightness_max=DPCode.BRIGHTNESS_MAX_1,
            brightness_min=DPCode.BRIGHTNESS_MIN_1,
        ),
    ),
    # Solar Light
    # https://developer.tuya.com/en/docs/iot/tynd?id=Kaof8j02e1t98
    "tyndj": (
        TuyaLightEntityDescription(
            key=DPCode.SWITCH_LED,
            name=None,
            color_mode=DPCode.WORK_MODE,
            brightness=DPCode.BRIGHT_VALUE,
            color_temp=DPCode.TEMP_VALUE,
            color_data=DPCode.COLOUR_DATA,
        ),
    ),
    # Ceiling Light
    # https://developer.tuya.com/en/docs/iot/ceiling-light?id=Kaiuz03xxfc4r
    "xdd": (
        TuyaLightEntityDescription(
            key=DPCode.SWITCH_LED,
            name=None,
            color_mode=DPCode.WORK_MODE,
            brightness=DPCode.BRIGHT_VALUE,
            color_temp=DPCode.TEMP_VALUE,
            color_data=DPCode.COLOUR_DATA,
        ),
        TuyaLightEntityDescription(
            key=DPCode.SWITCH_NIGHT_LIGHT,
            translation_key="night_light",
        ),
    ),
    # Remote Control
    # https://developer.tuya.com/en/docs/iot/ykq?id=Kaof8ljn81aov
    "ykq": (
        TuyaLightEntityDescription(
            key=DPCode.SWITCH_CONTROLLER,
            name=None,
            color_mode=DPCode.WORK_MODE,
            brightness=DPCode.BRIGHT_CONTROLLER,
            color_temp=DPCode.TEMP_CONTROLLER,
        ),
    ),
    # Fan
    # https://developer.tuya.com/en/docs/iot/categoryfs?id=Kaiuz1xweel1c
    "fs": (
        TuyaLightEntityDescription(
            key=DPCode.LIGHT,
            name=None,
            color_mode=DPCode.WORK_MODE,
            brightness=DPCode.BRIGHT_VALUE,
            color_temp=DPCode.TEMP_VALUE,
        ),
        TuyaLightEntityDescription(
            key=DPCode.SWITCH_LED,
            translation_key="light_2",
            brightness=DPCode.BRIGHT_VALUE_1,
        ),
    ),
}

# Socket (duplicate of `kg`)
# https://developer.tuya.com/en/docs/iot/s?id=K9gf7o5prgf7s
LIGHTS["cz"] = LIGHTS["kg"]

# Power Socket (duplicate of `kg`)
# https://developer.tuya.com/en/docs/iot/s?id=K9gf7o5prgf7s
LIGHTS["pc"] = LIGHTS["kg"]

# update the category mapping using the product mapping overrides
# both tuple should have the same size
def update_mapping(category_description: tuple[TuyaLightEntityDescription], mapping: tuple[TuyaLightEntityDescription]) -> tuple[TuyaLightEntityDescription]:
    m = tuple()
    l = list(category_description)
    for desc in mapping:
        cat_desc = l.pop(0)
        if desc.key == "":
            cat_desc = copy.deepcopy(cat_desc)
            
            for key in [
                        "brightness_max", 
                        "brightness_min", 
                        "color_data", 
                        "color_mode", 
                        "color_temp", 
                    ]:
                if v := getattr(desc, key):
                    setattr(cat_desc, key, v)

            for key in [
                        "function", 
                        "status_range", 
                    ]:
                if v := getattr(desc, key):
                    l = getattr(desc, key)
                    if l:
                        l.append(v)
                    else:
                        l = v
                    setattr(cat_desc, key, l)

            for key in [
                        "values_overrides", 
                        "values_defaults", 
                    ]:
                if v := getattr(desc, key):
                    l = getattr(desc, key)
                    if l:
                        l.update(v)
                    else:
                        l = v
                    setattr(cat_desc, key, l)

            desc = cat_desc

        m = m + (desc,)

    return m

def get_mapping_by_device(device: TuyaBLEDevice) -> tuple[TuyaLightEntityDescription]:
    category_mapping = LIGHTS.get(device.category)

    category = ProductsMapping.get(device.category)
    if category is not None:
        product_mapping_overrides = category.get(device.product_id)
        if product_mapping_overrides is not None:
             return update_mapping(category_mapping, product_mapping_overrides)
             
    return category_mapping


class TuyaBLELight(TuyaBLEEntity, LightEntity):
    """Representation of a Tuya BLE Light."""

    entity_description: TuyaLightEntityDescription

    _brightness_max: IntegerTypeData | None = None
    _brightness_min: IntegerTypeData | None = None
    _brightness: IntegerTypeData | None = None
    _color_data_dpcode: DPCode | None = None
    _color_data_type: ColorTypeData | None = None
    _color_mode_dpcode: DPCode | None = None
    _color_temp: IntegerTypeData | None = None

    _attr_has_entity_name = True
    _attr_name = None

    def __init__(
        self,
        hass: HomeAssistant,
        coordinator: DataUpdateCoordinator,
        device: TuyaBLEDevice,
        product: TuyaBLEProductInfo,
        description: TuyaLightEntityDescription

    ) -> None:
        super().__init__(hass, coordinator, device, product, description)

        self._attr_unique_id = f"{super().unique_id}{description.key}"
        self._attr_supported_color_modes: set[ColorMode] = set()
        
        # Update/override the device info from our description
        device.update_description(description)

        _LOGGER.debug("%s : sunctions: %s", device.name, device.function)
        
        # Determine DPCodes
        self._color_mode_dpcode = self.find_dpcode(
            description.color_mode, prefer_function=True
        )

        if int_type := self.find_dpcode(
            description.brightness, dptype=DPType.INTEGER, prefer_function=True
        ):
            self._brightness = int_type
            self._attr_supported_color_modes.add(ColorMode.BRIGHTNESS)
            self._brightness_max = self.find_dpcode(
                description.brightness_max, dptype=DPType.INTEGER
            )
            self._brightness_min = self.find_dpcode(
                description.brightness_min, dptype=DPType.INTEGER
            )

        if int_type := self.find_dpcode(
            description.color_temp, dptype=DPType.INTEGER, prefer_function=True
        ):
            self._color_temp = int_type
            self._attr_supported_color_modes.add(ColorMode.COLOR_TEMP)

        if (
            dpcode := self.find_dpcode(description.color_data, prefer_function=True)
        ) and (self.get_dptype(dpcode) == DPType.JSON or self.get_dptype(dpcode) == DPType.STRING):
            self._color_data_dpcode = dpcode
            self._attr_supported_color_modes.add(ColorMode.HS)
            if dpcode in self.device.function:
                values = cast(str, self.device.function[dpcode].values)
            else:
                values = self.device.status_range[dpcode].values

            function_data = values
            if isinstance(function_data, str):
                function_data = json.loads(function_data)

            # Fetch color data type information
            if function_data and function_data.get("h"):
                self._color_data_type = ColorTypeData(
                    h_type=IntegerTypeData(dpcode, **function_data["h"]),
                    s_type=IntegerTypeData(dpcode, **function_data["s"]),
                    v_type=IntegerTypeData(dpcode, **function_data["v"]),
                )
            else:
                # If no type is found, use a default one
                self._color_data_type = self.entity_description.default_color_type
                if self._color_data_dpcode == DPCode.COLOUR_DATA_V2 or (
                    self._brightness and self._brightness.max > 255
                ):
                    self._color_data_type = DEFAULT_COLOR_TYPE_DATA_V2

        if not self._attr_supported_color_modes:
            self._attr_supported_color_modes = {ColorMode.ONOFF}

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self.async_write_ha_state()

    @property
    def is_on(self) -> bool:
        """Return true if light is on."""
        return self.device.status.get(self.entity_description.key, False)

    def turn_on(self, **kwargs: Any) -> None:
        """Turn on or control the light."""
        commands = [{"code": self.entity_description.key, "value": True}]

        if self._color_temp and ATTR_COLOR_TEMP in kwargs:
            if self._color_mode_dpcode:
                commands += [
                    {
                        "code": self._color_mode_dpcode,
                        "value": WorkMode.WHITE,
                    },
                ]

            commands += [
                {
                    "code": self._color_temp.dpcode,
                    "value": round(
                        self._color_temp.remap_value_from(
                            kwargs[ATTR_COLOR_TEMP],
                            self.min_mireds,
                            self.max_mireds,
                            reverse=True,
                        )
                    ),
                },
            ]

        if self._color_data_type and (
            ATTR_HS_COLOR in kwargs
            or (
                ATTR_BRIGHTNESS in kwargs
                and self.color_mode == ColorMode.HS
                and ATTR_COLOR_TEMP not in kwargs
            )
        ):
            if self._color_mode_dpcode:
                commands += [
                    {
                        "code": self._color_mode_dpcode,
                        "value": WorkMode.COLOUR,
                    },
                ]

            if not (brightness := kwargs.get(ATTR_BRIGHTNESS)):
                brightness = self.brightness or 0

            if not (color := kwargs.get(ATTR_HS_COLOR)):
                color = self.hs_color or (0, 0)

            h = self._color_data_type.h_type.remap_value_from(
                                    color[0], 0, 360
                                )
            s = self._color_data_type.s_type.remap_value_from(
                                    color[1], 0, 100
                                )
            v = self._color_data_type.v_type.remap_value_from(
                                    brightness
                                )

            # Encoding for RGB from localtuya light component
            if self.__is_color_rgb_encoded():
                rgb = color_util.color_hsv_to_RGB(
                    color[0],
                    color[1],
                    int(brightness),
                )
                colorstr = "{:02x}{:02x}{:02x}{:04x}{:02x}{:02x}".format(
                    round(rgb[0]),
                    round(rgb[1]),
                    round(rgb[2]),
                    round(h),
                    round(s),
                    round(v),
                )
            else:
                colorstr = "{:04x}{:04x}{:04x}".format(
                    round(h), round(s), round(v)
                )

            commands += [
                {
                    "code": self._color_data_dpcode,
                    #!! Color encoding is different from the cloud Light compoonent
                    #!! not sure that the encoding is the same for all light categories
                    "value": colorstr,
                },
            ]

        elif ATTR_BRIGHTNESS in kwargs and self._brightness:
            brightness = kwargs[ATTR_BRIGHTNESS]

            # If there is a min/max value, the brightness is actually limited.
            # Meaning it is actually not on a 0-255 scale.
            if (
                self._brightness_max is not None
                and self._brightness_min is not None
                and (
                    brightness_max := self.device.status.get(
                        self._brightness_max.dpcode
                    )
                )
                is not None
                and (
                    brightness_min := self.device.status.get(
                        self._brightness_min.dpcode
                    )
                )
                is not None
            ):
                # Remap values onto our scale
                brightness_max = self._brightness_max.remap_value_to(brightness_max)
                brightness_min = self._brightness_min.remap_value_to(brightness_min)

                # Remap the brightness value from their min-max to our 0-255 scale
                brightness = remap_value(
                    brightness,
                    to_min=brightness_min,
                    to_max=brightness_max,
                )

            commands += [
                {
                    "code": self._brightness.dpcode,
                    "value": round(self._brightness.remap_value_from(brightness)),
                },
            ]

        self._send_command(commands)

    def turn_off(self, **kwargs: Any) -> None:
        """Instruct the light to turn off."""

        self._send_command([{"code": self.entity_description.key, "value": False}])


    @property
    def brightness(self) -> int | None:
        """Return the brightness of the light."""
        # If the light is currently in color mode, extract the brightness from the color data
        if self.color_mode == ColorMode.HS and (color_data := self._get_color_data()):
            return color_data.brightness

        if not self._brightness:
            return None

        brightness = self.device.status.get(self._brightness.dpcode)
        if brightness is None:
            return None

        # Remap value to our scale
        brightness = self._brightness.remap_value_to(brightness)

        # If there is a min/max value, the brightness is actually limited.
        # Meaning it is actually not on a 0-255 scale.
        if (
            self._brightness_max is not None
            and self._brightness_min is not None
            and (brightness_max := self.device.status.get(self._brightness_max.dpcode))
            is not None
            and (brightness_min := self.device.status.get(self._brightness_min.dpcode))
            is not None
        ):
            # Remap values onto our scale
            brightness_max = self._brightness_max.remap_value_to(brightness_max)
            brightness_min = self._brightness_min.remap_value_to(brightness_min)

            # Remap the brightness value from their min-max to our 0-255 scale
            brightness = remap_value(
                brightness,
                from_min=brightness_min,
                from_max=brightness_max,
            )

        return round(brightness)

    @property
    def color_temp(self) -> int | None:
        """Return the color_temp of the light."""
        if not self._color_temp:
            return None

        temperature = self._device.status.get(self._color_temp.dpcode)
        if temperature is None:
            return None

        return round(
            self._color_temp.remap_value_to(
                temperature, self.min_mireds, self.max_mireds, reverse=True
            )
        )

    @property
    def hs_color(self) -> tuple[float, float] | None:
        """Return the hs_color of the light."""
        if self._color_data_dpcode is None or not (
            color_data := self._get_color_data()
        ):
            return None
        return color_data.hs_color

    @property
    def color_mode(self) -> ColorMode:
        """Return the color_mode of the light."""
        # We consider it to be in HS color mode, when work mode is anything
        # else than "white".
        if (
            self._color_mode_dpcode
            and self.device.status.get(self._color_mode_dpcode) != WorkMode.WHITE
        ):
            return ColorMode.HS
        if self._color_temp:
            return ColorMode.COLOR_TEMP
        if self._brightness:
            return ColorMode.BRIGHTNESS
        return ColorMode.ONOFF

    def _get_color_data(self) -> ColorData | None:
        """Get current color data from device."""
        if (
            self._color_data_type is None
            or self._color_data_dpcode is None
            or self._color_data_dpcode not in self.device.status
        ):
            return None

        if not (status_data := self.device.status[self._color_data_dpcode]):
            return None

        #!! Color encoding is different from the cloud Light compoonent
        #!! not sure that the encoding is the same for all light categories
        if len(status_data) == 12:
            h = float(int(status_data[:4], 16))
            s = float(int(status_data[4:8], 16))
            v = float(int(status_data[8:], 16))
            return ColorData(
                    type_data=self._color_data_type,
                    h_value=h,
                    s_value=s,
                    v_value=v,
                )   
        elif len(status_data) > 12:
            # Encoding for RGB devices from localtuya light component
            h = int(status_data[6:10], 16)
            s = int(status_data[10:12], 16)
            v = int(status_data[12:14], 16)
            return ColorData(
                    type_data=self._color_data_type,
                    h_value=h,
                    s_value=s,
                    v_value=v,
            )

        return None

    def __is_color_rgb_encoded(self):
        if not (status_data := self.device.status[self._color_data_dpcode]):
            return False

        if not (isinstance(status_data, str)):
            return False

        return len(status_data) > 12

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Tuya BLE sensors."""
    data: TuyaBLEData = hass.data[DOMAIN][entry.entry_id]
    descs = get_mapping_by_device(data.device)
    entities: list[TuyaBLELight] = []

    for desc in descs:
        entities.append(
            TuyaBLELight(
                    hass,
                    data.coordinator,
                    data.device,
                    data.product,
                    desc,
                )
        )
    async_add_entities(entities)
