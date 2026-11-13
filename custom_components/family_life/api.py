"""Family Life API client (OAuth2 session) and the PKCE OAuth implementation."""

from __future__ import annotations

from datetime import datetime
import logging
from typing import Any

from aiohttp import ClientError, ClientResponse, ClientSession
from yarl import URL

from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_entry_oauth2_flow
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import DOMAIN, SCOPES
from .logic import metadata_candidates, pkce_pair

_LOGGER = logging.getLogger(__name__)


class FamilyLifeError(Exception):
    """A Family Life API call failed."""


class FamilyLifeAuthError(FamilyLifeError):
    """The connection is no longer valid (revoked, plan changed, parent removed)."""


async def async_fetch_metadata(session: ClientSession, server: str) -> dict[str, Any]:
    """Discover the endpoints and the Home Assistant client id from the server."""
    last: Exception | None = None
    for url in metadata_candidates(server):
        try:
            async with session.get(url, timeout=15) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get("authorization_endpoint") and data.get("home_assistant", {}).get("client_id"):
                        return data
                last = FamilyLifeError(f"{url} answered {resp.status}")
        except (ClientError, TimeoutError, ValueError) as err:
            last = err
    raise FamilyLifeError(f"Could not discover Family Life at {server}: {last}")


class FamilyLifeImplementation(config_entry_oauth2_flow.LocalOAuth2Implementation):
    """Public OAuth client with PKCE (S256); endpoints and client id come from discovery."""

    def __init__(self, hass: HomeAssistant, metadata: dict[str, Any]) -> None:
        """Build from the server's metadata document."""
        super().__init__(
            hass,
            DOMAIN,
            metadata["home_assistant"]["client_id"],
            "",
            metadata["authorization_endpoint"],
            metadata["token_endpoint"],
        )

    @property
    def name(self) -> str:
        """Shown in the implementation picker."""
        return "Family Life"

    async def async_generate_authorize_url(self, flow_id: str) -> str:
        """Authorize URL with a per-flow PKCE challenge; the verifier rides in the signed state."""
        redirect_uri = self.redirect_uri
        verifier, challenge = pkce_pair()
        state = config_entry_oauth2_flow._encode_jwt(  # noqa: SLF001 - same helper core's PKCE implementation uses
            self.hass, {"flow_id": flow_id, "redirect_uri": redirect_uri, "code_verifier": verifier}
        )
        return str(
            URL(self.authorize_url).with_query(
                {
                    "response_type": "code",
                    "client_id": self.client_id,
                    "redirect_uri": redirect_uri,
                    "state": state,
                    "scope": SCOPES,
                    "code_challenge": challenge,
                    "code_challenge_method": "S256",
                }
            )
        )

    async def async_resolve_external_data(self, external_data: Any) -> dict:
        """Exchange the code, presenting the verifier from the state."""
        return await self._token_request(
            {
                "grant_type": "authorization_code",
                "code": external_data["code"],
                "redirect_uri": external_data["state"]["redirect_uri"],
                "code_verifier": external_data["state"]["code_verifier"],
            }
        )

    async def _token_request(self, data: dict) -> dict:
        """POST to the token endpoint as a public client (no client secret)."""
        session = async_get_clientsession(self.hass)
        data["client_id"] = self.client_id
        resp = await session.post(self.token_url, data=data)
        if resp.status >= 400:
            try:
                body = await resp.json()
            except ValueError:
                body = {}
            _LOGGER.debug("Family Life token endpoint refused: %s %s", resp.status, body.get("error"))
            if resp.status in (400, 401):
                # invalid_grant: revoked, reused, plan or role changed -> Home Assistant asks to re-authenticate.
                raise FamilyLifeAuthError(body.get("error_description") or "Sign-in refused")
        resp.raise_for_status()
        return await resp.json()


class FamilyLifeApi:
    """Thin client over the Family Life routes Home Assistant uses."""

    def __init__(self, oauth_session: config_entry_oauth2_flow.OAuth2Session, api_base: str) -> None:
        """api_base is '<host>[/api]/family-life'."""
        self._oauth = oauth_session
        self._base = api_base.rstrip("/")

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        try:
            await self._oauth.async_ensure_token_valid()
        except ClientError as err:
            raise FamilyLifeError(str(err)) from err
        try:
            resp: ClientResponse = await self._oauth.async_request(method, f"{self._base}{path}", **kwargs)
        except ClientError as err:
            raise FamilyLifeError(str(err)) from err
        if resp.status == 401:
            raise FamilyLifeAuthError("Family Life connection is no longer valid")
        try:
            body = await resp.json()
        except (ValueError, ClientError):
            body = {}
        if resp.status >= 400:
            raise FamilyLifeError(body.get("error") or f"HTTP {resp.status}")
        return body.get("data") if isinstance(body, dict) and "data" in body else body

    # reads ---------------------------------------------------------------
    async def board(self, days: int) -> dict[str, Any]:
        return await self._request("get", f"/hub/board?days={days}")

    async def me(self) -> dict[str, Any]:
        return await self._request("get", "/oauth/me")

    async def events(self, start: datetime, end: datetime) -> list[dict[str, Any]]:
        q = URL.build(query={"startDate": start.isoformat(), "endDate": end.isoformat()}).query_string
        return await self._request("get", f"/calendar/events?{q}") or []

    # writes --------------------------------------------------------------
    async def create_event(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await self._request("post", "/calendar/events", json=payload)

    async def delete_event(self, event_id: str) -> None:
        await self._request("delete", f"/calendar/events/{event_id}")

    async def add_item(self, list_id: str, text: str) -> None:
        await self._request("post", f"/lists/{list_id}/items", json={"text": text})

    async def update_item(self, list_id: str, item_id: str, patch: dict[str, Any]) -> None:
        await self._request("put", f"/lists/{list_id}/items/{item_id}", json=patch)

    async def delete_item(self, list_id: str, item_id: str) -> None:
        await self._request("delete", f"/lists/{list_id}/items/{item_id}")

    async def create_chore(self, title: str, assignee: str | None, due: str | None) -> None:
        await self._request("post", "/chores", json={"title": title, "assigneeMemberId": assignee, "dueDate": due})

    async def update_chore(self, chore_id: str, patch: dict[str, Any]) -> None:
        await self._request("put", f"/chores/{chore_id}", json=patch)

    async def complete_chore(self, chore_id: str) -> None:
        await self._request("post", f"/chores/{chore_id}/complete")

    async def delete_chore(self, chore_id: str) -> None:
        await self._request("delete", f"/chores/{chore_id}")

    async def register_webhook(self, url: str | None) -> dict[str, Any]:
        return await self._request("post", "/oauth/webhook", json={"url": url})
