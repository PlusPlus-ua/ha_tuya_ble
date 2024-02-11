"""Tuya Home Assistant Base Device Model."""
from __future__ import annotations

import base64
from dataclasses import dataclass
import json
import struct
from typing import Any, Literal, Self, overload

from tuya_iot import TuyaDevice, TuyaDeviceManager

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import Entity

from homeassistant.components.tuya.const import (
    DPCode,
)

from .util import remap_value


@dataclass
class IntegerTypeData:
    """Integer Type Data."""

    dpcode: DPCode
    min: int
    max: int
    scale: float
    step: float
    unit: str | None = None
    type: str | None = None

    @property
    def max_scaled(self) -> float:
        """Return the max scaled."""
        return self.scale_value(self.max)

    @property
    def min_scaled(self) -> float:
        """Return the min scaled."""
        return self.scale_value(self.min)

    @property
    def step_scaled(self) -> float:
        """Return the step scaled."""
        return self.step / (10**self.scale)

    def scale_value(self, value: float | int) -> float:
        """Scale a value."""
        return value / (10**self.scale)

    def scale_value_back(self, value: float | int) -> int:
        """Return raw value for scaled."""
        return int(value * (10**self.scale))

    def remap_value_to(
        self,
        value: float,
        to_min: float | int = 0,
        to_max: float | int = 255,
        reverse: bool = False,
    ) -> float:
        """Remap a value from this range to a new range."""
        return remap_value(value, self.min, self.max, to_min, to_max, reverse)

    def remap_value_from(
        self,
        value: float,
        from_min: float | int = 0,
        from_max: float | int = 255,
        reverse: bool = False,
    ) -> float:
        """Remap a value from its current range to this range."""
        return remap_value(value, from_min, from_max, self.min, self.max, reverse)

    @classmethod
    def from_json(cls, dpcode: DPCode, data: str | dict) -> IntegerTypeData | None:
        """Load JSON string and return a IntegerTypeData object."""
    
        if isinstance(data, str):
            parsed = json.loads(data)
        else:
            parsed = data

        if parsed is None:
            return

        return cls(
            dpcode,
            min=int(parsed["min"]),
            max=int(parsed["max"]),
            scale=float(parsed["scale"]),
            step=max(float(parsed["step"]), 1),
            unit=parsed.get("unit"),
            type=parsed.get("type"),
        )

    @classmethod
    def from_dict(cls, dpcode: DPCode, data: dict | None) -> IntegerTypeData | None:
        """Load Dict and return a IntegerTypeData object."""

        if not dict:
            return None

        return cls(
            dpcode,
            min=int(dict.get("min", 0)),
            max=int(dict.get("max", 0)),
            scale=float(dict.get("scale", 0)),
            step=max(float(dict.get("step", 0)), 1),
            unit=dict.get("unit"),
            type=dict.get("type"),
        )

@dataclass
class EnumTypeData:
    """Enum Type Data."""

    dpcode: DPCode
    range: list[str]

    @classmethod
    def from_json(cls, dpcode: DPCode, data: str) -> EnumTypeData | None:
        """Load JSON string and return a EnumTypeData object."""
        if not (parsed := json.loads(data)):
            return None
        return cls(dpcode, **parsed)

