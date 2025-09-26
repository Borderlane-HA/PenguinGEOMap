
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.const import EVENT_HOMEASSISTANT_START

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
            _LOGGER.info("PenguinGEOMap: %s disabled, not starting watcher", self.name)
            return
        if not self.entity_id or not self.key or not self.server_url:
            _LOGGER.warning("PenguinGEOMap: Device %s not fully configured (entity_id/key/server_url) – skipping.", self.name)
            return
        self._unsub = async_track_state_change_event(self.hass, [self.entity_id], self._state_changed)
        _LOGGER.info("PenguinGEOMap: Started watcher for %s (%s)", self.name, self.entity_id)
        # Send initial position once if available
        await self._send_current_if_available()

    async def async_stop(self):
        if self._unsub:
            self._unsub(); self._unsub = None
            _LOGGER.info("PenguinGEOMap: Stopped watcher for %s", self.name)

    async def _send_current_if_available(self):
        st = self.hass.states.get(self.entity_id)
        if not st:
            _LOGGER.debug("PenguinGEOMap: No current state for %s", self.entity_id)
            return
        attrs = st.attributes or {}
        lat = attrs.get("latitude"); lon = attrs.get("longitude")
        if lat is None or lon is None:
            _LOGGER.debug("PenguinGEOMap: %s has no latitude/longitude attributes", self.entity_id)
            return
        ts = int(time.time())
        await self._async_post(lat, lon, ts)

    @callback
    def _state_changed(self, event):
        new_state = event.data.get("new_state")
        if new_state is None:
            return
        attrs = new_state.attributes or {}
        lat = attrs.get("latitude"); lon = attrs.get("longitude")
        if lat is None or lon is None:
            _LOGGER.debug("PenguinGEOMap: Update for %s without lat/lon; skip", self.entity_id); return
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
                    _LOGGER.warning("PenguinGEOMap: POST %s failed (%s): %s", url, resp.status, await resp.text())
                else:
                    _LOGGER.debug("PenguinGEOMap: posted %s -> (%.6f, %.6f) ts=%s", self.entity_id, lat, lon, ts)
        except asyncio.TimeoutError:
            _LOGGER.warning("PenguinGEOMap: Timeout posting to %s", url)
        except Exception as e:
            _LOGGER.exception("PenguinGEOMap: Error posting to %s: %s", url, e)

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    hass.data.setdefault(DOMAIN, {})
    devices = entry.options.get(CONF_DEVICES, entry.data.get(CONF_DEVICES, []))
    watchers: List[DeviceWatcher] = []
    for dev in devices:
        w = DeviceWatcher(hass, dev)
        watchers.append(w)
        await w.async_start()

    # Register service to force-send current coords
    async def async_handle_send_now(call):
        entity_id = call.data.get("entity_id")
        # pick first watcher if not specified
        target: Optional[DeviceWatcher] = None
        if entity_id:
            for w in watchers:
                if w.entity_id == entity_id:
                    target = w; break
        else:
            target = watchers[0] if watchers else None
        if not target:
            _LOGGER.warning("PenguinGEOMap: send_now – no matching watcher/entity found"); return
        await target._send_current_if_available()

    hass.services.async_register(DOMAIN, "send_now", async_handle_send_now)

    hass.data[DOMAIN][entry.entry_id] = {"watchers": watchers}
    _LOGGER.info("PenguinGEOMap: setup complete with %d device(s)", len(watchers))
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
