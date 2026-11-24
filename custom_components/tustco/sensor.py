"""Tustco Presence sensor: coarse RF motion tripwire from local bulbs."""
from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.components.sensor import SensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers import aiohttp_client
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

from . import DOMAIN

_LOGGER = logging.getLogger(__name__)
SCAN_INTERVAL = timedelta(seconds=5)


async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities,
    discovery_info: DiscoveryInfoType | None = None,
) -> None:
    """Set up the presence sensor from YAML."""
    host = config.get("host") or hass.data.get(DOMAIN, {}).get("config", {}).get(
        "presence_host"
    )
    if not host:
        _LOGGER.info("Tustco presence sensor skipped: no presence_host configured")
        return
    async_add_entities([TustcoPresenceSensor(hass, host)], True)


class TustcoPresenceSensor(SensorEntity):
    """Aggregated state of the Tustco Presence daemon."""

    _attr_name = "Tustco Presence"
    _attr_should_poll = True

    def __init__(self, hass: HomeAssistant, host: str) -> None:
        self._host = host
        self._attr_unique_id = f"tustco_presence_{host}"
        self._attr_native_value = "unknown"
        self._attr_extra_state_attributes: dict = {}

    async def async_update(self) -> None:
        """Fetch /state.json from the local Presence daemon."""
        session = aiohttp_client.async_get_clientsession(self.hass)
        try:
            async with session.get(
                f"http://{self._host}:8126/state.json", timeout=5
            ) as response:
                data = await response.json(content_type=None)
        except Exception as exc:  # noqa: BLE001 - local daemon may be offline
            self._attr_native_value = "unavailable"
            _LOGGER.debug("Tustco Presence read failed: %s", exc)
            return

        devices = data.get("devices", [])
        states = [device.get("state") for device in devices]
        if "motion" in states:
            self._attr_native_value = "motion"
        elif states:
            self._attr_native_value = "idle"
        else:
            self._attr_native_value = "unknown"

        self._attr_extra_state_attributes = {
            "updated": data.get("updated"),
            "devices": devices,
        }
