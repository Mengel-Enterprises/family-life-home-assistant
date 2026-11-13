"""Pure helpers for the Family Life integration (no Home Assistant imports, unit-testable)."""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import time
from datetime import date, datetime
from typing import Any


def pkce_pair() -> tuple[str, str]:
    """Return (code_verifier, S256 code_challenge) per RFC 7636."""
    verifier = secrets.token_urlsafe(64)[:96]
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge


def verify_signature(
    secret: str, timestamp: str | None, signature: str | None, body: bytes, *, max_age: int, now: float | None = None
) -> bool:
    """Check a Family Life push: HMAC-SHA256 of "<ts>.<body>", fresh within max_age seconds."""
    if not secret or not timestamp or not signature or not signature.startswith("sha256="):
        return False
    try:
        ts = int(timestamp)
    except ValueError:
        return False
    current = time.time() if now is None else now
    if abs(current - ts) > max_age:
        return False
    expected = hmac.new(secret.encode(), f"{timestamp}.".encode() + body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(f"sha256={expected}", signature)


def metadata_candidates(server: str) -> list[str]:
    """URLs to try for the discovery document: the host behind an /api prefix, then without."""
    base = server.strip().rstrip("/")
    if base.endswith("/family-life"):
        base = base[: -len("/family-life")]
    if base.endswith("/api"):
        return [f"{base}/family-life/oauth/metadata"]
    return [f"{base}/api/family-life/oauth/metadata", f"{base}/family-life/oauth/metadata"]


def parse_iso(value: str | None) -> datetime | None:
    """Parse an ISO-8601 timestamp (with Z) into an aware datetime."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def parse_day(value: str | None) -> date | None:
    """Parse YYYY-MM-DD (or the date part of an ISO timestamp)."""
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def member_name(board: dict[str, Any], member_id: str | None) -> str:
    """The display name of a member on the board, or 'Anyone'."""
    for m in board.get("members", []):
        if m.get("id") == member_id:
            return m.get("name") or "Member"
    return "Anyone"


def chores_for(board: dict[str, Any], member_id: str | None) -> list[dict[str, Any]]:
    """Open chores assigned to member_id (None = unassigned)."""
    return [c for c in board.get("chores", []) if (c.get("assigneeMemberId") or None) == member_id]


def chores_due_today(board: dict[str, Any], member_id: str | None, today: date) -> int:
    """Open chores for member_id due today or earlier (or with no date)."""
    n = 0
    for c in chores_for(board, member_id):
        due = parse_day(c.get("dueDate"))
        if due is None or due <= today:
            n += 1
    return n


def overdue_chores(board: dict[str, Any], today: date) -> int:
    """Open chores whose due date has passed."""
    return sum(1 for c in board.get("chores", []) if (d := parse_day(c.get("dueDate"))) is not None and d < today)


def event_belongs_to(event: dict[str, Any], member_id: str) -> bool:
    """Is this event one member's (assigned to them, or owned by them)?"""
    return event.get("memberId") == member_id or event.get("ownerMemberId") == member_id
