"""The Family Life integration: your family calendar, chores and shopping lists in Home Assistant."""

from __future__ import annotations

from dataclasses import dataclass

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady, HomeAssistantError
from homeassistant.helpers import config_entry_oauth2_flow, config_validation as cv

from .api import FamilyLifeApi, FamilyLifeAuthError, FamilyLifeError, FamilyLifeImplementation
from .const import CONF_API_BASE, CONF_METADATA, DOMAIN, PLATFORMS
from .coordinator import FamilyLifeCoordinator
from .webhook import async_setup_push

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


@dataclass
class FamilyLifeData:
    """Runtime data for one family."""

    api: FamilyLifeApi
    coordinator: FamilyLifeCoordinator


type FamilyLifeConfigEntry = ConfigEntry[FamilyLifeData]


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Register the integration's services."""

    async def complete_chore(call: ServiceCall) -> None:
        chore_id: str = call.data["chore_id"]
        entries = [e for e in hass.config_entries.async_entries(DOMAIN) if getattr(e, "runtime_data", None)]
        if not entries:
            raise HomeAssistantError("Family Life is not set up")
        last: Exception | None = None
        for entry in entries:
            try:
                await entry.runtime_data.api.complete_chore(chore_id)
            except FamilyLifeError as err:
                last = err
                continue
            await entry.runtime_data.coordinator.async_request_refresh()
            return
        raise HomeAssistantError(f"Could not complete the chore: {last}")

    hass.services.async_register(DOMAIN, "complete_chore", complete_chore, schema=vol.Schema({vol.Required("chore_id"): cv.string}))
    return True


async def async_setup_entry(hass: HomeAssistant, entry: FamilyLifeConfigEntry) -> bool:
    """Set up one family."""
    # The OAuth implementation is built from the server's discovery document (stored at sign-in),
    # so it is registered again on every start.
    config_entry_oauth2_flow.async_register_implementation(hass, DOMAIN, FamilyLifeImplementation(hass, entry.data[CONF_METADATA]))
    implementation = await config_entry_oauth2_flow.async_get_config_entry_implementation(hass, entry)
    session = config_entry_oauth2_flow.OAuth2Session(hass, entry, implementation)
    api = FamilyLifeApi(session, entry.data[CONF_API_BASE])
    coordinator = FamilyLifeCoordinator(hass, entry, api)
    try:
        await coordinator.async_config_entry_first_refresh()
    except FamilyLifeAuthError as err:
        raise ConfigEntryAuthFailed(str(err)) from err
    except FamilyLifeError as err:
        raise ConfigEntryNotReady(str(err)) from err

    entry.runtime_data = FamilyLifeData(api=api, coordinator=coordinator)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    await async_setup_push(hass, entry, coordinator)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: FamilyLifeConfigEntry) -> bool:
    """Unload."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
