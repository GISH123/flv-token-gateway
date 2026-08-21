import pytest

from app.token_service import TokenError, TokenExpired, issue_token, verify_token


SECRET = "0123456789abcdef0123456789abcdef"


def test_token_is_valid_for_exact_path_before_expiry():
    token, claims = issue_token("/dev/liveB03.flv", SECRET, ttl_seconds=300, now=1_000)
    parsed = verify_token(token, "/dev/liveB03.flv", SECRET, now=1_299)
    assert parsed.path == claims.path
    assert parsed.expires_at == 1_300


def test_token_expires_at_exact_expiry_time():
    token, _ = issue_token("/dev/liveB03.flv", SECRET, ttl_seconds=300, now=1_000)
    with pytest.raises(TokenExpired):
        verify_token(token, "/dev/liveB03.flv", SECRET, now=1_300)


def test_token_cannot_be_reused_for_another_stream():
    token, _ = issue_token("/dev/liveB03.flv", SECRET, ttl_seconds=300, now=1_000)
    with pytest.raises(TokenError):
        verify_token(token, "/dev/liveB04.flv", SECRET, now=1_001)


def test_tampered_token_is_rejected():
    token, _ = issue_token("/dev/liveB03.flv", SECRET, ttl_seconds=300, now=1_000)
    payload, signature = token.split(".")
    tampered = payload + "." + ("A" if signature[0] != "A" else "B") + signature[1:]
    with pytest.raises(TokenError):
        verify_token(tampered, "/dev/liveB03.flv", SECRET, now=1_001)
