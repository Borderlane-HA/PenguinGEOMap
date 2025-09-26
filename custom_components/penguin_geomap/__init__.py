
from __future__ import annotations

import logging
import time
import asyncio
from typing import Any, Dict, List, Optional
from datetime import timedelta
import math

import aiohttp
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_state_change_event, async_track_time_interval
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
    CONF_POLL_SECONDS,
    KEY_REGEX,
)

_LOGGER = logging.getLogger(__name__)

import re
KEY_RE = re.compile(KEY_REGEX)

def _validate_device_input(data: Dict[str, Any]) -> Optional[str]:
    server = str(data.get("server_url", "")).strip()
    if not (server.startswith("http://") or server.startswith("https://")):
        return "server_url must start with http:// or https://"
    if "/api/ingest.php" in server:
        return "server_url must NOT include /api/ingest.php"
    key = str(data.get("key", "")).strip()
    if not KEY_RE.match(key):
        return "key must be 4–64 chars (A–Z a–z 0–9 _ -)"
    ent = str(data.get("entity_id", "")).strip()
    if not ent:
        return "entity_id required"
    return None

def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371000.0
    phi1 = math.radians(lat1); phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1); dl = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dl/2)**2
    return 2*R*math.asin(math.sqrt(a))


class DeviceWatcher:
    def __init__(self, hass: HomeAssistant, device: Dict[str, Any]) -> None:
        self.hass = hass
        self.name = device.get(CONF_NAME, "Unknown")
        self.entity_id = device.get(CONF_ENTITY_ID)
        self.key = device.get(CONF_KEY)
        self.server_url = device.get(CONF_SERVER_URL)
        self.enabled = bool(device.get(CONF_ENABLED, True))
        self.verify_ssl = bool(device.get(CONF_VERIFY_SSL, True))
        self.poll_seconds = int(device.get(CONF_POLL_SECONDS, 30))
        self._unsub = None
        self._unsub_poll = None
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

        self._unsub = async_track_state_change_event(
            self.hass,
            [self.entity_id],
            self._state_changed,
        )
        _LOGGER.info(
            "PenguinGEOMap: Started watcher for %s (%s) with verify_ssl=%s poll=%ss",
            self.name,
            self.entity_id,
            self.verify_ssl,
            self.poll_seconds,
        )

        await self._send_current_if_available()

        if self.poll_seconds > 0:
            self._unsub_poll = async_track_time_interval(self.hass, self._poll_now, timedelta(seconds=self.poll_seconds))
            _LOGGER.info("PenguinGEOMap: Polling every %ss for %s", self.poll_seconds, self.entity_id)

    async def async_stop(self) -> None:
        if self._unsub:
            self._unsub()
            self._unsub = None
            _LOGGER.info("PenguinGEOMap: Stopped watcher for %s", self.name)
        if self._unsub_poll:
            self._unsub_poll()
            self._unsub_poll = None

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

    async def _poll_now(self, now) -> None:
        st = self.hass.states.get(self.entity_id)
        if not st:
            return
        attrs = st.attributes or {}
        lat = attrs.get("latitude"); lon = attrs.get("longitude")
        if lat is None or lon is None:
            return
        lat = float(lat); lon = float(lon)
        if self._last_sent is None:
            await self._async_post(lat, lon, int(time.time()))
            self._last_sent = (lat, lon)
            _LOGGER.debug("PenguinGEOMap: poll -> first send for %s", self.entity_id)
            return
        dist = _haversine_m(self._last_sent[0], self._last_sent[1], lat, lon)
        if dist >= 1.0:
            await self._async_post(lat, lon, int(time.time()))
            self._last_sent = (lat, lon)
            _LOGGER.debug("PenguinGEOMap: poll -> moved %.2fm, sent for %s", dist, self.entity_id)

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

    # Auto-reload when options/data change
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
        if lat is None: lat = 48.137154
        if lon is None: lon = 11.576124
        ts = int(time.time())
        _LOGGER.info(
            "PenguinGEOMap: test_post to %s -> (%.6f, %.6f) ts=%s",
            target.server_url, float(lat), float(lon), ts,
        )
        await target._async_post(float(lat), float(lon), ts)

    async def async_handle_update_device(call):
        """Update a configured device (by index) in options and reload entry."""
        idx = call.data.get("index")
        if idx is None:
            _LOGGER.warning("PenguinGEOMap: update_device – missing 'index'"); return
        try:
            idx = int(idx)
        except Exception:
            _LOGGER.warning("PenguinGEOMap: update_device – invalid index"); return

        devices = entry.options.get(CONF_DEVICES, entry.data.get(CONF_DEVICES, []))
        if not (0 <= idx < len(devices)):
            _LOGGER.warning("PenguinGEOMap: update_device – index out of range"); return

        new_dev = dict(devices[idx])
        mapping = {
            "name": CONF_NAME,
            "entity_id": CONF_ENTITY_ID,
            "server_url": CONF_SERVER_URL,
            "key": CONF_KEY,
            "enabled": CONF_ENABLED,
            "verify_ssl": CONF_VERIFY_SSL,
            "poll_seconds": CONF_POLL_SECONDS,
        }
        for k_in, k_store in mapping.items():
            if k_in in call.data:
                new_dev[k_store] = call.data.get(k_in)

        err = _validate_device_input({
            "server_url": new_dev.get(CONF_SERVER_URL),
            "key": new_dev.get(CONF_KEY),
            "entity_id": new_dev.get(CONF_ENTITY_ID),
        })
        if err:
            _LOGGER.warning("PenguinGEOMap: update_device – %s", err)
            return

        devices[idx] = new_dev
        hass.config_entries.async_update_entry(entry, options={CONF_DEVICES: devices})
        _LOGGER.info("PenguinGEOMap: device %s updated; reloading entry", idx)

    hass.services.async_register(DOMAIN, "send_now", async_handle_send_now)
    hass.services.async_register(DOMAIN, "test_post", async_handle_test_post)
    hass.services.async_register(DOMAIN, "update_device", async_handle_update_device)

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
