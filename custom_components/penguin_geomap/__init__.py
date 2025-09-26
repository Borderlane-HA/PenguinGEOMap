from __future__ import annotations

import logging
from typing import Any, Dict, List

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_state_change_event

from .const import (
    DOMAIN,
    CONF_DEVICES,
    CONF_NAME,
    CONF_ENTITY_ID,
    CONF_KEY,
    CONF_SERVER_URL,
    CONF_ENABLED,
)

import aiohttp
import asyncio
import time

_LOGGER = logging.getLogger(__name__)

class DeviceWatcher:
    def __init__(self, hass: HomeAssistant, device: Dict[str, Any]):
        self.hass = hass
        self.name = device.get(CONF_NAME, "Unknown")
        self.entity_id = device.get(CONF_ENTITY_ID)
        self.key = device.get(CONF_KEY)
        self.server_url = device.get(CONF_SERVER_URL)
        self.enabled = device.get(CONF_ENABLED, True)
        self._unsub = None
        self._last_sent = None

    async def async_start(self):
        if not self.enabled:
            return
        if not self.entity_id or not self.key or not self.server_url:
            _LOGGER.warning("Device %s not fully configured; skipping watcher.", self.name)
            return
        self._unsub = async_track_state_change_event(
            self.hass,
            [self.entity_id],
            self._state_changed,
        )
        _LOGGER.debug("Started watcher for %s (%s)", self.name, self.entity_id)

    async def async_stop(self):
        if self._unsub:
            self._unsub()
            self._unsub = None
            _LOGGER.debug("Stopped watcher for %s", self.name)

    @callback
    def _state_changed(self, event):
        new_state = event.data.get("new_state")
        if new_state is None:
            return

        attrs = new_state.attributes or {}
        lat = attrs.get("latitude")
        lon = attrs.get("longitude")

        if lat is None or lon is None:
            _LOGGER.debug("State change for %s had no lat/lon; skipping", self.entity_id)
            return

        ts = int(time.time())
        # Debounce identical lat/lon
        if self._last_sent == (lat, lon):
            return
        self._last_sent = (lat, lon)

        self.hass.async_create_task(self._async_post(lat, lon, ts))

    async def _async_post(self, lat: float, lon: float, ts: int):
        payload = {
            "key": self.key,
            "lat": lat,
            "lon": lon,
            "ts": ts,
            "name": self.name,
            "entity_id": self.entity_id,
        }
        url = self.server_url.rstrip('/') + "/api/ingest.php"
        try:
            session: aiohttp.ClientSession = self.hass.helpers.aiohttp_client.async_get_clientsession()
            async with session.post(url, json=payload, timeout=10) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    _LOGGER.warning("PenguinGEOMap post failed (%s): %s", resp.status, text)
                else:
                    _LOGGER.debug("PenguinGEOMap posted for %s @ (%.6f, %.6f)", self.name, lat, lon)
        except asyncio.TimeoutError:
            _LOGGER.warning("Timeout posting to PenguinGEOMap server %s", url)
        except Exception as e:
            _LOGGER.exception("Error posting to PenguinGEOMap server: %s", e)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    hass.data.setdefault(DOMAIN, {})
    devices = entry.options.get(CONF_DEVICES, [])
    watchers: List[DeviceWatcher] = []
    for dev in devices:
        watcher = DeviceWatcher(hass, dev)
        watchers.append(watcher)
        await watcher.async_start()

    hass.data[DOMAIN][entry.entry_id] = {"watchers": watchers}
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    data = hass.data.get(DOMAIN, {}).pop(entry.entry_id, {})
    for watcher in data.get("watchers", []):
        await watcher.async_stop()
    return True


async def async_update_entry(hass: HomeAssistant, entry: ConfigEntry):
    await async_unload_entry(hass, entry)
    await async_setup_entry(hass, entry)

# IMPORTANT: Wire the Options Flow so HA shows the device editor.
from .config_flow import PenguinGeoMapOptionsFlow

async def async_get_options_flow(config_entry):
    return PenguinGeoMapOptionsFlow(config_entry)
