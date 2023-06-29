"""The Tuya BLE integration."""
from __future__ import annotations

from dataclasses import dataclass

import logging
from struct import pack, unpack
from typing import Callable

from homeassistant.components.text import (
    TextEntity,
    TextEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import (
    DOMAIN,
)
from .devices import TuyaBLEData, TuyaBLEEntity, TuyaBLEProductInfo
from .tuya_ble import TuyaBLEDataPointType, TuyaBLEDevice

_LOGGER = logging.getLogger(__name__)

SIGNAL_STRENGTH_DP_ID = -1

TuyaBLETextGetter = (
    Callable[["TuyaBLEText", TuyaBLEProductInfo], str | None] | None
)


TuyaBLETextIsAvailable = (
    Callable[["TuyaBLEText", TuyaBLEProductInfo], bool] | None
)


TuyaBLETextSetter = (
    Callable[["TuyaBLEText", TuyaBLEProductInfo, str], None] | None
)


def is_fingerbot_in_program_mode(
    self: TuyaBLEText,
    product: TuyaBLEProductInfo,
) -> bool:
    result: bool = True
    if product.fingerbot:
        datapoint = self._device.datapoints[product.fingerbot.mode]
        if datapoint:
            result = datapoint.value == 2
    return result


def get_fingerbot_program(
    self: TuyaBLEText,
    product: TuyaBLEProductInfo,
) -> str | None:
    result: float | None = None
    if product.fingerbot and product.fingerbot.program:
        datapoint = self._device.datapoints[product.fingerbot.program]
        if datapoint and type(datapoint.value) is bytes:
            result = ""
            step_count: int = datapoint.value[3]
            for step in range(step_count):
                step_pos = 4 + step * 3
                step_data = datapoint.value[step_pos:step_pos+3]
                position, delay = unpack(">BH", step_data)
                if delay > 9999:
                    delay = 9999
                result += (
                    (';' if step > 0 else '') +
                    str(position) +
                    (('/' + str(delay)) if delay > 0 else '')
                )
    return result


def set_fingerbot_program(
    self: TuyaBLEText,
    product: TuyaBLEProductInfo,
    value: str,
) -> None:
    if product.fingerbot and product.fingerbot.program:
        datapoint = self._device.datapoints[product.fingerbot.program]
        if datapoint and type(datapoint.value) is bytes:
            new_value = bytearray(datapoint.value[0:3])
            steps = value.split(';')
            new_value += int.to_bytes(len(steps), 1, "big")
            for step in steps:
                step_values = step.split('/')
                position = int(step_values[0])
                delay = int(step_values[1]) if len(step_values) > 1 else 0
                new_value += pack(">BH", position, delay)
            self._hass.create_task(datapoint.set_value(new_value))


@dataclass
class TuyaBLETextMapping:
    dp_id: int
    description: TextEntityDescription
    force_add: bool = True
    dp_type: TuyaBLEDataPointType | None = None
    default_value: str | None = None
    is_available: TuyaBLETextIsAvailable = None
    getter: Callable[[TuyaBLEText], None] | None = None
    setter: Callable[[TuyaBLEText], None] | None = None


@dataclass
class TuyaBLECategoryTextMapping:
    products: dict[str, list[TuyaBLETextMapping]] | None = None
    mapping: list[TuyaBLETextMapping] | None = None


mapping: dict[str, TuyaBLECategoryTextMapping] = {
    "szjqr": TuyaBLECategoryTextMapping(
        products={
            **dict.fromkeys(
                [
                    "blliqpsj",
                    "ndvkgsrm",
                    "yiihr7zh",
                    "neq16kgd"
                ],  # Fingerbot Plus
                [
                    TuyaBLETextMapping(
                        dp_id=121,
                        description=TextEntityDescription(
                            key="program",
                            icon="mdi:repeat",
                            pattern="^((\d{1,2}|100)(\/\d{1,2})?)(;((\d{1,2}|100)(\/\d{1,2})?))+$",
                            entity_category=EntityCategory.CONFIG,
                        ),
                        is_available=is_fingerbot_in_program_mode,
                        getter=get_fingerbot_program,
                        setter=set_fingerbot_program,
                    ),
                ]
            ),
        },
    ),
}


def get_mapping_by_device(device: TuyaBLEDevice) -> list[TuyaBLETextMapping]:
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


class TuyaBLEText(TuyaBLEEntity, TextEntity):
    """Representation of a Tuya BLE text entity."""

    def __init__(
        self,
        hass: HomeAssistant,
        coordinator: DataUpdateCoordinator,
        device: TuyaBLEDevice,
        product: TuyaBLEProductInfo,
        mapping: TuyaBLETextMapping,
    ) -> None:
        super().__init__(hass, coordinator, device, product, mapping.description)
        self._mapping = mapping

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        result = super().available
        if result and self._mapping.is_available:
            result = self._mapping.is_available(self, self._product)
        return result

    @property
    def native_value(self) -> str | None:
        """Return the value reported by the text."""
        if self._mapping.getter:
            return self._mapping.getter(self, self._product)

        datapoint = self._device.datapoints[self._mapping.dp_id]
        if datapoint:
            return str(datapoint.value)

        return self._mapping.description.default_value

    def set_value(self, value: str) -> None:
        """Change the value."""
        if self._mapping.setter:
            self._mapping.setter(self, self._product, value)
            return
        datapoint = self._device.datapoints.get_or_create(
            self._mapping.dp_id,
            TuyaBLEDataPointType.DT_STRING,
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
    entities: list[TuyaBLEText] = []
    for mapping in mappings:
        if mapping.force_add or data.device.datapoints.has_id(
            mapping.dp_id, mapping.dp_type
        ):
            entities.append(
                TuyaBLEText(
                    hass,
                    data.coordinator,
                    data.device,
                    data.product,
                    mapping,
                )
            )
    async_add_entities(entities)
