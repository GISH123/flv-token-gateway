# FLV Token Gateway 使用與 API 說明

## 1. 目的

FLV Token Gateway 是一個放在 Client/VLC 與內網 FLV Source 之間的短效 token 鑑權 reverse proxy。

它的目標不是取代 SRS，也不修改原本 RTMP/HTTP-FLV server；而是在既有 FLV URL 前面加上一層：

1. Client 先向 Gateway 申請短效 token。
2. Gateway 發出包含 stream path、expiry、nonce 的 HMAC token。
3. Client/VLC 使用 Gateway 回傳的 `stream_url` 拉流。
4. Gateway 驗證 token 後，再向 upstream FLV Source 取流並串回 Client。

---

## 2. 架構

```text
Client / VLC
    |
    | POST /api/v1/tokens {stream_path}
    v
FLV Token Gateway  <---- .env configuration
    |
    | GET upstream FLV
    v
SRS / FLV Source
```

內網驗證範例：

```env
PUBLIC_BASE_URL=http://127.0.0.1:18088
UPSTREAM_BASE_URL=https://10.2.192.8:8088
TOKEN_TTL_SECONDS=300
UPSTREAM_VERIFY_TLS=false
```

對應播放路徑：

```text
OBS RTMP push:
rtmp://10.2.192.8/gishtest
Stream key: gish

HTTP-FLV stream path:
/gishtest/gish.flv

VLC final URL:
http://127.0.0.1:18088/gishtest/gish.flv?token=<TOKEN>
```

---

## 3. 安裝與啟動

### 3.1 建立虛擬環境

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

### 3.2 設定 `.env`

複製範例：

```powershell
copy .env.example .env
```

設定重點：

```env
PUBLIC_BASE_URL=http://127.0.0.1:18088
UPSTREAM_BASE_URL=https://10.2.192.8:8088
TOKEN_SECRET=<long-random-secret>
TOKEN_TTL_SECONDS=300
TOKEN_ISSUER_API_KEY=
UPSTREAM_VERIFY_TLS=false
```

欄位說明：

| 欄位 | 說明 |
|---|---|
| `PUBLIC_BASE_URL` | Client/VLC 看到的 Gateway 對外 URL。 |
| `UPSTREAM_BASE_URL` | Gateway 背後要代理的 FLV Source URL。 |
| `TOKEN_SECRET` | HMAC 簽章使用的 secret；正式環境不可外洩。 |
| `TOKEN_TTL_SECONDS` | token 有效秒數，POC 使用 300 秒。 |
| `TOKEN_ISSUER_API_KEY` | 若非空，申請 token 時必須帶 `X-Token-API-Key`。POC 可留空。 |
| `UPSTREAM_VERIFY_TLS` | 是否驗證 upstream TLS 憑證；內網自簽憑證可設為 `false`。 |

### 3.3 啟動服務

```powershell
python -m uvicorn app.main:app --host 127.0.0.1 --port 18088
```

健康檢查：

```powershell
curl http://127.0.0.1:18088/health
```

預期：

```json
{"status":"ok"}
```

---

## 4. API 說明

## 4.1 `GET /health`

用途：確認 Gateway 服務是否啟動。

Request：

```http
GET /health
```

Response：

```json
{
  "status": "ok"
}
```

---

## 4.2 `POST /api/v1/tokens`

用途：替指定 FLV stream path 申請短效 token。

Request：

```http
POST /api/v1/tokens
Content-Type: application/json
```

Body：

```json
{
  "stream_path": "/gishtest/gish.flv"
}
```

Response：

```json
{
  "token": "<TOKEN>",
  "expires_in": 300,
  "expires_at": 1788151441,
  "stream_url": "http://127.0.0.1:18088/gishtest/gish.flv?token=<TOKEN>"
}
```

PowerShell 範例：

```powershell
$streamPath = "/gishtest/gish.flv"
$body = @{ stream_path = $streamPath } | ConvertTo-Json

$r = Invoke-RestMethod `
    -Method Post `
    -Uri "http://127.0.0.1:18088/api/v1/tokens" `
    -ContentType "application/json" `
    -Body $body

$r | Format-List token, expires_in, expires_at, stream_url
$r.stream_url | Set-Clipboard
```

---

## 4.3 `GET /<stream_path>?token=<TOKEN>`

