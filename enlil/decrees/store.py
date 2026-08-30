import sqlite3
import json
import os
from dataclasses import asdict
from .decree import Decree, GodVoice
from ..quantum import sign_decree, verify_decree
from ..reliability import AttemptResult, SynthesisAttempt

DEFAULT_DB = os.environ.get("ENLIL_DB", "enlil.db")

_VALID_STATUSES = ("complete", "partial", "failed")


class SchemaMismatchError(RuntimeError):
    """Una columna ya existente no coincide con la definición esperada
    (tipo, nullability o default) — la migración aborta en vez de asumir
    que 'el nombre coincide, ya vale'. Ver ENLIL_TEST01B_AUDITORIA_DISENO_V4/V6."""


# Esquema definitivo de columnas nuevas (V6 §2) — ninguna con DEFAULT
# distinto de NULL: nada de "desconocido" se convierte en un hecho por
# defecto. `accounting_complete` (v3) y `synthesis_tokens` (v3) quedan
# retirados del diseño, sustituidos por accounting_state/
# known_token_subtotal/observed_total_tokens/synthesis_attempts.
_EXPECTED_SCHEMA: dict[str, dict] = {
    "status":                    {"type": "TEXT",    "notnull": False, "dflt_value": None},
    "signature_payload_version": {"type": "INTEGER", "notnull": False, "dflt_value": None},
    "wall_clock_ms":              {"type": "REAL",    "notnull": False, "dflt_value": None},
    "accounting_state":           {"type": "TEXT",    "notnull": False, "dflt_value": None},
    "known_token_subtotal":       {"type": "INTEGER", "notnull": False, "dflt_value": None},
    "observed_total_tokens":      {"type": "INTEGER", "notnull": False, "dflt_value": None},
    "synthesis_attempts":         {"type": "TEXT",    "notnull": False, "dflt_value": None},
}


