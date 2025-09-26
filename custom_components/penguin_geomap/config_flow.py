
from __future__ import annotations
import voluptuous as vol
from typing import Any, Dict, List, Optional
from homeassistant import config_entries
from homeassistant.helpers.selector import EntitySelector, EntitySelectorConfig, TextSelector, TextSelectorConfig
from homeassistant.data_entry_flow import FlowResult
from .const import DOMAIN, CONF_DEVICES, CONF_NAME, CONF_ENTITY_ID, CONF_KEY, CONF_SERVER_URL, CONF_ENABLED

def device_schema(existing: Optional[Dict[str, Any]] = None) -> vol.Schema:
    existing = existing or {}
    return vol.Schema({
        vol.Required(CONF_NAME, default=existing.get(CONF_NAME, "")): TextSelector(TextSelectorConfig(type="text")),
        vol.Required(CONF_ENTITY_ID, default=existing.get(CONF_ENTITY_ID, "")): EntitySelector(EntitySelectorConfig(domain=["device_tracker"])),
        vol.Required(CONF_SERVER_URL, default=existing.get(CONF_SERVER_URL, "")): TextSelector(TextSelectorConfig(type="text")),
        vol.Required(CONF_KEY, default=existing.get(CONF_KEY, "")): TextSelector(TextSelectorConfig(type="password")),
        vol.Required(CONF_ENABLED, default=existing.get(CONF_ENABLED, True)): bool,
    })

class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict | None = None) -> FlowResult:
        # Collect the FIRST device immediately (no empty OK dialog)
        if user_input is not None:
            devices = [user_input]
            return self.async_create_entry(title="PenguinGEOMap", data={CONF_DEVICES: devices}, options={CONF_DEVICES: devices})
        return self.async_show_form(step_id="user", data_schema=device_schema(), description_placeholders={
            "example": "Select your device_tracker.XX (e.g., device_tracker.bananastefan). Server: https://your-server.tld/penguin_geomap_server"
        })

class OptionsFlowHandler(config_entries.OptionsFlow):
    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self.config_entry = config_entry
        self.devices: List[Dict[str, Any]] = list(config_entry.options.get(CONF_DEVICES, config_entry.data.get(CONF_DEVICES, [])))
        self._edit_index: Optional[int] = None

    async def async_step_init(self, user_input: dict | None = None) -> FlowResult:
        return self.async_show_menu(step_id="init", menu_options={"add": "Add device","edit": "Edit device","delete": "Delete device","save": "Save"})

    async def async_step_save(self, user_input: dict | None = None) -> FlowResult:
        return self.async_create_entry(title="", data={CONF_DEVICES: self.devices})

    async def async_step_add(self, user_input: dict | None = None) -> FlowResult:
        if user_input is not None:
            self.devices.append(user_input); return await self.async_step_init()
        return self.async_show_form(step_id="add", data_schema=device_schema())

    async def async_step_edit(self, user_input: dict | None = None) -> FlowResult:
        if user_input is not None:
            self._edit_index = int(user_input["index"]); return await self.async_step_edit_form()
        options = {str(i): f"{dev.get(CONF_NAME)} ({dev.get(CONF_ENTITY_ID)})" for i, dev in enumerate(self.devices)}
        schema = vol.Schema({vol.Required("index"): vol.In(list(options.keys()))})
        return self.async_show_form(step_id="edit", data_schema=schema)

    async def async_step_edit_form(self, user_input: dict | None = None) -> FlowResult:
        if self._edit_index is None: return await self.async_step_init()
        existing = self.devices[self._edit_index]
        if user_input is not None:
            self.devices[self._edit_index] = user_input; self._edit_index = None; return await self.async_step_init()
        return self.async_show_form(step_id="edit_form", data_schema=device_schema(existing))

    async def async_step_delete(self, user_input: dict | None = None) -> FlowResult:
        if user_input is not None:
            idx = int(user_input["index"]); 
            if 0 <= idx < len(self.devices): self.devices.pop(idx)
            return await self.async_step_init()
        options = {str(i): f"{dev.get(CONF_NAME)} ({dev.get(CONF_ENTITY_ID)})" for i, dev in enumerate(self.devices)}
        schema = vol.Schema({vol.Required("index"): vol.In(list(options.keys()))})
        return self.async_show_form(step_id="delete", data_schema=schema)
