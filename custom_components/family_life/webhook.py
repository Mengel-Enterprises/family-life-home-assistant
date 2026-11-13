"""Instant updates: Family Life POSTs a signed, data-free "something changed" ping here.

Family Life only delivers to a PUBLIC https URL, so push is registered when this instance has one:
a Home Assistant Cloud cloudhook, or an external https URL. Otherwise the integration simply polls.
"""

from __future__ import annotations

import logging

from aiohttp import web

from homeassistant.components import webhook
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.network import NoURLAvailableError, get_url

from .api import FamilyLifeError
from .const import (
    CONF_WEBHOOK_ID,
    CONF_WEBHOOK_SECRET,
    DOMAIN,
    SCAN_INTERVAL_WITH_PUSH,
    SIGNATURE_HEADER,
    SIGNATURE_MAX_AGE_SECONDS,
    TIMESTAMP_HEADER,
)
from .coordinator import FamilyLifeCoordinator
from .logic import verify_signature

_LOGGER = logging.getLogger(__name__)


async def _public_url(hass: HomeAssistant, webhook_id: str) -> str | None:
    if "cloud" in hass.config.components:
        try:
            from homeassistant.components import cloud  # noqa: PLC0415

            if cloud.async_active_subscription(hass):
                return await cloud.async_create_cloudhook(hass, webhook_id)
        except Exception:  # noqa: BLE001 - cloud not linked: fall through
            _LOGGER.debug("Cloudhook unavailable", exc_info=True)
    try:
        base = get_url(hass, allow_internal=False, allow_ip=False, require_ssl=True, require_standard_port=True)
    except NoURLAvailableError:
        return None
    return f"{base}{webhook.async_generate_path(webhook_id)}"


async def async_setup_push(hass: HomeAssistant, entry: ConfigEntry, coordinator: FamilyLifeCoordinator) -> None:
    """Register the webhook with Home Assistant and with Family Life (best effort)."""
    webhook_id = entry.data.get(CONF_WEBHOOK_ID) or webhook.async_generate_id()

    async def handle(hass: HomeAssistant, _id: str, request: web.Request) -> web.Response:
        body = await request.read()
        secret = entry.data.get(CONF_WEBHOOK_SECRET, "")
        if not verify_signature(
            secret, request.headers.get(TIMESTAMP_HEADER), request.headers.get(SIGNATURE_HEADER), body, max_age=SIGNATURE_MAX_AGE_SECONDS
        ):
            return web.Response(status=401)
        await coordinator.async_request_refresh()
        return web.Response(status=204)

    webhook.async_register(hass, DOMAIN, "Family Life", webhook_id, handle, allowed_methods=["POST"])
    entry.async_on_unload(lambda: webhook.async_unregister(hass, webhook_id))

    url = await _public_url(hass, webhook_id)
    if not url:
        _LOGGER.info("Family Life: no public https URL for this instance, refreshing every %s instead of push", coordinator.update_interval)
        return
    try:
        result = await coordinator.api.register_webhook(url)
    except FamilyLifeError as err:
        _LOGGER.info("Family Life push not enabled (%s); polling instead", err)
        return
    secret = (result or {}).get("secret")
    if secret:
        hass.config_entries.async_update_entry(entry, data={**entry.data, CONF_WEBHOOK_ID: webhook_id, CONF_WEBHOOK_SECRET: secret})
        coordinator.update_interval = SCAN_INTERVAL_WITH_PUSH