class DecreeStore:
    def __init__(self, db_path: str = DEFAULT_DB, connection: sqlite3.Connection | None = None):
        if connection is not None:
            self._connection = connection
        else:
            self._connection = sqlite3.connect(db_path, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._init_db()

    def _init_db(self):
        self._connection.execute(
            """CREATE TABLE IF NOT EXISTS decrees (
                id TEXT PRIMARY KEY,
                timestamp REAL NOT NULL,
                query TEXT NOT NULL,
                domains TEXT NOT NULL,
                gods_convened TEXT NOT NULL,
                voices TEXT NOT NULL,
                synthesis TEXT NOT NULL,
                total_tokens INTEGER NOT NULL,
                budget_tier TEXT NOT NULL,
                parent_decree_id TEXT,
                has_dissent INTEGER NOT NULL DEFAULT 0,
                pq_signature TEXT,
                vertical TEXT NOT NULL DEFAULT 'general',
                predicted_scores TEXT NOT NULL DEFAULT '{}'
            )"""
        )
        for col, sql in [
            ("client_id",       "ALTER TABLE decrees ADD COLUMN client_id TEXT NOT NULL DEFAULT 'default'"),
            ("pq_signature", "ALTER TABLE decrees ADD COLUMN pq_signature TEXT"),
            ("vertical",     "ALTER TABLE decrees ADD COLUMN vertical TEXT NOT NULL DEFAULT 'general'"),
            ("predicted_scores", "ALTER TABLE decrees ADD COLUMN predicted_scores TEXT NOT NULL DEFAULT '{}'"),
        ]:
            if not self._column_exists(col):
                self._connection.execute(sql)
        self._connection.commit()
        self._migrate_schema()
        self._assert_signature_version_invariant()

    def _column_exists(self, column: str) -> bool:
        cols = [r[1] for r in self._connection.execute("PRAGMA table_info(decrees)").fetchall()]
        return column in cols

    # ── Migración TEST 01B — validación de esquema completa, transaccional ──

    def _actual_schema(self) -> dict[str, dict]:
        rows = self._connection.execute("PRAGMA table_info(decrees)").fetchall()
        return {
            r["name"]: {"type": r["type"], "notnull": bool(r["notnull"]), "dflt_value": r["dflt_value"]}
            for r in rows
        }

    def _migrate_schema(self) -> None:
        """Añade las columnas nuevas de TEST 01B si faltan, validando
        estrictamente las que ya existan (tipo, nullability, DEFAULT).
        Transaccional: cualquier fallo hace rollback completo, no deja
        columnas a medias. El backfill de signature_payload_version=1
        ocurre EXCLUSIVAMENTE dentro de la rama que crea esa columna por
        primera vez, y solo para decretos ya firmados
        (pq_signature IS NOT NULL) — nunca en ejecuciones posteriores,
        nunca para históricos sin firma (ver V4 §7 / V6)."""
        self._connection.execute("BEGIN")
        try:
            actual = self._actual_schema()
            for col, spec in _EXPECTED_SCHEMA.items():
                if col not in actual:
                    self._connection.execute(f"ALTER TABLE decrees ADD COLUMN {col} {spec['type']}")
                    if col == "signature_payload_version":
                        self._connection.execute(
                            "UPDATE decrees SET signature_payload_version = 1 "
                            "WHERE signature_payload_version IS NULL AND pq_signature IS NOT NULL"
                        )
                else:
                    existing = actual[col]
                    # SQLite reporta dflt_value=None cuando la columna no
                    # tiene clausula DEFAULT en absoluto, pero devuelve el
                    # texto literal 'NULL' cuando la clausula fue escrita
                    # explicitamente como "DEFAULT NULL" -- ambas formas
                    # son semanticamente "sin valor por defecto real" y se
                    # aceptan igual. Solo un DEFAULT con un valor de
                    # verdad (p.ej. 'complete') debe abortar la migracion.
                    existing_default_is_null = existing["dflt_value"] in (None, "NULL")
                    if (existing["type"].upper() != spec["type"].upper()
                            or existing["notnull"] != spec["notnull"]
                            or not existing_default_is_null):
                        raise SchemaMismatchError(
                            f"columna '{col}' existe con definición incompatible: "
                            f"esperado {spec}, encontrado {existing}. "
                            f"Un DEFAULT distinto de NULL en un campo que debe empezar "
                            f"'desconocido' falsificaría datos históricos en silencio."
                        )
            self._connection.commit()
        except Exception:
            self._connection.rollback()
            raise

    def _assert_signature_version_invariant(self) -> None:
        """Postcondición obligatoria (V6 §5): ninguna fila puede tener
        firma sin versión. Se ejecuta en cada arranque, no solo cuando
        hay una migración pendiente. Si falla, el servicio no debe
        arrancar — nunca se autocorrige."""
        row = self._connection.execute(
            "SELECT COUNT(*) AS n FROM decrees "
            "WHERE pq_signature IS NOT NULL AND signature_payload_version IS NULL"
        ).fetchone()
        if row["n"] > 0:
            raise SchemaMismatchError(
                f"{row['n']} decreto(s) firmado(s) sin signature_payload_version asignado — "
                f"estado inconsistente, el servicio no arranca así. Nunca se autocorrige."
            )

    # ── Persistencia ─────────────────────────────────────────────────────

    def save(self, decree: Decree, client_id: str = "default"):
        """Persiste un decreto NUEVO. Exige (no asigna, no corrige):
        signature_payload_version == 2 y status en {complete,partial,failed}
        — responsabilidad única de quien crea el decreto (Orchestrator),
        ver ENLIL_TEST01B_AUDITORIA_DISENO_V4.md §8. Firma, status y
        versión se persisten atómicamente en la misma transacción que
        la firma que los cubre."""
        if decree.signature_payload_version != 2:
            raise ValueError(
                f"save() exige signature_payload_version==2 para decretos nuevos, "
                f"recibido: {decree.signature_payload_version!r}. Esto no se corrige "
                f"aquí — es responsabilidad de quien construye el Decree (Orchestrator)."
            )
        if decree.status not in _VALID_STATUSES:
            raise ValueError(f"save() exige status en {_VALID_STATUSES}, recibido: {decree.status!r}")

        voices_data = [
            {
                "god_name": v.god_name, "model": v.model, "content": v.content,
                "tokens_used": v.tokens_used, "latency_ms": v.latency_ms, "dissent": v.dissent,
                "voice_status": v.voice_status, "finish_reason": v.finish_reason,
                "retry_count": v.retry_count, "returned_model": v.returned_model,
                "reasoning_tokens": v.reasoning_tokens, "usage_state": v.usage_state,
                "attempts": [asdict(a) for a in v.attempts],
            }
            for v in decree.voices
        ]

        self._connection.execute("BEGIN")
        try:
            # 1-2. status/signature_payload_version ya fijados por el llamador (validado arriba).
            # 3-4. construir payload v2 exacto y firmar con esos valores, sin reasignarlos.
            pq_sig = sign_decree(
                decree.id, decree.query, decree.synthesis, decree.timestamp,
                payload_version=2, status=decree.status,
            )
            decree.pq_signature = pq_sig or None
            decree.client_id = client_id

            synthesis_attempts_json = (
                json.dumps([asdict(a) for a in decree.synthesis_attempts])
                if decree.synthesis_attempts is not None else None
            )

            # 5. persistir exactamente esos mismos campos + firma, misma transacción.
            self._connection.execute(
                """INSERT INTO decrees
                   (id, timestamp, query, domains, gods_convened, voices, synthesis,
                    total_tokens, budget_tier, parent_decree_id, has_dissent, pq_signature,
                    vertical, predicted_scores, client_id,
                    status, signature_payload_version, wall_clock_ms,
                    accounting_state, known_token_subtotal, observed_total_tokens,
                    synthesis_attempts)
                   VALUES (:id, :timestamp, :query, :domains, :gods_convened, :voices, :synthesis,
                           :total_tokens, :budget_tier, :parent_decree_id, :has_dissent, :pq_signature,
                           :vertical, :predicted_scores, :client_id,
                           :status, :signature_payload_version, :wall_clock_ms,
                           :accounting_state, :known_token_subtotal, :observed_total_tokens,
                           :synthesis_attempts)""",
                {
                    "id": decree.id, "timestamp": decree.timestamp, "query": decree.query,
                    "domains": json.dumps(decree.domains), "gods_convened": json.dumps(decree.gods_convened),
                    "voices": json.dumps(voices_data), "synthesis": decree.synthesis,
                    "total_tokens": decree.total_tokens, "budget_tier": decree.budget_tier,
                    "parent_decree_id": decree.parent_decree_id,
                    "has_dissent": 1 if decree.has_dissent() else 0,
                    "pq_signature": decree.pq_signature,
                    "vertical": getattr(decree, "vertical", "general"),
                    "predicted_scores": json.dumps(getattr(decree, "predicted_scores", {})),
                    "client_id": client_id,
                    "status": decree.status,
                    "signature_payload_version": decree.signature_payload_version,
                    "wall_clock_ms": decree.wall_clock_ms,
                    "accounting_state": decree.accounting_state,
                    "known_token_subtotal": decree.known_token_subtotal,
                    "observed_total_tokens": decree.observed_total_tokens,
                    "synthesis_attempts": synthesis_attempts_json,
                },
            )
            # 6. commit.
            self._connection.commit()
        except Exception:
            self._connection.rollback()
            raise

    def get(self, decree_id: str) -> Decree | None:
        row = self._connection.execute(
            "SELECT * FROM decrees WHERE id = ?", (decree_id,)
        ).fetchone()
        return self._row_to_decree(row) if row else None

    def recent(self, limit: int = 20, client_id=None) -> list[Decree]:
        if client_id:
            rows = self._connection.execute(
                "SELECT * FROM decrees WHERE client_id = ? ORDER BY timestamp DESC LIMIT ?",
                (client_id, limit)
            ).fetchall()
        else:
            rows = self._connection.execute(
                "SELECT * FROM decrees ORDER BY timestamp DESC LIMIT ?", (limit,)
            ).fetchall()
        return [self._row_to_decree(r) for r in rows]

    def count(self) -> int:
        row = self._connection.execute("SELECT COUNT(*) FROM decrees").fetchone()
        return row[0] if row else 0

    def _row_to_decree(self, row) -> Decree:
        r = dict(row)
        voices_raw = json.loads(r["voices"])
        voices = [
            GodVoice(
                god_name=v["god_name"], model=v["model"], content=v["content"],
                tokens_used=v["tokens_used"], latency_ms=v["latency_ms"],
                dissent=v.get("dissent"),
                voice_status=v.get("voice_status", "unknown"),
                finish_reason=v.get("finish_reason"),
                retry_count=v.get("retry_count", 0),
                returned_model=v.get("returned_model"),
                reasoning_tokens=v.get("reasoning_tokens"),
                usage_state=v.get("usage_state", "unknown"),
                attempts=[AttemptResult(**a) for a in v.get("attempts", [])],
            )
            for v in voices_raw
        ]
        raw_sa = r.get("synthesis_attempts")
        synthesis_attempts = (
            [SynthesisAttempt(**a) for a in json.loads(raw_sa)] if raw_sa is not None else None
        )
        obj = Decree(
            id=r["id"], timestamp=r["timestamp"], query=r["query"],
            domains=json.loads(r["domains"]), gods_convened=json.loads(r["gods_convened"]),
            voices=voices, synthesis=r["synthesis"], total_tokens=r["total_tokens"],
            budget_tier=r["budget_tier"], parent_decree_id=r["parent_decree_id"],
            pq_signature=r.get("pq_signature"),
            # Restaurar el propietario real — sin esto, api.py trata
            # cualquier decreto leído de SQLite como "default" y el
            # control de ownership no bloquea nada (hallazgo P0
            # 2026-08-29). Filas nulas/vacías (no deberían darse, la
            # columna es NOT NULL DEFAULT 'default', pero por si acaso)
            # caen también a "default", igual que los decretos
            # históricos anteriores a esta columna.
            client_id=r.get("client_id") or "default",
            status=r.get("status"),
            signature_payload_version=r.get("signature_payload_version"),
            wall_clock_ms=r.get("wall_clock_ms"),
            accounting_state=r.get("accounting_state"),
            known_token_subtotal=r.get("known_token_subtotal"),
            observed_total_tokens=r.get("observed_total_tokens"),
            synthesis_attempts=synthesis_attempts,
        )
        obj.vertical = r.get("vertical", "general")
        obj.predicted_scores = json.loads(r.get("predicted_scores", "{}") or "{}")
        return obj

    def verify(self, decree_id: str) -> dict:
        decree = self.get(decree_id)
        if not decree:
            return {"valid": False, "reason": "decreto no encontrado"}
        if not decree.pq_signature:
            return {"valid": False, "reason": "decreto sin firma PQ (anterior a S7)"}
        if decree.signature_payload_version not in (1, 2):
            return {
                "valid": False,
                "reason": (
                    f"versión de firma ausente o desconocida "
                    f"({decree.signature_payload_version!r}) — no se puede verificar "
                    f"sin asumir una versión, y eso no se hace nunca."
                ),
            }
        try:
            valid = verify_decree(
                decree.id, decree.query, decree.synthesis, decree.timestamp, decree.pq_signature,
                payload_version=decree.signature_payload_version, status=decree.status,
            )
        except ValueError as exc:
            return {"valid": False, "reason": f"versión de firma desconocida: {exc}"}
        return {
            "valid": valid,
            "decree_id": decree_id,
            "algorithm": "ML-DSA-87",
            "reason": "firma valida" if valid else "firma invalida o decreto manipulado",
        }
