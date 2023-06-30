"""The Tuya BLE integration."""
from __future__ import annotations

from dataclasses import dataclass

import logging
from typing import Callable

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
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


TuyaBLEBinarySensorIsAvailable = (
    Callable[["TuyaBLEBinarySensor", TuyaBLEProductInfo], bool] | None
)


@dataclass
class TuyaBLEBinarySensorMapping:
    dp_id: int
    description: BinarySensorEntityDescription
    force_add: bool = True
    dp_type: TuyaBLEDataPointType | None = None
    getter: Callable[[TuyaBLEBinarySensor], None] | None = None
    #coefficient: float = 1.0
    #icons: list[str] | None = None
    is_available: TuyaBLEBinarySensorIsAvailable = None


@dataclass
class TuyaBLECategoryBinarySensorMapping:
    products: dict[str, list[TuyaBLEBinarySensorMapping]] | None = None
    mapping: list[TuyaBLEBinarySensorMapping] | None = None


mapping: dict[str, TuyaBLECategoryBinarySensorMapping] = {
    "wk": TuyaBLECategoryBinarySensorMapping(
        products={
            "drlajpqc": [  # Thermostatic Radiator Valve
                TuyaBLEBinarySensorMapping(
                    dp_id=105,
                    description=BinarySensorEntityDescription(
                        key="battery",
                        #icon="mdi:battery-alert",
                        device_class=BinarySensorDeviceClass.BATTERY,
                        entity_category=EntityCategory.DIAGNOSTIC,
                    ),
                ),
            ],
        },
    ),
}


def get_mapping_by_device(device: TuyaBLEDevice) -> list[TuyaBLEBinarySensorMapping]:
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


class TuyaBLEBinarySensor(TuyaBLEEntity, BinarySensorEntity):
    """Representation of a Tuya BLE binary sensor."""

    def __init__(
        self,
        hass: HomeAssistant,
        coordinator: DataUpdateCoordinator,
        device: TuyaBLEDevice,
        product: TuyaBLEProductInfo,
        mapping: TuyaBLEBinarySensorMapping,
    ) -> None:
        super().__init__(hass, coordinator, device, product, mapping.description)
        self._mapping = mapping

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        if self._mapping.getter is not None:
            self._mapping.getter(self)
        else:
            datapoint = self._device.datapoints[self._mapping.dp_id]
            if datapoint:
                self._attr_is_on = bool(datapoint.value)
                '''
                if datapoint.type == TuyaBLEDataPointType.DT_ENUM:
                    if self.entity_description.options is not None:
                        if datapoint.value >= 0 and datapoint.value < len(
                            self.entity_description.options
                        ):
                            self._attr_native_value = self.entity_description.options[
                                datapoint.value
                            ]
                        else:
                            self._attr_native_value = datapoint.value
                    if self._mapping.icons is not None:
                        if datapoint.value >= 0 and datapoint.value < len(
                            self._mapping.icons
                        ):
                            self._attr_icon = self._mapping.icons[datapoint.value]
                elif datapoint.type == TuyaBLEDataPointType.DT_VALUE:
                    self._attr_native_value = (
                        datapoint.value / self._mapping.coefficient
                    )
                else:
                    self._attr_native_value = datapoint.value
                '''
        self.async_write_ha_state()

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        result = super().available
        if result and self._mapping.is_available:
            result = self._mapping.is_available(self, self._product)
        return result


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Tuya BLE sensors."""
    data: TuyaBLEData = hass.data[DOMAIN][entry.entry_id]
    mappings = get_mapping_by_device(data.device)
    entities: list[TuyaBLEBinarySensor] = []
    for mapping in mappings:
        if mapping.force_add or data.device.datapoints.has_id(
            mapping.dp_id, mapping.dp_type
        ):
            entities.append(
                TuyaBLEBinarySensor(
                    hass,
                    data.coordinator,
                    data.device,
                    data.product,
                    mapping,
                )
            )
    async_add_entities(entities)
