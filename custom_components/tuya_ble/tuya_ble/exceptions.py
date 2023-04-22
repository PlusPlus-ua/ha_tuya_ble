from __future__ import annotations


class TuyaBLEError(Exception):
    """Base class for Tuya BLE errors."""


class TuyaBLEEnumValueError(TuyaBLEError):
    """Raised when value assigned to DP_ENUM datapoint has unexpected type."""

    def __init__(self) -> None:
        super().__init__("Value of DP_ENUM datapoint must be unsigned integer")


class TuyaBLEDataFormatError(TuyaBLEError):
    """Raised when data in Tuya BLE structures formatted in wrong way."""

    def __init__(self) -> None:
        super().__init__("Incoming packet is formatted in wrong way")


class TuyaBLEDataCRCError(TuyaBLEError):
    """Raised when data packet has invalid CRC."""

    def __init__(self) -> None:
        super().__init__("Incoming packet has invalid CRC")


class TuyaBLEDataLengthError(TuyaBLEError):
    """Raised when data packet has invalid length."""

    def __init__(self) -> None:
        super().__init__("Incoming packet has invalid length")


class TuyaBLEDeviceError(TuyaBLEError):
    """Raised when Tuya BLE device returned error in response to command."""

    def __init__(self, code: int) -> None:
        super().__init__(("BLE deice returned error code %s") % (code))
