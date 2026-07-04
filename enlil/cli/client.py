"""Cliente HTTP para la API de ENLIL -- solo stdlib, cero dependencias extra."""
import json
import urllib.request
import urllib.error


def _headers(api_key: str) -> dict:
    return {"Content-Type": "application/json", "X-Api-Key": api_key}


def query_stream(url: str, api_key: str, text: str, budget_tier=None, peer_review: bool = False, timeout_override: float | None = None):
    """POST /query/stream -- genera dicts de eventos SSE."""
    payload = {"query": text}
    if budget_tier:
        payload["budget_tier"] = budget_tier
    if peer_review:
        payload["peer_review"] = True
    if timeout_override is not None:
        payload["timeout_override"] = timeout_override
    req = urllib.request.Request(
        f"{url}/query/stream",
        data=json.dumps(payload).encode(),
        headers=_headers(api_key),
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            for raw in resp:
                line = raw.decode("utf-8", errors="replace").rstrip("\r\n")
                if line.startswith("data: "):
                    try:
                        yield json.loads(line[6:])
                    except json.JSONDecodeError:
                        pass
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        raise RuntimeError(f"HTTP {e.code}: {body}") from e


def history(url: str, api_key: str, limit: int = 10) -> list:
    req = urllib.request.Request(
        f"{url}/history?limit={limit}",
        headers=_headers(api_key),
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def get_decree(url: str, api_key: str, decree_id: str) -> dict:
    req = urllib.request.Request(
        f"{url}/decree/{decree_id}",
        headers=_headers(api_key),
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def server_status(url: str, api_key: str) -> dict:
    req = urllib.request.Request(
        f"{url}/mode",
        headers=_headers(api_key),
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read())


def health(url: str) -> bool:
    try:
        with urllib.request.urlopen(f"{url}/health", timeout=5) as resp:
            return resp.status == 200
    except Exception:
        return False
