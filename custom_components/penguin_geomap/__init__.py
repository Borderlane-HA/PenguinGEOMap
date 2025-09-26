
from __future__ import annotations

import logging
from typing import Any, Dict, List
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_state_change_event
from .const import (
    DOMAIN, CONF_DEVICES, CONF_NAME, CONF_ENTITY_ID, CONF_KEY, CONF_SERVER_URL, CONF_ENABLED,
)
import aiohttp, asyncio, time

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
        self._unsub = async_track_state_change_event(self.hass, [self.entity_id], self._state_changed)
        _LOGGER.debug("Started watcher for %s (%s)", self.name, self.entity_id)

    async def async_stop(self):
        if self._unsub:
            self._unsub(); self._unsub = None

    @callback
    def _state_changed(self, event):
        new_state = event.data.get("new_state")
        if new_state is None:
            return
        attrs = new_state.attributes or {}
        lat = attrs.get("latitude"); lon = attrs.get("longitude")
        if lat is None or lon is None:
            _LOGGER.debug("No lat/lon in %s update; skipping", self.entity_id); return
        ts = int(time.time())
        if self._last_sent == (lat, lon): return
        self._last_sent = (lat, lon)
        self.hass.async_create_task(self._async_post(lat, lon, ts))

    async def _async_post(self, lat: float, lon: float, ts: int):
        url = self.server_url.rstrip('/') + "/api/ingest.php"
        payload = {"key": self.key, "lat": lat, "lon": lon, "ts": ts, "name": self.name, "entity_id": self.entity_id}
        try:
            session: aiohttp.ClientSession = self.hass.helpers.aiohttp_client.async_get_clientsession()
            async with session.post(url, json=payload, timeout=10) as resp:
                if resp.status != 200:
                    _LOGGER.warning("POST %s failed (%s): %s", url, resp.status, await resp.text())
        except asyncio.TimeoutError:
            _LOGGER.warning("Timeout posting to %s", url)
        except Exception as e:
            _LOGGER.exception("Error posting to %s: %s", url, e)

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    hass.data.setdefault(DOMAIN, {})
    devices = entry.options.get(CONF_DEVICES, entry.data.get(CONF_DEVICES, []))
    watchers: List[DeviceWatcher] = []
    for dev in devices:
        w = DeviceWatcher(hass, dev); watchers.append(w); await w.async_start()
    hass.data[DOMAIN][entry.entry_id] = {"watchers": watchers}
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    data = hass.data.get(DOMAIN, {}).pop(entry.entry_id, {})
    for w in data.get("watchers", []): await w.async_stop()
    return True

async def async_update_entry(hass: HomeAssistant, entry: ConfigEntry):
    await async_unload_entry(hass, entry); await async_setup_entry(hass, entry)

from .config_flow import OptionsFlowHandler
async def async_get_options_flow(config_entry):
    return OptionsFlowHandler(config_entry)
