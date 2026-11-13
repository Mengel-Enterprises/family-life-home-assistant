"""One coordinator per family: the board (calendar, chores, lists, members) in one read."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import FamilyLifeApi, FamilyLifeAuthError, FamilyLifeError
from .const import BOARD_DAYS, DOMAIN, SCAN_INTERVAL

_LOGGER = logging.getLogger(__name__)


class FamilyLifeCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Polls GET family-life/hub/board; a push from Family Life triggers an immediate refresh."""

    config_entry: ConfigEntry

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, api: FamilyLifeApi) -> None:
        """Initialize."""
        super().__init__(hass, _LOGGER, config_entry=entry, name=DOMAIN, update_interval=SCAN_INTERVAL)
        self.api = api

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            return await self.api.board(BOARD_DAYS)
        except FamilyLifeAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except FamilyLifeError as err:
            raise UpdateFailed(str(err)) from err
