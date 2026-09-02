# FLV Token Gateway

短效 Token 鑑權 HTTP-FLV reverse proxy。

此服務放在 Client / Browser Player / VLC 與內網 SRS HTTP-FLV Source 之間。Client 不直接使用 upstream FLV URL，而是先向 Gateway 申請短效 token，再透過 Gateway URL 拉流。

## Features

- FastAPI token gateway
- HMAC-SHA256 signed token
- token binds exact stream path, expiry, and nonce
- reverse-proxy HTTP-FLV streaming
- optional token issuer API key
- LAN listener configurable from `.env`
- browser-player CORS configurable from `.env`
- browser `Range` request forwarding and response range-header passthrough
- bundled Test UI reads defaults from the same `.env`

## Architecture

```text
Client / VLC / Browser Player
        |
        | POST /api/v1/tokens {stream_path}
        v
FLV Token Gateway
        |
        | server-side GET upstream FLV
        v
SRS / FLV Source
```

Current intranet example:

```text
Browser / Client
    |
    | http://10.2.192.9:18088
    v
FLV Token Gateway (10.2.192.9)
    |
    | https://10.2.192.8:8088/<stream_path>
    v
SRS HTTP-FLV Source (10.2.192.8)
```

OBS example:

```text
rtmp://10.2.192.8/gishtest
stream key: gish
HTTP-FLV path: /gishtest/gish.flv
```

## Quick Start

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
copy .env.example .env
python -m app.server
```

Health check:

```powershell
curl http://127.0.0.1:18088/health
```

`run_local_demo.bat` starts a deterministic localhost demo:

```text
Gateway       http://127.0.0.1:18088
Mock upstream http://127.0.0.1:9090
```

The local demo overrides deployment-specific `.env` values only for that process.

## Configuration

```env
GATEWAY_HOST=0.0.0.0
GATEWAY_PORT=18088
GATEWAY_LOG_LEVEL=info

PUBLIC_BASE_URL=http://10.2.192.9:18088
UPSTREAM_BASE_URL=https://10.2.192.8:8088

TOKEN_SECRET=<long-random-secret>
TOKEN_TTL_SECONDS=300
TOKEN_ISSUER_API_KEY=
UPSTREAM_VERIFY_TLS=false

CORS_ALLOW_ORIGINS=*
TEST_STREAM_PATH=/gishtest/gish.flv
```

| Setting | Description |
|---|---|
| `GATEWAY_HOST` | Listener bind address. `0.0.0.0` accepts connections on all local interfaces. |
| `GATEWAY_PORT` | Gateway listener port. Default: `18088`. |
| `GATEWAY_LOG_LEVEL` | Uvicorn log level. |
| `PUBLIC_BASE_URL` | Gateway URL returned to clients. Must be reachable by clients. |
| `UPSTREAM_BASE_URL` | Internal HTTP-FLV source origin. Server-side only. |
| `TOKEN_SECRET` | HMAC signing secret. Never commit the real `.env`. |
| `TOKEN_TTL_SECONDS` | Token TTL in seconds. POC value: 300. |
| `TOKEN_ISSUER_API_KEY` | Optional API key required by the token endpoint when non-empty. |
| `UPSTREAM_VERIFY_TLS` | Whether to verify the upstream TLS certificate. |
| `CORS_ALLOW_ORIGINS` | Comma-separated browser origins, or `*` for POC/demo. |
| `TEST_STREAM_PATH` | Initial stream path shown by the bundled Test UI. |

`GATEWAY_HOST=0.0.0.0` controls where the process listens. `PUBLIC_BASE_URL` controls what URL clients receive. Do not use `0.0.0.0` as `PUBLIC_BASE_URL`.

## Issue Token

```powershell
$body = @{ stream_path = "/gishtest/gish.flv" } | ConvertTo-Json
$r = Invoke-RestMethod `
  -Method Post `
  -Uri "http://10.2.192.9:18088/api/v1/tokens" `
  -ContentType "application/json" `
  -Body $body
$r | Format-List token, expires_in, expires_at, stream_url
```

Typical `stream_url`:

```text
http://10.2.192.9:18088/gishtest/gish.flv?token=<TOKEN>
```

The client sees the Gateway address. The normal token response does not contain `UPSTREAM_BASE_URL`.

## VLC

Use the returned `stream_url` in VLC. VLC is not subject to browser CORS policy.

## Browser Player / CORS

Example player:

```text
http://10.2.192.8:8080/players/srs_player.html
```

Gateway FLV:

```text
http://10.2.192.9:18088/gishtest/gish.flv?token=...
```

These are different origins, so browser playback requires CORS headers.

POC/demo:

```env
CORS_ALLOW_ORIGINS=*
```

Restricted deployment:

```env
CORS_ALLOW_ORIGINS=http://10.2.192.8:8080
```

Browser `Range` requests are forwarded to the upstream. `Content-Range` and `Accept-Ranges` are passed back when provided by the upstream.

## Source URL Exposure and Origin Bypass

The Gateway is a reverse proxy, not an HTTP redirect. It validates the token and performs the upstream request server-side.

The token response exposes the **Gateway** address, not the configured `UPSTREAM_BASE_URL`.

However, hiding an upstream IP or port is **not** a security boundary. If clients can reach the source network, they may discover the source host/port through another service, configuration knowledge, or port scanning. For example, a player served from `http://10.2.192.8:8080` already reveals the source host IP.

Production deployment must therefore protect the source at the network layer.

Recommended current topology:

```text
10.2.192.9    -> 10.2.192.8:8088   ALLOW
other clients -> 10.2.192.8:8088   DENY
```

The player port may remain separately reachable if required:

```text
clients -> 10.2.192.8:8080         ALLOW
```

Then even if someone guesses:

```text
https://10.2.192.8:8088/gishtest/gish.flv
```

they still cannot bypass the Gateway unless their source host is explicitly allowed.

If the source host itself must not be visible to viewers, serve the web player through the Gateway/reverse-proxy side as well.

## Token Behavior

- each token binds the exact stream path
- token expiry is checked when establishing a connection
- already-established streams are not forcibly cut exactly at the TTL boundary
- expired/tampered/path-mismatched tokens are rejected
- this POC does not implement one-time token or replay prevention

## Tests

```powershell
python -m pytest -q
```

With local demo running:

```powershell
python .\scripts\smoke_test.py http://127.0.0.1:18088
```

CORS preflight:

```powershell
curl.exe -i -X OPTIONS `
  -H "Origin: http://10.2.192.8:8080" `
  -H "Access-Control-Request-Method: GET" `
  http://127.0.0.1:18088/gishtest/gish.flv
```

The local mock upstream proves token/proxy byte flow, not real OBS/SRS video playback. Real OBS + SRS + browser playback must be verified inside the intranet.

## PyInstaller Release

```powershell
python -m PyInstaller --clean --noconfirm FLVTokenGateway_v04_sslfix.spec
```

`.env` remains external and editable beside the EXE. Source mode, EXE server, and Test UI share the same configuration model.

## Production Hardening

- protect source port `8088` with firewall/ACL; do not rely on hidden IP/port
- restrict `CORS_ALLOW_ORIGINS` instead of `*`
- require `TOKEN_ISSUER_API_KEY` or internal identity
- stream path allowlist
- token issuance rate limit
- one-time token / replay prevention
- token revoke
- audit logging
- public Gateway TLS
- proper upstream certificate validation
- optionally serve the browser player behind the Gateway/reverse proxy
