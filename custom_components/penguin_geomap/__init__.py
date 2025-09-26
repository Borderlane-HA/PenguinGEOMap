
from __future__ import annotations

import logging
import time
import asyncio
from typing import Any, Dict, List, Optional

import aiohttp
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    DOMAIN,
    CONF_DEVICES,
    CONF_NAME,
    CONF_ENTITY_ID,
    CONF_KEY,
    CONF_SERVER_URL,
    CONF_ENABLED,
    CONF_VERIFY_SSL,
)

_LOGGER = logging.getLogger(__name__)


class DeviceWatcher:
    def __init__(self, hass: HomeAssistant, device: Dict[str, Any]) -> None:
        self.hass = hass
        self.name = device.get(CONF_NAME, "Unknown")
        self.entity_id = device.get(CONF_ENTITY_ID)
        self.key = device.get(CONF_KEY)
        self.server_url = device.get(CONF_SERVER_URL)
        self.enabled = bool(device.get(CONF_ENABLED, True))
        self.verify_ssl = bool(device.get(CONF_VERIFY_SSL, True))
        self._unsub = None
        self._last_sent: Optional[tuple[float, float]] = None

    async def async_start(self) -> None:
        if not self.enabled:
            _LOGGER.info("PenguinGEOMap: %s disabled, not starting watcher", self.name)
            return

        if not self.entity_id or not self.key or not self.server_url:
            _LOGGER.warning(
                "PenguinGEOMap: Device %s not fully configured (entity_id/key/server_url) – skipping.",
                self.name,
            )
            return

        # Subscribe to state changes
        self._unsub = async_track_state_change_event(
            self.hass,
            [self.entity_id],
            self._state_changed,
        )
        _LOGGER.info(
            "PenguinGEOMap: Started watcher for %s (%s) with verify_ssl=%s",
            self.name,
            self.entity_id,
            self.verify_ssl,
        )

        # Send initial position once if available
        await self._send_current_if_available()

    async def async_stop(self) -> None:
        if self._unsub:
            self._unsub()
            self._unsub = None
            _LOGGER.info("PenguinGEOMap: Stopped watcher for %s", self.name)

    async def _send_current_if_available(self) -> None:
        st = self.hass.states.get(self.entity_id)
        if not st:
            _LOGGER.debug("PenguinGEOMap: No current state for %s", self.entity_id)
            return
        attrs = st.attributes or {}
        lat = attrs.get("latitude")
        lon = attrs.get("longitude")
        if lat is None or lon is None:
            _LOGGER.debug("PenguinGEOMap: %s has no latitude/longitude attributes", self.entity_id)
            return
        ts = int(time.time())
        await self._async_post(float(lat), float(lon), ts)

    @callback
    def _state_changed(self, event) -> None:
        _LOGGER.debug("PenguinGEOMap: State changed for %s", self.entity_id)
        new_state = event.data.get("new_state")
        if new_state is None:
            return
        attrs = new_state.attributes or {}
        lat = attrs.get("latitude")
        lon = attrs.get("longitude")
        if lat is None or lon is None:
            _LOGGER.debug("PenguinGEOMap: Update for %s without lat/lon; skip", self.entity_id)
            return
        ts = int(time.time())
        coords = (float(lat), float(lon))
        if self._last_sent == coords:
            return
        self._last_sent = coords
        self.hass.async_create_task(self._async_post(coords[0], coords[1], ts))

    async def _async_post(self, lat: float, lon: float, ts: int) -> None:
        url = self.server_url.rstrip("/") + "/api/ingest.php"
        payload = {
            "key": self.key,
            "lat": lat,
            "lon": lon,
            "ts": ts,
            "name": self.name,
            "entity_id": self.entity_id,
        }
        try:
            session: aiohttp.ClientSession = async_get_clientsession(self.hass)
            async with session.post(url, json=payload, timeout=10, ssl=self.verify_ssl) as resp:
                if resp.status != 200:
                    _LOGGER.warning(
                        "PenguinGEOMap: POST %s failed (%s): %s",
                        url,
                        resp.status,
                        await resp.text(),
                    )
                else:
                    _LOGGER.debug(
                        "PenguinGEOMap: posted %s -> (%.6f, %.6f) ts=%s",
                        self.entity_id,
                        lat,
                        lon,
                        ts,
                    )
        except asyncio.TimeoutError:
            _LOGGER.warning("PenguinGEOMap: Timeout posting to %s", url)
        except Exception as err:
            _LOGGER.exception("PenguinGEOMap: Error posting to %s: %s", url, err)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    hass.data.setdefault(DOMAIN, {})
    devices = entry.options.get(CONF_DEVICES, entry.data.get(CONF_DEVICES, []))

    watchers: List[DeviceWatcher] = []
    _LOGGER.info("PenguinGEOMap: Configured devices: %s", devices)
    for dev in devices:
        watcher = DeviceWatcher(hass, dev)
        watchers.append(watcher)
        await watcher.async_start()


# Reload integration when options/data change
async def _update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
entry.async_on_unload(entry.add_update_listener(_update_listener))

    # Services
    async def async_handle_send_now(call):
        entity_id = call.data.get("entity_id")
        target: Optional[DeviceWatcher] = None
        if entity_id:
            for w in watchers:
                if w.entity_id == entity_id:
                    target = w
                    break
        else:
            target = watchers[0] if watchers else None
        if not target:
            _LOGGER.warning("PenguinGEOMap: send_now – no matching watcher/entity found")
            return
        await target._send_current_if_available()

    async def async_handle_test_post(call):
        device_index = call.data.get("device_index")
        lat = call.data.get("lat")
        lon = call.data.get("lon")
        target: Optional[DeviceWatcher] = None
        if device_index is not None:
            try:
                target = watchers[int(device_index)]
            except Exception:
                target = None
        if target is None and watchers:
            target = watchers[0]
        if not target:
            _LOGGER.warning("PenguinGEOMap: test_post – no devices configured")
            return
        if lat is None:
            lat = 48.137154
        if lon is None:
            lon = 11.576124
        ts = int(time.time())
        _LOGGER.info(
            "PenguinGEOMap: test_post to %s -> (%.6f, %.6f) ts=%s",
            target.server_url,
            float(lat),
            float(lon),
            ts,
        )
        await target._async_post(float(lat), float(lon), ts)

    hass.services.async_register(DOMAIN, "send_now", async_handle_send_now)
    hass.services.async_register(DOMAIN, "test_post", async_handle_test_post)

    hass.data[DOMAIN][entry.entry_id] = {"watchers": watchers}
    _LOGGER.info("PenguinGEOMap: setup complete with %d device(s)", len(watchers))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    data = hass.data.get(DOMAIN, {}).pop(entry.entry_id, {})
    for watcher in data.get("watchers", []):
        await watcher.async_stop()
    return True


async def async_update_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await async_unload_entry(hass, entry)
    await async_setup_entry(hass, entry)


# Options flow hook
from .config_flow import OptionsFlowHandler  # noqa: E402


async def async_get_options_flow(config_entry):
    return OptionsFlowHandler(config_entry)