用途：使用 tokenized Gateway URL 拉 HTTP-FLV stream。

範例：

```text
http://127.0.0.1:18088/gishtest/gish.flv?token=<TOKEN>
```

Gateway 會做三件事：

1. 驗證 HMAC signature。
2. 驗證 token 是否過期。
3. 驗證 request path 是否與 token 內的 path 完全一致。

通過後，Gateway 會向 upstream 取流：

```text
https://10.2.192.8:8088/gishtest/gish.flv
```

並用 streaming response 回給 Client/VLC。

---

## 5. Token 行為說明

### 5.1 每次 POST 都會產生不同 token

即使 `stream_path` 相同，每次 `POST /api/v1/tokens` 都會重新產生 `nonce`，因此 token 應不同。

### 5.2 Token 前半段看起來相似是正常的

token 格式可理解為：

```text
<payload_base64url>.<hmac_signature>
```

payload 裡包含：

```json
{
  "p": "/gishtest/gish.flv",
  "exp": 1788151441,
  "n": "random-nonce"
}
```

因為 path 與 JSON 欄位名稱一樣，所以 token 前半段可能很像；真正差異通常在 payload 後半段與 signature。

### 5.3 新 token 不會主動註銷舊 token

本版是 stateless short-lived token，不保存 server-side token 狀態。

因此：

```text
POST #1 -> token A，有效 300 秒
POST #2 -> token B，有效 300 秒
```

token A 和 token B 可以在各自 TTL 內同時有效。

### 5.4 同一 token 在 TTL 內可以重複建立連線

本版沒有 one-time token / replay prevention。只要 token 沒過期、path 沒被改、signature 合法，就可以再次建立 stream。

這是 POC 的已知限制；若要正式上線，可改成 server-side token store 或 Redis，加入一次性使用、撤銷與 replay 防護。

### 5.5 已建立的 stream 不會在第 300 秒硬切

目前 Gateway 是在「建立連線時」驗證 token。

若 VLC 在 token 有效期間成功連上，stream 不會在第 300 秒被強制中斷。

但 token 過期後，使用同一 URL 重新建立連線時，應被拒絕。

---

## 6. 錯誤碼

| 狀況 | HTTP Status | 說明 |
|---|---:|---|
| 沒帶 token | 401 | `token required` |
| token 格式錯誤 / 簽章錯誤 | 403 | token invalid |
| token 過期 | 403 | token expired |
| token 內 path 與 request path 不一致 | 403 | path mismatch |
| upstream 不存在或不可連 | 依 upstream / Gateway error | 需查 Gateway log 與 upstream service |

---

## 7. VLC 使用流程

1. OBS 推流到 SRS。
2. 向 Gateway 申請 token。
3. 複製 response 裡的 `stream_url`。
4. VLC → Media → Open Network Stream。
5. 貼上 `stream_url` 並播放。

---

## 8. 測試覆蓋

目前 pytest 覆蓋：

1. token 在有效期內可驗證。
2. token 到期會被拒絕。
3. token 綁定 path，換 path 會失敗。
4. token 被竄改會失敗。
5. 沒帶 token 拉流回 401。
6. 有效 token 可以串流 upstream response。
7. token endpoint 回傳 stream_url 與 TTL。
8. 若設定 API Key，token endpoint 需檢查 `X-Token-API-Key`。

---

## 9. Production hardening 建議

POC 已驗證核心流程；正式環境建議補：

1. 強制啟用 `TOKEN_ISSUER_API_KEY` 或接入公司內部身份驗證。
2. stream path allowlist，只允許特定路徑申請 token。
3. rate limit，避免 token endpoint 被濫用。
4. one-time token / replay prevention，可用 Redis 保存 token jti/nonce 狀態。
5. token revoke 機制，可主動使 token 失效。
6. audit log，記錄 token 發行、拒絕原因、upstream 狀態。
7. 正式 TLS 憑證，將 `UPSTREAM_VERIFY_TLS=true`。

---

## 10. 專案目前結論

本 POC 已完成：

- Gateway 可發行短效 HMAC token。
- token 綁定 exact stream path 與 expiry。
- VLC 可使用 Gateway URL + token 成功播放內網 FLV。
- 主要安全行為已有 pytest 覆蓋。

結論：POC 可交付，後續若要 production 化，再補 API Key 強制、allowlist、rate limit、one-time token、audit log 等 hardening。
