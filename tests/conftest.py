"""Fixtures for the Family Life integration tests."""

from __future__ import annotations

import pytest

pytest_plugins = "pytest_homeassistant_custom_component"

SERVER = "https://api.familylife.test"
API_BASE = f"{SERVER}/api/family-life"
METADATA = {
    "issuer": f"{SERVER}/api",
    "authorization_endpoint": f"{API_BASE}/oauth/authorize",
    "token_endpoint": f"{API_BASE}/oauth/token",
    "revocation_endpoint": f"{API_BASE}/oauth/revoke",
    "home_assistant": {"client_id": "ha-test-client"},
    "api_base": API_BASE,
}
BOARD = {
    "generatedAt": "2026-11-12T08:00:00Z",
    "display": {"name": "Family hub", "kind": "member"},
    "members": [{"id": "m1", "name": "Sam", "color": "#ff0000"}],
    "events": [
        {"id": "e1", "title": "Soccer", "startDate": "2099-01-01T16:00:00Z", "endDate": "2099-01-01T17:00:00Z", "allDay": False, "memberId": "m1", "source": "app"},
    ],
    "chores": [{"id": "c1", "title": "Feed cat", "assigneeMemberId": "m1", "dueDate": "2000-01-01", "recurrence": "daily", "status": "open"}],
    "lists": [{"id": "l1", "name": "Groceries", "kind": "shopping", "items": [{"id": "i1", "text": "Milk", "checked": False}]}],
    "reminders": [],
}


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Load custom_components/family_life."""
    return
