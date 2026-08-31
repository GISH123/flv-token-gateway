# FLV Token Gateway

短效 Token 鑑權拉流 POC。此服務放在 Client/VLC 與內網 SRS / HTTP-FLV Source 之間，讓 Client 不直接使用原始 FLV URL，而是先申請短效 token，再透過 Gateway URL 拉流。

## Features

- FastAPI based token gateway
- HMAC-SHA256 signed token
- token binds exact stream path, expiry, and nonce
- tokenized HTTP-FLV pull stream
- reverse proxy streaming response; does not preload entire FLV into memory
- optional token issuer API key
- pytest coverage for token and gateway behavior

## Architecture

```text
Client / VLC
    |
    | POST /api/v1/tokens {stream_path}
    v
FLV Token Gateway
    |
    | GET upstream FLV
    v
SRS / FLV Source
```

## Quick Start

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
copy .env.example .env
python -m uvicorn app.main:app --host 127.0.0.1 --port 18088
```

Health check:

```powershell
curl http://127.0.0.1:18088/health
```

## Configuration

`.env` example:

```env
PUBLIC_BASE_URL=http://127.0.0.1:18088
UPSTREAM_BASE_URL=https://10.2.192.8:8088
TOKEN_SECRET=<long-random-secret>
TOKEN_TTL_SECONDS=300
TOKEN_ISSUER_API_KEY=
UPSTREAM_VERIFY_TLS=false
```

| Setting | Description |
|---|---|
| `PUBLIC_BASE_URL` | Gateway URL returned to clients. |
| `UPSTREAM_BASE_URL` | Internal FLV source URL. |
| `TOKEN_SECRET` | HMAC signing secret. Use a strong random value. |
| `TOKEN_TTL_SECONDS` | Token TTL in seconds. Default POC value: 300. |
| `TOKEN_ISSUER_API_KEY` | Optional API key required by token endpoint when non-empty. |
| `UPSTREAM_VERIFY_TLS` | Whether to verify upstream TLS certificate. |

## Issue Token

```powershell
$streamPath = "/gishtest/gish.flv"
$body = @{ stream_path = $streamPath } | ConvertTo-Json

$r = Invoke-RestMethod `
    -Method Post `
    -Uri "http://127.0.0.1:18088/api/v1/tokens" `
    -ContentType "application/json" `
    -Body $body

$r | Format-List token, expires_in, expires_at, stream_url
```

Response:

```json
{
  "token": "<TOKEN>",
  "expires_in": 300,
  "expires_at": 1788151441,
  "stream_url": "http://127.0.0.1:18088/gishtest/gish.flv?token=<TOKEN>"
}
```

## Play with VLC

Copy `stream_url` and open it in VLC:

```text
Media -> Open Network Stream -> paste stream_url -> Play
```

## Token Behavior

- Each `POST /api/v1/tokens` issues a new token.
- Tokens may look similar at the beginning because the payload contains the same path and similar expiry time.
- A newly issued token does not revoke previously issued tokens.
- The same token can be reused within its TTL.
- Token TTL is checked when establishing a connection. An already established FLV stream is not forcibly terminated at the TTL boundary.
- After expiry, reusing the same URL to establish a new connection should return 403.

This is a stateless POC design. One-time token, revoke, replay protection, allowlist, and audit log are production hardening items.

## Error Behavior

| Condition | HTTP Status |
|---|---:|
| Missing token | 401 |
| Expired token | 403 |
| Tampered token | 403 |
| Path mismatch | 403 |
| Valid token | Streaming response |

## Tests

```powershell
python -m pytest -q
```

Current POC coverage includes:

1. valid token verification
2. expiry rejection
3. path binding rejection
4. tamper rejection
5. no-token stream request -> 401
6. valid token streams upstream response
7. token endpoint returns stream URL and TTL
8. optional API key check for token endpoint

## Production Hardening

Recommended before production:

- require `TOKEN_ISSUER_API_KEY` or integrate with internal identity service
- stream path allowlist
- rate limit token endpoint
- one-time token / replay protection with Redis or DB
- token revoke support
- audit log for token issue, reject reason, upstream failures
- TLS certificate validation in production
