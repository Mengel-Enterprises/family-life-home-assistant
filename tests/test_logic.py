"""Pure helpers: signature verification, PKCE, discovery URLs, chore counts (no Home Assistant needed)."""

from __future__ import annotations

import base64
from datetime import date
import hashlib
import hmac
import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location("fl_logic", Path(__file__).parents[1] / "custom_components" / "family_life" / "logic.py")
logic = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(logic)  # type: ignore[union-attr]


def _sign(secret: str, ts: str, body: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode(), f"{ts}.".encode() + body, hashlib.sha256).hexdigest()


def test_signature_accepts_a_fresh_correct_signature() -> None:
    body = b'{"area":"lists"}'
    assert logic.verify_signature("s3cret", "1000", _sign("s3cret", "1000", body), body, max_age=300, now=1100)


def test_signature_refuses_wrong_secret_tampered_body_stale_and_malformed() -> None:
    body = b'{"area":"lists"}'
    good = _sign("s3cret", "1000", body)
    assert not logic.verify_signature("other", "1000", good, body, max_age=300, now=1100)
    assert not logic.verify_signature("s3cret", "1000", good, b'{"area":"chores"}', max_age=300, now=1100)
    assert not logic.verify_signature("s3cret", "1000", good, body, max_age=300, now=2000)
    assert not logic.verify_signature("s3cret", "abc", good, body, max_age=300, now=1100)
    assert not logic.verify_signature("s3cret", "1000", good[7:], body, max_age=300, now=1100)
    assert not logic.verify_signature("", "1000", good, body, max_age=300, now=1100)


def test_pkce_pair_is_s256_and_in_the_verifier_alphabet() -> None:
    verifier, challenge = logic.pkce_pair()
    assert 43 <= len(verifier) <= 128
    expected = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    assert challenge == expected


def test_metadata_candidates_handle_api_prefix_and_trailing_parts() -> None:
    assert logic.metadata_candidates("https://api.example.com/") == [
        "https://api.example.com/api/family-life/oauth/metadata",
        "https://api.example.com/family-life/oauth/metadata",
    ]
    assert logic.metadata_candidates("https://api.example.com/api") == ["https://api.example.com/api/family-life/oauth/metadata"]
    assert logic.metadata_candidates("https://api.example.com/api/family-life") == ["https://api.example.com/api/family-life/oauth/metadata"]


BOARD = {
    "members": [{"id": "m1", "name": "Sam"}],
    "chores": [
        {"id": "c1", "assigneeMemberId": "m1", "dueDate": "2026-11-10"},
        {"id": "c2", "assigneeMemberId": "m1", "dueDate": "2026-11-12"},
        {"id": "c3", "assigneeMemberId": "m1", "dueDate": "2026-11-14"},
        {"id": "c4", "assigneeMemberId": None, "dueDate": None},
    ],
}


def test_chore_counts() -> None:
    today = date(2026, 11, 12)
    assert logic.chores_due_today(BOARD, "m1", today) == 2
    assert logic.chores_due_today(BOARD, None, today) == 1
    assert logic.overdue_chores(BOARD, today) == 1
    assert [c["id"] for c in logic.chores_for(BOARD, None)] == ["c4"]
    assert logic.member_name(BOARD, "m1") == "Sam"
    assert logic.member_name(BOARD, None) == "Anyone"
