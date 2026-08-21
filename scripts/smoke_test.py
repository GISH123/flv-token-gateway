import json
import sys
import urllib.error
import urllib.request


def request_json(url: str, method: str = "GET", body: dict | None = None) -> tuple[int, dict]:
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"} if data else {},
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


def main() -> int:
    base = sys.argv[1].rstrip("/") if len(sys.argv) > 1 else "http://127.0.0.1:8088"

    status, health = request_json(base + "/health")
    assert status == 200 and health["status"] == "ok", (status, health)
    print("PASS health")

    status, body = request_json(base + "/dev/liveB03.flv")
    assert status == 401 and body["detail"] == "token required", (status, body)
    print("PASS no token -> 401")

    status, token_data = request_json(
        base + "/api/v1/tokens",
        method="POST",
        body={"stream_path": "/dev/liveB03.flv"},
    )
    assert status == 200, (status, token_data)
    assert token_data["expires_in"] == 300, token_data
    print("PASS token issued with 300-second TTL")

    with urllib.request.urlopen(token_data["stream_url"], timeout=10) as response:
        prefix = response.read(3)
        assert response.status == 200
        assert prefix == b"FLV", prefix
    print("PASS valid token -> FLV stream")

    wrong_path = base + "/dev/liveB04.flv?token=" + token_data["token"]
    status, body = request_json(wrong_path)
    assert status == 403, (status, body)
    print("PASS token is bound to stream path -> 403")

    print("\nALL LOCALHOST SMOKE TESTS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
