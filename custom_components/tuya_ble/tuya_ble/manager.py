from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

@dataclass
class TuyaBLEDeviceCredentials:
    uuid: str
    local_key: str
    device_id: str
    category: str
    product_id: str
    device_name: str | None
    product_model: str | None
    product_name: str | None
    functions: List | None
    status_range: List | None

    def __str__(self):
        return (
            "uuid: xxxxxxxxxxxxxxxx, "
            "local_key: xxxxxxxxxxxxxxxx, "
            "device_id: xxxxxxxxxxxxxxxx, "
            "category: %s, "
            "product_id: %s, "
            "device_name: %s, "
            "product_model: %s, "
            "product_name: %s"
            "functions: %s"
            "status_range: %s"
        ) % (
            self.category,
            self.product_id,
            self.device_name,
            self.product_model,
            self.product_name,
            self.functions,
            self.status_range,
        )

class AbstaractTuyaBLEDeviceManager(ABC):
    """Abstaract manager of the Tuya BLE devices credentials."""

    @abstractmethod
    async def get_device_credentials(
        self,
        address: str,
        force_update: bool = False,
        save_data: bool = False,
    ) -> TuyaBLEDeviceCredentials | None:
        """Get credentials of the Tuya BLE device."""
        pass

    @classmethod
    def check_and_create_device_credentials(
        self,
        uuid: str | None,
        local_key: str | None,
        device_id: str | None,
        category: str | None,
        product_id: str | None,
        device_name: str | None,
        product_model: str | None,
        product_name: str | None,
        functions: List | None,
        status_range: List | None,
    ) -> TuyaBLEDeviceCredentials | None:
        """Checks and creates credentials of the Tuya BLE device."""
        if (
            uuid and 
            local_key and 
            device_id and
            category and
            product_id
        ):
            return TuyaBLEDeviceCredentials(
                uuid,
                local_key,
                device_id,
                category,
                product_id,
                device_name,
                product_model,
                product_name,
                functions,
                status_range,
            )
        else:
            return None
