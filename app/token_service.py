import base64
import hashlib
import hmac
import json
import secrets
import time
from dataclasses import dataclass


class TokenError(ValueError):
    pass


class TokenExpired(TokenError):
    pass


@dataclass(frozen=True)
class TokenClaims:
    path: str
    expires_at: int
    nonce: str


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64url_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    try:
        return base64.urlsafe_b64decode(value + padding)
    except Exception as exc:  # pragma: no cover - defensive
        raise TokenError("malformed base64") from exc


def issue_token(path: str, secret: str, ttl_seconds: int, now: int | None = None) -> tuple[str, TokenClaims]:
    if not path.startswith("/") or not path.lower().endswith(".flv"):
        raise TokenError("stream path must start with '/' and end with '.flv'")

    issued_at = int(time.time() if now is None else now)
    claims = TokenClaims(path=path, expires_at=issued_at + ttl_seconds, nonce=secrets.token_urlsafe(8))
    payload = {"p": claims.path, "exp": claims.expires_at, "n": claims.nonce}
    payload_b64 = _b64url_encode(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    signature = hmac.new(secret.encode("utf-8"), payload_b64.encode("ascii"), hashlib.sha256).digest()
    return f"{payload_b64}.{_b64url_encode(signature)}", claims


def verify_token(token: str, requested_path: str, secret: str, now: int | None = None) -> TokenClaims:
    try:
        payload_b64, signature_b64 = token.split(".", 1)
    except ValueError as exc:
        raise TokenError("malformed token") from exc

    expected = hmac.new(secret.encode("utf-8"), payload_b64.encode("ascii"), hashlib.sha256).digest()
    supplied = _b64url_decode(signature_b64)
    if not hmac.compare_digest(expected, supplied):
        raise TokenError("invalid signature")

    try:
        payload = json.loads(_b64url_decode(payload_b64))
        claims = TokenClaims(path=str(payload["p"]), expires_at=int(payload["exp"]), nonce=str(payload["n"]))
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise TokenError("invalid claims") from exc

    current = int(time.time() if now is None else now)
    if current >= claims.expires_at:
        raise TokenExpired("token expired")
    if claims.path != requested_path:
        raise TokenError("token does not match requested stream")
    return claims
