# FLV Token Gateway 使用與 API 說明

## 1. 目的

FLV Token Gateway 是放在 Client / VLC / Browser Player 與內網 HTTP-FLV Source 之間的短效 token reverse proxy。

流程：Client 先申請 token；Gateway 驗證後，再由 server-side 向 upstream 拉流並串回 Client。

## 2. 內網架構範例

```text
Client / Browser / VLC
        |
        | http://10.2.192.9:18088
        v
FLV Token Gateway (10.2.192.9)
        |
        | https://10.2.192.8:8088
        v
SRS HTTP-FLV Source (10.2.192.8)
```

OBS：

```text
rtmp://10.2.192.8/gishtest
stream key: gish
```

HTTP-FLV path：

```text
/gishtest/gish.flv
```

## 3. 設定

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

`GATEWAY_HOST=0.0.0.0` 代表 listen 所有 interface；`PUBLIC_BASE_URL` 是 Client 實際收到的 Gateway URL。

## 4. 啟動

```powershell
python -m app.server
```

Local mock demo：

```powershell
.\run_local_demo.bat
```

local demo 固定使用 Gateway `127.0.0.1:18088` 與 mock upstream `127.0.0.1:9090`，只驗證程式邏輯，不代表真實 OBS/SRS 播放驗證。

## 5. API

### `GET /health`

```json
{"status":"ok"}
```

### `POST /api/v1/tokens`

```json
{"stream_path":"/gishtest/gish.flv"}
```

回傳：

```json
{
  "token":"<TOKEN>",
  "expires_in":300,
  "expires_at":1788151441,
  "stream_url":"http://10.2.192.9:18088/gishtest/gish.flv?token=<TOKEN>"
}
```

### `GET /<stream_path>?token=<TOKEN>`

Gateway 驗證 HMAC、expiry、exact path。通過後 server-side 組成 `UPSTREAM_BASE_URL + requested_path` 向 source 拉流。

## 6. Browser Player / CORS

若 player page 在：

```text
http://10.2.192.8:8080/players/srs_player.html
```

而 FLV 在：

```text
http://10.2.192.9:18088/gishtest/gish.flv?token=...
```

兩者為不同 origin，因此需 CORS。

POC：

```env
CORS_ALLOW_ORIGINS=*
```

正式限制：

```env
CORS_ALLOW_ORIGINS=http://10.2.192.8:8080
```

Gateway 會轉發 Browser `Range` request，並在 upstream 有提供時傳回 `Content-Range` / `Accept-Ranges`。

## 7. 源站 URL 與 bypass 風險

正常 token response 只回 Gateway URL，不回 `UPSTREAM_BASE_URL`。Gateway 是 reverse proxy，不會 redirect Client 到 source。

但「隱藏 IP / port」不是安全邊界。若 Client 能直接連 source network，仍可能透過已知服務、設定資訊或 port scan 找到 source endpoint。尤其 player 若直接由 `10.2.192.8:8080` 提供，Client 已知道 source host IP。

正式部署應使用 ACL / Firewall：

```text
10.2.192.9    -> 10.2.192.8:8088   ALLOW
other clients -> 10.2.192.8:8088   DENY
```

需要時可另外允許：

```text
clients -> 10.2.192.8:8080         ALLOW
```

因此即使 source URL 被猜到，也無法繞過 Gateway 直接盜拉。

若連 source host IP 都不希望暴露，web player 也應放到 Gateway / reverse proxy 後面。

## 8. Test UI

Test UI 從相同 `.env` 取得：

```text
Gateway Base URL <- PUBLIC_BASE_URL
Stream Path      <- TEST_STREAM_PATH
```

## 9. 測試

```powershell
python -m pytest -q
python .\scripts\smoke_test.py http://127.0.0.1:18088
```

外網 local mock 可以驗證 token、401/403、path binding、FLV proxy byte flow、CORS、Range forwarding。

真正 OBS -> SRS -> Gateway -> VLC/Browser 必須在內網驗證。

## 10. PyInstaller

```powershell
python -m PyInstaller --clean --noconfirm FLVTokenGateway_v04_sslfix.spec
```

`.env` 保持在 EXE 外部可編輯。

## 11. Production hardening

1. Source `8088` firewall/ACL，只允許 Gateway host。
2. CORS 從 `*` 改為明確 player origin。
3. 強制 token issuer API key / identity。
4. stream allowlist。
5. rate limit。
6. one-time token / replay prevention。
7. revoke / audit log。
8. public Gateway TLS 與正式 upstream certificate validation。
9. 若需隱藏 source host，將 web player 也放在 Gateway/reverse proxy 後。
