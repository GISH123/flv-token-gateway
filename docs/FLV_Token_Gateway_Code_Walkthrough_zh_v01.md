# FLV Token Gateway 程式理解筆記

這份是用來讓你能完整講清楚這個 POC 的「口袋稿」。

## 一句話說明

這支程式是一個 FastAPI reverse proxy。Client 不直接打 SRS 的 FLV URL，而是先向 Gateway 申請短效 HMAC token，再用 Gateway 回傳的 tokenized URL 拉流。Gateway 在建立連線時驗證 token，通過後才去 upstream SRS 拉 FLV 並串流回 VLC。

---

## 整體流程

```text
1. OBS -> SRS
   OBS 先把 RTMP stream 推到 SRS。

2. Client -> Gateway: POST /api/v1/tokens
   Client 告訴 Gateway 想拉哪個 stream path。

3. Gateway -> Token Service
   Token Service 產生一個 HMAC-signed token。

4. Gateway -> Client
   回傳 token、expires_in、expires_at、stream_url。

5. VLC -> Gateway: GET /gishtest/gish.flv?token=...
   VLC 拿 tokenized URL 拉流。

6. Gateway 驗證 token
   檢查 signature、expiry、path 是否一致。

7. Gateway -> SRS
   通過後向 upstream 拉真正的 FLV。

8. Gateway -> VLC
   用 StreamingResponse 把 upstream bytes 串回 VLC。
```

---

## 主要檔案怎麼分工

### `app/settings.py`

負責從 `.env` 讀設定。

你可以這樣說：

> 我把 Gateway 的 public URL、upstream URL、token secret、TTL、TLS verify 等參數都抽到 `.env`，所以部署到內網時不用改 code，只要換設定。

重要欄位：

- `PUBLIC_BASE_URL`：Gateway 對 Client/VLC 暴露的 URL。
- `UPSTREAM_BASE_URL`：Gateway 背後真正拉流的 SRS/FLV Source。
- `TOKEN_SECRET`：HMAC 簽章用 secret。
- `TOKEN_TTL_SECONDS`：token 有效秒數。
- `TOKEN_ISSUER_API_KEY`：可選，如果設定就要求 token endpoint 帶 API Key。
- `UPSTREAM_VERIFY_TLS`：內網自簽憑證時可設 false。

---

### `app/token_service.py`

這是 token 的核心。

你可以這樣說：

> token_service 不負責 HTTP，它只負責 token 的產生與驗證。這樣可以讓 token 邏輯跟 FastAPI route 分開，單元測試也比較好寫。

Token payload 包含：

```json
{
  "p": "stream path",
  "exp": "expiry timestamp",
  "n": "random nonce"
}
```

其中：

- `p`：綁定 exact stream path。
- `exp`：過期時間。
- `n`：nonce，避免同路徑同時間產生完全相同 token。

token 格式：

```text
base64url(payload).base64url(hmac_sha256(payload, TOKEN_SECRET))
```

重點說法：

> Payload 不是加密，只是 Base64URL encoding，所以可以被 decode；安全性來自 HMAC signature。只要有人改 path 或 exp，Gateway 重算 signature 就會不一致，因此驗證失敗。

---

### `app/main.py`

這是 FastAPI 入口。

主要做三件事：

1. 建立 app 與 HTTP client。
2. 提供 `/health`。
3. 提供 token API 與 FLV proxy route。

#### `/api/v1/tokens`

邏輯：

1. 接收 `stream_path`。
2. 如果設定了 `TOKEN_ISSUER_API_KEY`，就檢查 `X-Token-API-Key`。
3. 呼叫 `issue_token()`。
4. 回傳 `token`、`expires_in`、`expires_at`、`stream_url`。

你可以這樣講：

> token endpoint 不直接回 upstream URL，而是回 Gateway URL + token。VLC 只需要使用這個 URL，不需要知道 upstream 的真實來源。

#### FLV proxy route

邏輯：

1. VLC 打 `/{stream_path}?token=...`。
2. Gateway 取出 request path 與 token。
3. 呼叫 `verify_token()`。
4. 確認 token 內的 path 與 request path 完全一致。
5. 用 `httpx.AsyncClient` 向 upstream 發 GET。
6. 用 `StreamingResponse` 把 upstream stream 回 Client。

你可以這樣講：

> 這裡不是先把整個 FLV 下載到記憶體，而是用 streaming response 邊讀邊回，符合長連線串流的使用情境。

---

## Token 為什麼不是每次前面都完全不同？

token 前半段是 payload 的 Base64URL。

因為每次 path 一樣、欄位名稱一樣、expiry 很接近，所以前半段看起來很像是正常的。

真正保證每次不同的是：

- `nonce` 不同。
- `exp` 可能不同。
- HMAC signature 也會跟著不同。

你已經用：

```powershell
$r1.token -eq $r2.token
```

驗證過結果是 `False`，所以兩個 token 確實不同。

---

## 新 token 會不會讓舊 token 失效？

目前版本不會。

這是 stateless token 設計：Gateway 不在 server side 保存每個 token，因此也沒有「發新 token 就 revoke 舊 token」的邏輯。

正確理解：

```text
token A: 自己的 expires_at 前有效
token B: 自己的 expires_at 前有效
```

兩個可以同時有效。

這是 POC 可接受的設計，但 production 可以加 Redis / DB 做 one-time token、revoke、replay protection。

---

## 為什麼播放中不會 300 秒自動斷線？

目前是「建立連線時驗證 token」。

所以：

- token 有效時建立 stream：可以播放。
- 播放中到 300 秒：不會硬切。
- token 過期後重新 GET：應該 403。

你可以這樣說：

> 本 POC 的 TTL 是限制新的連線建立，不是定時切斷已建立串流。這樣比較符合 VLC/HTTP-FLV 長連線播放的實測需求。

---

## 8 個 pytest 在保護什麼

### token_service tests

1. 有效 token 能驗證。
2. expiry 到達後會拒絕。
3. path 不同會拒絕。
4. token 被竄改會拒絕。

### gateway tests

5. 沒帶 token 拉流會回 401。
6. 有效 token 能 proxy upstream stream。
7. token endpoint 會回 stream_url、TTL。
8. 若設定 API Key，token endpoint 會檢查 `X-Token-API-Key`。

你可以這樣說：

> 我不是只測服務有沒有起來，而是測 token 的有效、過期、path binding、tamper，以及 gateway 的 no-token、valid-stream、API key 行為。

---

## 如果別人問「這能不能上 production？」

回答：

> 目前是 POC，核心 token-gated pull stream 流程已驗證。Production 還要補 API Key 強制、stream path allowlist、rate limit、one-time token/revoke、audit log，以及正式 TLS 驗證。

不要說現在已是完整 production security。

---

## 你可以直接這樣介紹專案

> 我做了一個 FLV Token Gateway POC，用 FastAPI 包在 Client/VLC 和 SRS HTTP-FLV source 中間。Client 先 POST stream path 取得短效 HMAC token，token 內綁 path、expiry、nonce。VLC 再用 Gateway 回的 stream_url 拉流。Gateway 會驗證 signature、expiry、path，一旦通過就用 httpx 向 upstream 拉 FLV，再用 StreamingResponse 轉回 VLC。這版是 stateless token，所以新 token 不會 revoke 舊 token，TTL 是限制新連線建立；one-time token、allowlist、rate limit、audit log 會放在 production hardening。
