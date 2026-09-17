# FLV Token Gateway — Why the HTTP/HTTPS Architecture Was Adjusted

## Background

The previous design treated HTTPS as the only real Gateway endpoint. HTTP `:18080` existed only to return a `308 Permanent Redirect` to HTTPS `:18088`.

```text
Client
  |
  | HTTP :18080
  v
Redirect-only listener
  |
  | 308
  v
HTTPS :18088
  |
  +-- /health
  +-- /api/v1/tokens
  +-- /player
  +-- protected FLV proxy
```

That was an intentional design. The original assumption was:

> HTTP is only a compatibility entry point; HTTPS is the canonical production service.

This follows the common web deployment model `HTTP :80 -> HTTPS :443`, mapped here to `18080 -> 18088`.

## Why the original design made sense

First, the token is an access credential. If the token API and token-bearing stream URL use plain HTTP, the credential is transported without TLS protection. For PRD, forcing HTTPS therefore makes sense.

Second, one canonical URL keeps configuration and troubleshooting simpler. With `PUBLIC_BASE_URL=https://<gateway>:18088`, every token response returns the same protocol and port.

Third, redirect-only HTTP avoids maintaining two independent application entry points. All real behavior—token issuance, validation, player, CORS, Range forwarding, proxying, and error handling—lives on HTTPS.

## What changed

The deployment requirement was clarified:

```text
PRD: HTTPS is required.
UAT: HTTP may be used.
Both protocols should be supported for testing.
```

That is a different contract.

Old assumption:

```text
HTTP = compatibility / redirect only
HTTPS = real Gateway
```

Clarified requirement:

```text
HTTP = first-class Gateway protocol for UAT
HTTPS = first-class Gateway protocol for PRD
```

Once HTTP itself is an intended UAT operating mode, redirecting every HTTP request to HTTPS is no longer appropriate.

## Why the redirect caused browser trouble

Browser origin is determined by:

```text
scheme + host + port
```

Therefore these are different origins:

```text
http://10.2.192.9:18080
https://10.2.192.9:18088
```

The old token flow could become:

```text
Browser
  |
  | fetch HTTP token API
  v
http://10.2.192.9:18080/api/v1/tokens
  |
  | 308 redirect
  v
https://10.2.192.9:18088/api/v1/tokens
```

That introduces unnecessary concerns for an HTTP UAT environment:

- CORS / cross-origin behavior
- self-signed certificate trust
- redirected `fetch()` behavior
- HTTPS certificate setup even though UAT intentionally uses HTTP

## New architecture

Both listeners are now real Gateway endpoints:

```text
                    +--> HTTP :18080  --> Full Gateway
Client / Player ----|
                    +--> HTTPS :18088 --> Full Gateway
```

Both expose the same application behavior:

```text
/health
/api/v1/tokens
/player
/assets/flv.min.js
/*.flv protected reverse proxy
```

There is no application-level HTTP -> HTTPS redirect.

## Token URL behavior

A token issued through HTTP returns an HTTP stream URL:

```text
GET http://10.2.192.9:18080/api/v1/tokens?stream_path=/gishtest/gish.flv

-> http://10.2.192.9:18080/gishtest/gish.flv?token=...
```

A token issued through HTTPS returns an HTTPS stream URL:

```text
GET https://10.2.192.9:18088/api/v1/tokens?stream_path=/gishtest/gish.flv

-> https://10.2.192.9:18088/gishtest/gish.flv?token=...
```

This keeps each browser/player flow same-origin.

## Why each listener gets its own FastAPI app instance

The application lifespan creates an upstream `httpx.AsyncClient` and stores it in `app.state.upstream_client`.

Running two Uvicorn servers against one shared FastAPI instance would make both servers operate on the same lifecycle state. That creates avoidable risk around startup, shutdown, and upstream-client ownership.

Therefore the adjusted startup creates two app instances:

```text
HTTP listener  -> create_app(settings)
HTTPS listener -> create_app(settings)
```

The listeners still share the same configuration and token secret, but their runtime lifecycle state is independent.

## Deployment modes

### UAT — HTTP only

```env
GATEWAY_ENABLE_HTTP=true
GATEWAY_ENABLE_HTTPS=false
```

Useful when UAT intentionally runs without a production TLS certificate.

### PRD — HTTPS only

```env
GATEWAY_ENABLE_HTTP=false
GATEWAY_ENABLE_HTTPS=true
```

This is the recommended production policy.

### Compatibility / integration testing

```env
GATEWAY_ENABLE_HTTP=true
GATEWAY_ENABLE_HTTPS=true
```

Both listeners expose the same Gateway behavior.

## Trade-off summary

| Item | Redirect-only HTTP | Dual real listeners |
|---|---|---|
| PRD TLS enforcement | Strong by default | Controlled by config |
| Configuration simplicity | Simpler | Slightly more complex |
| UAT without TLS | Poor fit | Good fit |
| HTTP same-origin browser flow | No | Yes |
| HTTPS same-origin browser flow | Yes | Yes |
| Certificate/CORS friction in HTTP UAT | Higher | Lower |
| Protocol flexibility | Low | High |

The newer design is not universally superior. It is the better match for the clarified UAT/PRD deployment requirements.

## Interview explanation

> Initially, I treated HTTP as a compatibility listener and HTTPS as the canonical production endpoint, following the common HTTP-to-HTTPS redirect pattern. That simplified configuration and ensured token transport was protected by TLS.
>
> Later, the deployment requirement clarified that UAT could intentionally operate over HTTP while production required HTTPS. Redirecting UAT traffic to HTTPS then introduced unnecessary certificate and cross-origin issues for browser clients.
>
> I changed both protocols into first-class Gateway listeners, made them independently configurable, and made token responses preserve the request protocol. Production can still run HTTPS-only, while UAT can run HTTP-only.

The key architectural lesson is:

> Architecture should follow the actual deployment contract. A redirect model is appropriate when HTTP is only a compatibility entry point, but not when HTTP itself is a supported environment protocol.

## Validation after adjustment

Run tests:

```powershell
python -m pytest -q
```

HTTP health should return `200`, not `308`:

```powershell
curl.exe -i http://10.2.192.9:18080/health
```

HTTP token API:

```powershell
curl.exe -i "http://10.2.192.9:18080/api/v1/tokens?stream_path=%2Fgishtest%2Fgish.flv"
```

Expected `stream_url` prefix:

```text
http://10.2.192.9:18080/
```

HTTPS token API:

```powershell
curl.exe -k -i "https://10.2.192.9:18088/api/v1/tokens?stream_path=%2Fgishtest%2Fgish.flv"
```

Expected `stream_url` prefix:

```text
https://10.2.192.9:18088/
```
