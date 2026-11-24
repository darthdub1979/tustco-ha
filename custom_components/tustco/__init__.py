"""Tustco Local Tools - local-only Home Assistant integration.

No cloud, no account, no telemetry. Talks directly to Tustco bulbs and
the local Tustco Presence daemon on the LAN.
"""
from __future__ import annotations

import logging

from homeassistant.core import HomeAssistant
from homeassistant.helpers import aiohttp_client
from homeassistant.helpers.typing import ConfigType

DOMAIN = "tustco"
_LOGGER = logging.getLogger(__name__)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up from YAML (HACS installs the files; YAML enables them)."""
    conf = dict(config.get(DOMAIN, {}) or {})
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN]["config"] = conf

    hass.async_create_task(hass.async_forward_entry_setup(config, "sensor"))

    async def async_alert(call) -> None:
        """Pulse a Tustco bulb: color beacon with automatic restore."""
        host = call.data.get("host") or conf.get("bulb_host")
        if not host:
            _LOGGER.error("Tustco alert needs a bulb host (host: or bulb_host:)")
            return

        color = str(call.data.get("color", "FF0000")).lstrip("#")
        count = int(call.data.get("count", 3))
        session = aiohttp_client.async_get_clientsession(hass)

        try:
            async with session.get(
                f"http://{host}/cm",
                params={"cmnd": f"TustcoAlert {color},{count}"},
                timeout=10,
            ) as response:
                await response.text()
            _LOGGER.info("Tustco alert sent to %s: %s x%s", host, color, count)
        except Exception as exc:  # noqa: BLE001 - local device may be offline
            _LOGGER.error("Tustco alert failed for %s: %s", host, exc)

    hass.services.async_register(DOMAIN, "alert", async_alert)
    return True
