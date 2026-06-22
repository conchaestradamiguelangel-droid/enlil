import warnings
import logging
logger = logging.getLogger("enlil.quantum")
warnings.filterwarnings("ignore", message="liboqs version")
"""
Criptografía Post-Cuántica para ENLIL.
Firma cada Decreto con ML-DSA-87 (NIST FIPS 204) al guardarse.
Los Decretos son irrevocables e inviolables desde el origen.
"""
import os
import json
import base64
import hashlib

_KEY_PATH = os.environ.get("ENLIL_PQ_KEYPATH", "./data/enlil_pq.key")
_ALGORITHM = "ML-DSA-87"

_keypair_cache: tuple[bytes, bytes] | None = None


def _load_or_generate_keypair() -> tuple[bytes, bytes]:
    global _keypair_cache
    if _keypair_cache:
        return _keypair_cache
    try:
        import oqs
        if os.path.exists(_KEY_PATH):
            with open(_KEY_PATH, "rb") as f:
                data = json.loads(f.read())
                private_key = base64.b64decode(data["private_key"])
                public_key = base64.b64decode(data["public_key"])
        else:
            with oqs.Signature(_ALGORITHM) as signer:
                public_key = signer.generate_keypair()
                private_key = signer.export_secret_key()
            os.makedirs(os.path.dirname(_KEY_PATH), exist_ok=True)
            with open(_KEY_PATH, "wb") as f:
                f.write(json.dumps({
                    "algorithm": _ALGORITHM,
                    "public_key": base64.b64encode(public_key).decode(),
                    "private_key": base64.b64encode(private_key).decode(),
                }).encode())
        _keypair_cache = (private_key, public_key)
        return private_key, public_key
    except ImportError:
        return b"", b""


def _decree_payload(decree_id: str, query: str, synthesis: str, timestamp: float) -> bytes:
    """Contenido canónico que se firma — reproducible y determinista."""
    canonical = json.dumps({
        "id": decree_id,
        "query": query,
        "synthesis": synthesis,
        "timestamp": timestamp,
    }, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode()).digest()


def sign_decree(decree_id: str, query: str, synthesis: str, timestamp: float) -> str:
    """Firma un Decreto. Devuelve la firma en base64 o cadena vacía si oqs no disponible."""
    try:
        import oqs
        private_key, _ = _load_or_generate_keypair()
        if not private_key:
            return ""
        payload = _decree_payload(decree_id, query, synthesis, timestamp)
        with oqs.Signature(_ALGORITHM, secret_key=private_key) as signer:
            signature = signer.sign(payload)
        return base64.b64encode(signature).decode()
    except Exception as e:
        logger.error("sign_decree failed: %s", e)
        return ""


def verify_decree(decree_id: str, query: str, synthesis: str, timestamp: float, signature_b64: str) -> bool:
    """Verifica la firma PQ de un Decreto. False si oqs no disponible o firma inválida."""
    if not signature_b64:
        return False
    try:
        import oqs
        _, public_key = _load_or_generate_keypair()
        if not public_key:
            return False
        payload = _decree_payload(decree_id, query, synthesis, timestamp)
        signature = base64.b64decode(signature_b64)
        with oqs.Signature(_ALGORITHM) as verifier:
            return verifier.verify(payload, signature, public_key)
    except Exception as e:
        logger.error("verify_decree failed: %s", e)
        return False


def public_key_b64() -> str:
    """Clave pública en base64 para verificación externa."""
    try:
        _, public_key = _load_or_generate_keypair()
        return base64.b64encode(public_key).decode() if public_key else ""
    except Exception as e:
        logger.error("sign_decree failed: %s", e)
        return ""


def is_available() -> bool:
    """True si oqs está instalado y el sistema PQ está operativo."""
    try:
        import oqs
        private_key, _ = _load_or_generate_keypair()
        return bool(private_key)
    except Exception as e:
        logger.error("verify_decree failed: %s", e)
        return False


def key_id() -> str:
    """SHA-256 de la clave publica, primeros 16 bytes en hex (32 chars). Identifica el par de claves activo."""
    try:
        import hashlib as _hl
        _, public_key = _load_or_generate_keypair()
        if not public_key:
            return ""
        return _hl.sha256(public_key).digest()[:16].hex()
    except Exception as e:
        logger.error("key_id failed: %s", e)
        return ""


def sign_task_response(
    request_id: str,
    connection_id: str,
    sender_node_id: str,
    status: str,
    result: str | None,
    error: str | None,
) -> tuple[str, str, str]:
    """
    Firma el payload canonico de una respuesta A2A ekurhive-task-v1.
    Devuelve (pq_signature_b64, key_id_hex, result_sha3_256_hex).
    Lanza RuntimeError si oqs no esta disponible o la clave no existe.
    """
    import hashlib as _hl
    import json as _json
    try:
        import oqs
    except ImportError:
        raise RuntimeError("liboqs no disponible — J4 requiere firma obligatoria")

    private_key, _ = _load_or_generate_keypair()
    if not private_key:
        raise RuntimeError("Clave privada ML-DSA-87 no disponible")

    kid = key_id()
    result_bytes = result.encode("utf-8") if result is not None else b""
    result_sha3 = _hl.sha3_256(result_bytes).hexdigest()

    canonical_obj = {
        "algorithm":         _ALGORITHM,
        "connection_id":     connection_id,
        "error":             error,
        "key_id":            kid,
        "protocol":          "ekurhive-task-v1",
        "request_id":        request_id,
        "result_sha3_256":   result_sha3,
        "sender_node_id":    sender_node_id,
        "signature_version": "1",
        "status":            status,
        "target_node_id":    "node-enlil-001",
    }
    canonical_bytes = _json.dumps(
        canonical_obj,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")

    with oqs.Signature(_ALGORITHM, secret_key=private_key) as signer:
        signature = signer.sign(canonical_bytes)

    return base64.b64encode(signature).decode("ascii"), kid, result_sha3
