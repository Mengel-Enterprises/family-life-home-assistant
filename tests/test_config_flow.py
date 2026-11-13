"""Config flow: discovery -> PKCE authorize URL -> token exchange -> entry (once per family)."""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

import pytest

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import config_entry_oauth2_flow

from custom_components.family_life.const import DOMAIN

from .conftest import API_BASE, METADATA, SERVER


async def _start(hass: HomeAssistant, aioclient_mock) -> dict:
    aioclient_mock.get(f"{SERVER}/api/family-life/oauth/metadata", json=METADATA)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    assert result["type"] is FlowResultType.FORM
    return await hass.config_entries.flow.async_configure(result["flow_id"], {"server": SERVER})


@pytest.mark.usefixtures("current_request_with_host")
async def test_full_flow(hass: HomeAssistant, hass_client_no_auth, aioclient_mock) -> None:
    """The authorize URL carries S256 PKCE and our scopes; the verifier reaches the token call."""
    result = await _start(hass, aioclient_mock)
    assert result["type"] is FlowResultType.EXTERNAL_STEP
    url = urlparse(result["url"])
    q = parse_qs(url.query)
    assert f"{url.scheme}://{url.netloc}{url.path}" == METADATA["authorization_endpoint"]
    assert q["client_id"] == ["ha-test-client"]
    assert q["code_challenge_method"] == ["S256"]
    assert "chores:write" in q["scope"][0]
    state = q["state"][0]

    client = await hass_client_no_auth()
    resp = await client.get(f"/auth/external/callback?code=flo_ac.abc&state={state}")
    assert resp.status == 200

    aioclient_mock.post(METADATA["token_endpoint"], json={"access_token": "flo_at.x.y", "refresh_token": "flo_rt.x.y", "token_type": "Bearer", "expires_in": 3600})
    aioclient_mock.get(f"{API_BASE}/oauth/me", json={"success": True, "data": {"familyKey": "fam-key-1", "scopes": []}})
    aioclient_mock.get(f"{API_BASE}/hub/board?days=14", json={"success": True, "data": {"members": [], "events": [], "chores": [], "lists": [], "reminders": []}})
    aioclient_mock.post(f"{API_BASE}/oauth/webhook", status=400, json={"success": False})

    result = await hass.config_entries.flow.async_configure(result["flow_id"])
    assert result["type"] is FlowResultType.CREATE_ENTRY
    entry = result["result"]
    assert entry.unique_id == "fam-key-1"
    assert entry.data["api_base"] == API_BASE

    token_call = next(c for c in aioclient_mock.mock_calls if str(c[1]) == METADATA["token_endpoint"])
    sent = token_call[2]
    assert sent["grant_type"] == "authorization_code"
    assert sent["client_id"] == "ha-test-client"
    assert len(sent["code_verifier"]) >= 43


async def test_unreachable_server_shows_an_error(hass: HomeAssistant, aioclient_mock) -> None:
    """Discovery failure keeps the user on the form."""
    aioclient_mock.get(f"{SERVER}/api/family-life/oauth/metadata", status=503)
    aioclient_mock.get(f"{SERVER}/family-life/oauth/metadata", status=404)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"server": SERVER})
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


def test_implementation_is_registered_under_the_domain(hass: HomeAssistant) -> None:
    """Sanity: the implementation key the flow picks is the domain."""
    from custom_components.family_life.api import FamilyLifeImplementation

    impl = FamilyLifeImplementation(hass, METADATA)
    assert impl.domain == DOMAIN
    assert isinstance(impl, config_entry_oauth2_flow.LocalOAuth2Implementation)
