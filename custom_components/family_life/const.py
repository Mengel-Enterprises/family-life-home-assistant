"""Constants for the Family Life integration."""

from __future__ import annotations

from datetime import timedelta
from typing import Final

DOMAIN: Final = "family_life"

CONF_SERVER: Final = "server"
CONF_API_BASE: Final = "api_base"
CONF_METADATA: Final = "metadata"
CONF_WEBHOOK_ID: Final = "webhook_id"
CONF_WEBHOOK_SECRET: Final = "webhook_secret"

# The Family Life API host suggested in the setup form. The user can change it (staging, or a
# future host); every endpoint and the OAuth client id are then DISCOVERED from that host's
# /family-life/oauth/metadata document, so nothing else about the service is built in here.
SUGGESTED_SERVER: Final = "https://api.mengelenterprises.com"

SCOPES: Final = (
    "calendar:read calendar:write chores:read chores:write lists:read lists:write members:read"
)

# Polling: frequent enough for a wall dashboard without push; relaxed once push is registered.
SCAN_INTERVAL: Final = timedelta(minutes=5)
SCAN_INTERVAL_WITH_PUSH: Final = timedelta(minutes=30)
BOARD_DAYS: Final = 14

# Webhook signature (the platform's signer): X-Platform-Signature-V2 = "sha256=" + HMAC-SHA256
# of "<X-Platform-Timestamp>.<raw body>". Deliveries older than this are refused (replay).
SIGNATURE_HEADER: Final = "X-Platform-Signature-V2"
TIMESTAMP_HEADER: Final = "X-Platform-Timestamp"
SIGNATURE_MAX_AGE_SECONDS: Final = 300

PLATFORMS: Final = ["calendar", "sensor", "todo"]
