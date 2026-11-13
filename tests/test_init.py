"""Setup from a stored entry: entities from the board; to-do actions call Family Life."""

from __future__ import annotations

import time

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.family_life.const import DOMAIN

from .conftest import API_BASE, BOARD, METADATA, SERVER


def _entry() -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        unique_id="fam-key-1",
        data={
            "auth_implementation": DOMAIN,
            "token": {"access_token": "flo_at.x.y", "refresh_token": "flo_rt.x.y", "expires_at": time.time() + 3600, "token_type": "Bearer"},
            "server": SERVER,
            "api_base": API_BASE,
            "metadata": METADATA,
        },
    )


async def test_setup_creates_calendar_todo_and_sensors(hass: HomeAssistant, aioclient_mock) -> None:
    """One read of the board creates every entity; a to-do check calls the list item route."""
    aioclient_mock.get(f"{API_BASE}/hub/board?days=14", json={"success": True, "data": BOARD})
    aioclient_mock.post(f"{API_BASE}/oauth/webhook", status=400, json={"success": False})
    entry = _entry()
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED

    states = {s.entity_id: s for s in hass.states.async_all()}
    assert any(e.startswith("calendar.") and "family" in e for e in states)
    groceries = next(s for e, s in states.items() if e.startswith("todo.") and "groceries" in e)
    assert groceries.state == "1"
    sam_chores = next(s for e, s in states.items() if e.startswith("todo.") and "sam" in e)
    assert sam_chores.state == "1"
    overdue = next(s for e, s in states.items() if e.startswith("sensor.") and "overdue" in e)
    assert overdue.state == "1"

    aioclient_mock.put(f"{API_BASE}/lists/l1/items/i1", json={"success": True, "data": {}})
    await hass.services.async_call("todo", "update_item", {"item": "Milk", "status": "completed"}, target={"entity_id": groceries.entity_id}, blocking=True)
    put = next(c for c in aioclient_mock.mock_calls if str(c[0]).upper() == "PUT")
    assert put[2] == {"checked": True}


async def test_revoked_connection_asks_to_reauthenticate(hass: HomeAssistant, aioclient_mock) -> None:
    """A 401 from Family Life (disconnected in Settings, plan changed) starts reauth, not a retry loop."""
    aioclient_mock.get(f"{API_BASE}/hub/board?days=14", status=401, json={"success": False})
    entry = _entry()
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.SETUP_ERROR
    assert any(f["context"]["source"] == "reauth" for f in hass.config_entries.flow.async_progress())
