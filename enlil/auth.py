"""
ENLIL — Sistema de autenticación comercial
API keys por cliente, rate limiting, logs de uso para facturación.
"""
import os
import time
import uuid
import secrets
import sqlite3
from datetime import datetime, timezone
from typing import Optional
from fastapi import Header, HTTPException

DB_PATH = os.environ.get("ENLIL_DB", "./data/enlil.db")
MASTER_KEY = os.environ.get("ENLIL_MASTER_KEY", "")


def _db():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_auth_tables():
    conn = _db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS clients (
            id          TEXT PRIMARY KEY,
            name        TEXT NOT NULL,
            email       TEXT UNIQUE NOT NULL,
            plan        TEXT DEFAULT 'standard',
            monthly_token_budget  INTEGER DEFAULT 500000,
            max_requests_per_hour INTEGER DEFAULT 30,
            max_total_requests    INTEGER DEFAULT NULL,
            monthly_decrees_limit INTEGER DEFAULT NULL,
            active      INTEGER DEFAULT 1,
            created_at  REAL NOT NULL,
            notes       TEXT DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS api_keys (
            key         TEXT PRIMARY KEY,
            client_id   TEXT NOT NULL,
            label       TEXT DEFAULT '',
            created_at  REAL NOT NULL,
            expires_at  REAL,
            active      INTEGER DEFAULT 1,
            FOREIGN KEY (client_id) REFERENCES clients(id)
        );

        CREATE TABLE IF NOT EXISTS usage_log (
            id           TEXT PRIMARY KEY,
            client_id    TEXT NOT NULL,
            decree_id    TEXT,
            tokens_used  INTEGER DEFAULT 0,
            budget_tier  TEXT DEFAULT 'standard',
            gods_count   INTEGER DEFAULT 0,
            query_preview TEXT DEFAULT '',
            timestamp    REAL NOT NULL,
            FOREIGN KEY (client_id) REFERENCES clients(id)
        );

        CREATE TABLE IF NOT EXISTS rate_buckets (
            client_id   TEXT NOT NULL,
            hour_bucket TEXT NOT NULL,
            count       INTEGER DEFAULT 0,
            PRIMARY KEY (client_id, hour_bucket)
        );

        CREATE INDEX IF NOT EXISTS idx_usage_client ON usage_log(client_id, timestamp);
        CREATE INDEX IF NOT EXISTS idx_keys_client  ON api_keys(client_id);
    """)
    conn.commit()
    # Migration guard: add monthly_decrees_limit if missing
    try:
        conn.execute("ALTER TABLE clients ADD COLUMN monthly_decrees_limit INTEGER DEFAULT NULL")
        conn.commit()
    except Exception:
        pass
    conn.close()


# ─── Key generation ───────────────────────────────────────────────────────────

def generate_api_key() -> str:
    return "enlil_" + secrets.token_urlsafe(32)


def generate_client_id() -> str:
    return secrets.token_hex(8)


# ─── Client CRUD ──────────────────────────────────────────────────────────────

def create_client(name: str, email: str, plan: str = "standard",
                  monthly_token_budget: int = 500000,
                  max_requests_per_hour: int = 30,
                  max_total_requests: int = None,
                  monthly_decrees_limit: int = None,
                  notes: str = "") -> dict:
    cid = generate_client_id()
    key = generate_api_key()
    now = time.time()
    conn = _db()
    conn.execute(
        "INSERT INTO clients (id,name,email,plan,monthly_token_budget,max_requests_per_hour,max_total_requests,monthly_decrees_limit,active,created_at,notes) "
        "VALUES (?,?,?,?,?,?,?,?,1,?,?)",
        (cid, name, email, plan, monthly_token_budget, max_requests_per_hour, max_total_requests, monthly_decrees_limit, now, notes)
    )
    conn.execute(
        "INSERT INTO api_keys (key,client_id,label,created_at,active) VALUES (?,?,?,?,1)",
        (key, cid, "primary", now)
    )
    conn.commit()
    conn.close()
    return {"client_id": cid, "api_key": key}


def list_clients() -> list:
    conn = _db()
    rows = conn.execute(
        "SELECT id,name,email,plan,monthly_token_budget,max_requests_per_hour,active,created_at,notes "
        "FROM clients ORDER BY created_at DESC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def toggle_client(client_id: str, active: bool):
    conn = _db()
    conn.execute("UPDATE clients SET active=? WHERE id=?", (1 if active else 0, client_id))
    conn.commit()
    conn.close()


def list_keys(client_id: str) -> list:
    conn = _db()
    rows = conn.execute(
        "SELECT key,label,created_at,expires_at,active FROM api_keys WHERE client_id=?",
        (client_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def revoke_key(key: str):
    conn = _db()
    conn.execute("UPDATE api_keys SET active=0 WHERE key=?", (key,))
    conn.commit()
    conn.close()


def add_key(client_id: str, label: str = "extra") -> str:
    key = generate_api_key()
    conn = _db()
    conn.execute(
        "INSERT INTO api_keys (key,client_id,label,created_at,active) VALUES (?,?,?,?,1)",
        (key, client_id, label, time.time())
    )
    conn.commit()
    conn.close()
    return key


# ─── Usage & rate limiting ────────────────────────────────────────────────────

def _hour_bucket() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d-%H")


def _month_start() -> float:
    now = datetime.now(timezone.utc)
    return datetime(now.year, now.month, 1, tzinfo=timezone.utc).timestamp()


def check_and_increment_rate(client_id: str, max_per_hour: int) -> bool:
    """True = permitido. False = rate limited."""
    bucket = _hour_bucket()
    conn = _db()
    row = conn.execute(
        "SELECT count FROM rate_buckets WHERE client_id=? AND hour_bucket=?",
        (client_id, bucket)
    ).fetchone()
    count = row["count"] if row else 0
    if count >= max_per_hour:
        conn.close()
        return False
    conn.execute(
        "INSERT INTO rate_buckets (client_id,hour_bucket,count) VALUES (?,?,1) "
        "ON CONFLICT(client_id,hour_bucket) DO UPDATE SET count=count+1",
        (client_id, bucket)
    )
    conn.commit()
    conn.close()
    return True


def total_requests_used(client_id: str) -> int:
    conn = _db()
    row = conn.execute(
        "SELECT COUNT(*) AS n FROM usage_log WHERE client_id=?",
        (client_id,)
    ).fetchone()
    conn.close()
    return int(row["n"]) if row else 0


def monthly_tokens_used(client_id: str) -> int:
    conn = _db()
    row = conn.execute(
        "SELECT COALESCE(SUM(tokens_used),0) AS t FROM usage_log "
        "WHERE client_id=? AND timestamp>=?",
        (client_id, _month_start())
    ).fetchone()
    conn.close()
    return int(row["t"]) if row else 0


def monthly_decrees_used(client_id: str) -> int:
    conn = _db()
    row = conn.execute(
        "SELECT COUNT(*) AS n FROM usage_log WHERE client_id=? AND timestamp>=?",
        (client_id, _month_start())
    ).fetchone()
    conn.close()
    return int(row["n"]) if row else 0


def log_usage(client_id: str, decree_id: str, tokens: int,
              budget_tier: str, gods_count: int, query_preview: str):
    conn = _db()
    conn.execute(
        "INSERT INTO usage_log (id,client_id,decree_id,tokens_used,budget_tier,gods_count,query_preview,timestamp) "
        "VALUES (?,?,?,?,?,?,?,?)",
        (str(uuid.uuid4()), client_id, decree_id, tokens,
         budget_tier, gods_count, query_preview[:120], time.time())
    )
    conn.commit()
    conn.close()


def client_usage_this_month(client_id: str) -> dict:
    ms = _month_start()
    conn = _db()
    row = conn.execute(
        "SELECT COUNT(*) as requests, COALESCE(SUM(tokens_used),0) as tokens "
        "FROM usage_log WHERE client_id=? AND timestamp>=?",
        (client_id, ms)
    ).fetchone()
    conn.close()
    return {"requests": row["requests"], "tokens": int(row["tokens"])}


def all_clients_usage() -> list:
    ms = _month_start()
    conn = _db()
    rows = conn.execute("""
        SELECT c.id, c.name, c.email, c.plan, c.monthly_token_budget,
               c.max_requests_per_hour, c.max_total_requests, c.monthly_decrees_limit, c.active,
               COALESCE(SUM(u.tokens_used),0) AS tokens_month,
               COUNT(u.id) AS requests_month
        FROM clients c
        LEFT JOIN usage_log u ON u.client_id = c.id AND u.timestamp >= ?
        GROUP BY c.id
        ORDER BY tokens_month DESC
    """, (ms,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def client_usage_log(client_id: str, limit: int = 50) -> list:
    conn = _db()
    rows = conn.execute(
        "SELECT id,decree_id,tokens_used,budget_tier,gods_count,query_preview,timestamp "
        "FROM usage_log WHERE client_id=? ORDER BY timestamp DESC LIMIT ?",
        (client_id, limit)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ─── FastAPI dependencies ─────────────────────────────────────────────────────

def _validate_key(key: str) -> Optional[dict]:
    conn = _db()
    row = conn.execute("""
        SELECT c.id, c.name, c.email, c.plan, c.monthly_token_budget,
               c.max_requests_per_hour, c.max_total_requests, c.monthly_decrees_limit, c.active,
               k.expires_at, k.active AS key_active
        FROM api_keys k
        JOIN clients c ON k.client_id = c.id
        WHERE k.key=? AND k.active=1 AND c.active=1
    """, (key,)).fetchone()
    conn.close()
    if not row:
        return None
    if row["expires_at"] and row["expires_at"] < time.time():
        return None
    return dict(row)


async def require_auth(x_api_key: Optional[str] = Header(None)) -> dict:
    if not x_api_key:
        raise HTTPException(401, "API key requerida. Incluye el header X-Api-Key.")
    client = _validate_key(x_api_key)
    if not client:
        raise HTTPException(401, "API key inválida, revocada o expirada.")
    if client.get("max_total_requests") is not None:
        used_total = total_requests_used(client["id"])
        if used_total >= client["max_total_requests"]:
            raise HTTPException(429, f"Límite de prueba alcanzado: {used_total}/{client['max_total_requests']} decretos usados. Contacta con nosotros para activar tu plan.")
    if client.get("monthly_decrees_limit") is not None:
        used_dec = monthly_decrees_used(client["id"])
        lim_dec = client["monthly_decrees_limit"]
        if used_dec >= lim_dec:
            raise HTTPException(429, f"Límite mensual alcanzado: {used_dec}/{lim_dec} decretos usados este mes. Configura tu propio servidor o aumenta el límite en tu configuración.")
    used = monthly_tokens_used(client["id"])
    if used >= client["monthly_token_budget"]:
        raise HTTPException(429, f"Budget mensual agotado ({used:,}/{client['monthly_token_budget']:,} tokens).")
    if not check_and_increment_rate(client["id"], client["max_requests_per_hour"]):
        raise HTTPException(429, f"Límite de {client['max_requests_per_hour']} consultas/hora alcanzado.")
    return client


async def require_master(x_master_key: Optional[str] = Header(None)):
    if not MASTER_KEY:
        raise HTTPException(503, "ENLIL_MASTER_KEY no configurada en el servidor.")
    if x_master_key != MASTER_KEY:
        raise HTTPException(403, "Acceso denegado.")
