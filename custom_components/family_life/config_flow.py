"""Config flow: "Sign in with Family Life" (OAuth2 + PKCE, endpoints discovered from the server)."""

from __future__ import annotations

from collections.abc import Mapping
import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import SOURCE_REAUTH, ConfigFlowResult
from homeassistant.helpers import config_entry_oauth2_flow
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import FamilyLifeError, FamilyLifeImplementation, async_fetch_metadata
from .const import CONF_API_BASE, CONF_METADATA, CONF_SERVER, DOMAIN, SUGGESTED_SERVER

_LOGGER = logging.getLogger(__name__)


class FamilyLifeFlowHandler(config_entry_oauth2_flow.AbstractOAuth2FlowHandler, domain=DOMAIN):
    """Add a Family Life family to Home Assistant."""

    DOMAIN = DOMAIN
    VERSION = 1

    def __init__(self) -> None:
        """Initialize."""
        super().__init__()
        self._metadata: dict[str, Any] | None = None
        self._server: str | None = None

    @property
    def logger(self) -> logging.Logger:
        """Return logger."""
        return _LOGGER

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Ask which Family Life server (prefilled), discover it, then sign in."""
        errors: dict[str, str] = {}
        if user_input is not None:
            server = user_input[CONF_SERVER].strip()
            try:
                self._metadata = await async_fetch_metadata(async_get_clientsession(self.hass), server)
            except FamilyLifeError as err:
                _LOGGER.debug("Discovery failed: %s", err)
                errors["base"] = "cannot_connect"
            else:
                self._server = server
                return await self._async_start_oauth()
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Required(CONF_SERVER, default=self._server or SUGGESTED_SERVER): str}),
            errors=errors,
        )

    async def _async_start_oauth(self) -> ConfigFlowResult:
        assert self._metadata is not None
        impl = FamilyLifeImplementation(self.hass, self._metadata)
        config_entry_oauth2_flow.async_register_implementation(self.hass, DOMAIN, impl)
        return await self.async_step_pick_implementation({"implementation": impl.domain})

    async def async_oauth_create_entry(self, data: dict[str, Any]) -> ConfigFlowResult:
        """Signed in: identify the family so it is added once, then create (or update) the entry."""
        assert self._metadata is not None
        session = async_get_clientsession(self.hass)
        api_base = self._metadata.get("api_base") or self._metadata["token_endpoint"].rsplit("/oauth/", 1)[0]
        token = data["token"]["access_token"]
        async with session.get(f"{api_base}/oauth/me", headers={"Authorization": f"Bearer {token}"}) as resp:
            if resp.status != 200:
                return self.async_abort(reason="oauth_failed")
            me = (await resp.json()).get("data", {})
        await self.async_set_unique_id(me["familyKey"])
        entry_data = {**data, CONF_SERVER: self._server, CONF_API_BASE: api_base, CONF_METADATA: self._metadata}
        if self.source == SOURCE_REAUTH:
            self._abort_if_unique_id_mismatch(reason="wrong_family")
            return self.async_update_reload_and_abort(self._get_reauth_entry(), data_updates=entry_data)
        self._abort_if_unique_id_configured()
        return self.async_create_entry(title="Family Life", data=entry_data)

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        """The connection was revoked or expired: sign in again."""
        self._server = entry_data.get(CONF_SERVER)
        self._metadata = entry_data.get(CONF_METADATA)
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Confirm, then re-discover (endpoints may have moved) and sign in."""
        if user_input is None:
            return self.async_show_form(step_id="reauth_confirm")
        return await self.async_step_user({CONF_SERVER: self._server or SUGGESTED_SERVER})
