# FLV Token Gateway

將內網／源站 FLV 拉流地址包在一層 **5 分鐘 HMAC token 驗證** 後，再對外提供拉流。

需求對應：

- 源站：`https://10.2.192.8:8088/dev/liveB03.flv`
- Client 不能直接碰源站，只碰 Gateway。
- 每次先呼叫 Token API 取得 token。
- token 預設有效 **300 秒（5 分鐘）**。
- 拉 `.flv` 時沒有 token → `401`。
- token 無效、被竄改、過期、或拿 B03 的 token 拉 B04 → `403`。
- token 只在「建立拉流連線」時驗證。連線建立成功後，不會在第 300 秒硬切斷正在播放的 stream；下一次 reconnect 時必須重新取得有效 token。

## Architecture

```text
Client
  |  POST /api/v1/tokens {stream_path}
  v
FLV Token Gateway :8088
  |  returns /dev/liveB03.flv?token=...
  |
  |  GET .flv?token=...  (verify HMAC + path + expiry)
  v
Source / Upstream :9090 in localhost demo
  or https://10.2.192.8:8088 in intranet
```

## 1. Localhost demo (Windows)

最簡單：

```bat
run_local_demo.bat
```

它會啟動：

- Mock source: `http://127.0.0.1:9090`
- Gateway: `http://127.0.0.1:8088`
- Swagger: `http://127.0.0.1:8088/docs`

### 先取得 5 分鐘 token

PowerShell:

```powershell
$body = @{ stream_path = "/dev/liveB03.flv" } | ConvertTo-Json
$r = Invoke-RestMethod -Method Post `
  -Uri "http://127.0.0.1:8088/api/v1/tokens" `
  -ContentType "application/json" `
  -Body $body
$r
$r.stream_url
```

你會拿到類似：

```text
http://127.0.0.1:8088/dev/liveB03.flv?token=eyJ...<signature>
```

接著：

```powershell
Invoke-WebRequest -Uri $r.stream_url -OutFile test.flv
```

直接不帶 token：

```powershell
Invoke-WebRequest "http://127.0.0.1:8088/dev/liveB03.flv"
```

應回 `401 token required`。

## 2. Run automated tests

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
pytest -q
```

測試包含：

1. token 5 分鐘 expiry。
2. 無 token 禁止拉流。
3. 正確 token 可以取得 upstream FLV bytes。
4. token 綁定 path，B03 token 不能拿去拉 B04。
5. token 被竄改會拒絕。
6. Token API 可選擇加 `X-Token-API-Key` 保護。

## 3. Move to intranet

修改 `.env`：

```env
PUBLIC_BASE_URL=https://your-public-host.example.com
UPSTREAM_BASE_URL=https://10.2.192.8:8088
TOKEN_SECRET=<至少 32 bytes 的強隨機 secret>
TOKEN_TTL_SECONDS=300
TOKEN_ISSUER_API_KEY=<建議設定，避免任何人都能無限制索取 token>
UPSTREAM_VERIFY_TLS=false
```

若內網源站使用正式憑證，`UPSTREAM_VERIFY_TLS=true`。只有 self-signed/internal CA 且尚未匯入 trust store 時才暫時設 `false`。

### Production token request

若設定 `TOKEN_ISSUER_API_KEY`：

```powershell
$headers = @{ "X-Token-API-Key" = "<your issuer key>" }
$body = @{ stream_path = "/dev/liveB03.flv" } | ConvertTo-Json
Invoke-RestMethod -Method Post `
  -Uri "https://your-public-host.example.com/api/v1/tokens" `
  -Headers $headers -ContentType "application/json" -Body $body
```

## 4. HTTPS

程式本身可置於 Nginx / IIS / ingress 後方做 TLS termination，這通常比讓 Uvicorn 直接管理正式憑證更合適。最終對外 URL 就可以符合需求中的 `https://xxxx/...flv?token=...`。

## Security notes

- HMAC-SHA256，token 無 server-side session，適合多 worker / 多 instance。
- token 綁定 exact stream path，不能跨頻道重用。
- HMAC 驗證使用 constant-time compare。
- `.env` 不進 Git。
- Token API 建議於正式環境設定 `TOKEN_ISSUER_API_KEY`，否則「任何可以連到 API 的人」都可以自行取得 5 分鐘 token。
- 若需求之後要求「同一 token 只能使用一次」或「300 秒到點立即切斷既有 stream」，需要增加 server-side state；目前依常見串流 token 語意為 **300 秒內允許建立連線**。

## API

### `POST /api/v1/tokens`

Request:

```json
{
  "stream_path": "/dev/liveB03.flv"
}
```

Response:

```json
{
  "token": "...",
  "expires_in": 300,
  "expires_at": 1787280000,
  "stream_url": "https://your-public-host.example.com/dev/liveB03.flv?token=..."
}
```

### `GET /dev/liveB03.flv?token=...`

驗證通過後，以 streaming/chunked 方式 reverse proxy 原始 FLV；不先下載整個影片到記憶體。
