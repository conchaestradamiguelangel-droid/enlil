"""Lee/escribe la configuracion del CLI en ~/.enlil/config.json"""
import json
import sys
from pathlib import Path

CONFIG_DIR  = Path.home() / ".enlil"
CONFIG_FILE = CONFIG_DIR / "config.json"


def load() -> dict:
    if not CONFIG_FILE.exists():
        return {}
    try:
        return json.loads(CONFIG_FILE.read_text())
    except Exception:
        return {}


def save(url: str, api_key: str) -> None:
    CONFIG_DIR.mkdir(exist_ok=True)
    CONFIG_FILE.write_text(json.dumps({"url": url.rstrip("/"), "api_key": api_key}, indent=2))
    try:
        CONFIG_FILE.chmod(0o600)
    except Exception:
        pass


def require() -> dict:
    cfg = load()
    if not cfg.get("url") or not cfg.get("api_key"):
        print("  ENLIL no configurado. Ejecuta primero: enlil init")
        sys.exit(1)
    return cfg
