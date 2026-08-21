from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse

app = FastAPI(title="Mock FLV Upstream")

# FLV signature + a small deterministic payload. It is enough to prove byte-for-byte proxying.
MOCK_FLV = b"FLV\x01\x05\x00\x00\x00\x09\x00\x00\x00\x00" + b"mock-stream-payload" * 64


@app.get("/{stream_path:path}")
async def stream(stream_path: str):
    if not stream_path.lower().endswith(".flv"):
        raise HTTPException(status_code=404)

    async def chunks():
        for i in range(0, len(MOCK_FLV), 64):
            yield MOCK_FLV[i : i + 64]

    return StreamingResponse(chunks(), media_type="video/x-flv")
