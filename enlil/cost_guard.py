"""ENLIL — Guardarrail economico real (v2).

Gate en USD que se aplica en el UNICO choke point real de llamadas
pagadas: Council.consult_god() (enlil/council.py), justo despues del
kill switch ENLIL_ENABLED (_enlil_enabled()). Los dos gates son
independientes y se aplican en cascada: si ENLIL_ENABLED esta OFF nunca
se llega aqui; si esta ON, este modulo decide si ADEMAS hay presupuesto
real para la llamada concreta.

No sustituye ni toca el limite mensual de TOKENS por cliente que ya
existe en enlil/auth.py (monthly_token_budget) -- ese es un control de
equidad/facturacion por cliente en tokens; este es un control agregado
en USD, a nivel de todo el proceso, independiente de que cliente lo
pidio.

DOS gates independientes deben pasar para que este modulo apruebe una
llamada, ademas de los caps en USD:

1. Pricing verificado -- enlil.pricing.estimate_cost_usd()/
   VERIFIED_MODEL_PRICING (input/output separados, flag "verified"
   explicito -- vacia a proposito, ver docstring de enlil/pricing.py).
2. Metodo de contabilizacion de INPUT verificado para ese modelo --
   enlil.input_accounting.get_verified_accounting() (vacia a proposito
   tambien, ver su docstring). Este gate existe porque
   enlil.budget.estimate_content_token_upper_bound()/
   estimate_content_tokens_from_messages() SOLO acotan el contenido de
   texto que ENLIL construye y controla -- nunca framing/tools/
   reasoning/caching especificos del proveedor -- asi que ese numero
   nunca debe usarse para gastar dinero real sin una verificacion
   adicional, independiente del pricing.

Ambos gates fallan-cerrado por separado: un modelo con precio
verificado pero sin contabilizacion de input verificada (o viceversa)
sigue denegado. Los dos estan vacios hoy, asi que ningun modelo pasa
ninguno de los dos -- produccion sigue bloqueada hasta que un humano
rellene explicitamente cualquiera de las dos tablas con una fuente
real, decision fuera del alcance de este modulo.

CAP POR OPERACION LOGICA (v2): ENLIL_MAX_COST_PER_REQUEST_USD limita el
gasto AGREGADO de una operacion de consejo completa -- todos sus
intentos/retries/fallbacks compartiendo el mismo `operation_id` cuentan
juntos contra ese cap, no cada intento por separado. Una llamada sin
operation_id explicito recibe uno nuevo automaticamente (no comparte
presupuesto con nada mas).

ESTADOS DEL LEDGER (v2):
- reserved:   la reserva existe, la red AUN no se ha tocado. Puede
              liberarse (release()) SOLO si se puede garantizar que
              nunca se llego a llamar al proveedor.
- attempting: la llamada de red esta en curso o se intento -- si el
              proceso muere aqui, la fila se queda en este estado para
              siempre (v2 no implementa ninguna reconciliacion/TTL
              automatica) y sigue contando el worst-case reservado.
- settled:    coste real conocido con confianza (usage fiable del
              proveedor). Puede ser <= reserved_usd.
- uncertain:  la red fue tocada pero el resultado es incierto (timeout,
              excepcion tras iniciar la llamada, o respuesta sin
              `usage` fiable) -- se conserva el reserved_usd completo
              como gasto contado, nunca se reduce.
- released:   demostrado que NO hubo llamada facturable (p.ej. circuit
              breaker abierto sin fallback disponible) -- unico estado
              que cuenta actual_usd=0.0 explicito.

En todos los casos la suma que cuenta contra los caps es
COALESCE(actual_usd, reserved_usd) -- es decir, mientras algo no se
liquide explicitamente a un numero conocido (settled/released), sigue
contando el techo reservado completo. Nada desaparece por timeout.

Concurrencia: SQLite con journal_mode=WAL + una transaccion
BEGIN IMMEDIATE que lee el gasto agregado (por operacion/dia/mes) y
reserva el coste estimado de la llamada actual en la MISMA transaccion.
Esto serializa a cualquier proceso/worker que escriba al MISMO fichero
SQLite en la MISMA maquina y evita que dos llamadas concurrentes vean
el mismo saldo "libre" y aprueben ambas por encima del cap. NO es un
lock distribuido entre maquinas distintas -- si ENLIL se despliega
alguna vez en varios hosts sin un unico fichero/volumen SQLite
compartido, este mecanismo deja de ser suficiente por si solo y haria
falta un backend distribuido real (Postgres con SELECT... FOR UPDATE,
Redis, etc). Hoy ENLIL corre como un unico proceso uvicorn (sin
`--workers`) en una sola maquina, asi que esta garantia ya cubre el
caso real; si algun dia se pasa a multiples workers en la MISMA
maquina, sigue cubierto siempre que compartan el mismo fichero
(WorkingDirectory=/root/enlil, path relativo resuelto ahi).

Periodos: dia/mes se calculan siempre en UTC
(datetime.now(timezone.utc)), deterministas e independientes de la
zona horaria del VPS.

Fail-closed explicito: si los caps no estan configurados (ausentes o
invalidos), si el coste no se puede estimar, o si el almacenamiento del
presupuesto no se puede leer/escribir con seguridad, SIEMPRE se deniega
la llamada -- nunca se aproxima a "sin limite" por defecto.

Sin TTL/reconciliacion automatica en v2: una reserva que quede en
'reserved' o 'attempting' por un crash del proceso NO se libera nunca
sola. Sigue contando contra el presupuesto para siempre hasta que
alguien la reconcilie manualmente (fuera de alcance de v2) -- es la
direccion segura (nunca subestimar), a costa de requerir intervencion
humana si se acumulan reservas huerfanas.
"""
from __future__ import annotations

import logging
import os
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from .pricing import estimate_cost_usd, PricingNotVerifiedError
from .input_accounting import get_verified_accounting, InputAccountingNotVerifiedError

_logger = logging.getLogger("enlil.cost_guard")

_DEFAULT_DB_PATH = "./data/enlil_cost_ledger.db"


class BudgetDeniedError(RuntimeError):
    """La llamada NO se autoriza -- fail-closed. `.reason` es un codigo
    estable para logs/tests, nunca contiene secretos."""

    def __init__(self, reason: str, detail: str = ""):
        self.reason = reason
        self.detail = detail
        super().__init__(f"{reason}: {detail}" if detail else reason)


@dataclass(frozen=True)
class BudgetConfig:
    per_request_cap_usd: float
    daily_cap_usd: float
    monthly_cap_usd: float
    db_path: str


@dataclass(frozen=True)
class Reservation:
    id: int
    operation_id: str
    estimated_usd: float
    daily_remaining_usd: float
    monthly_remaining_usd: float


def _parse_positive_float(raw: str | None) -> float | None:
    if raw is None or raw.strip() == "":
        return None
    try:
        value = float(raw)
    except ValueError:
        return None
    if value <= 0:
        return None
    return value


def load_config() -> BudgetConfig | None:
    """Lee los 3 caps desde el entorno. Fail-closed: si CUALQUIERA falta,
    esta vacio, no es numerico o es <= 0, devuelve None (config invalida
    -- el caller debe denegar, nunca asumir "sin limite")."""
    per_request = _parse_positive_float(os.environ.get("ENLIL_MAX_COST_PER_REQUEST_USD"))
    daily = _parse_positive_float(os.environ.get("ENLIL_MAX_COST_DAILY_USD"))
    monthly = _parse_positive_float(os.environ.get("ENLIL_MAX_COST_MONTHLY_USD"))
    if per_request is None or daily is None or monthly is None:
        return None
    db_path = os.environ.get("ENLIL_COST_LEDGER_DB", _DEFAULT_DB_PATH)
    return BudgetConfig(
        per_request_cap_usd=per_request,
        daily_cap_usd=daily,
        monthly_cap_usd=monthly,
        db_path=db_path,
    )


def _db(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, timeout=10, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS cost_ledger (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at   TEXT NOT NULL,
            day          TEXT NOT NULL,
            month        TEXT NOT NULL,
            model        TEXT NOT NULL,
            operation_id TEXT NOT NULL,
            context      TEXT NOT NULL DEFAULT '',
            status       TEXT NOT NULL CHECK(
                status IN ('reserved', 'attempting', 'settled', 'uncertain', 'released')
            ),
            reserved_usd REAL NOT NULL,
            actual_usd   REAL
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_cost_ledger_day ON cost_ledger(day)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_cost_ledger_month ON cost_ledger(month)")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_cost_ledger_operation ON cost_ledger(operation_id)"
    )
    return conn


def _spent_usd(conn: sqlite3.Connection, *, column: str, value: str) -> float:
    row = conn.execute(
        f"SELECT COALESCE(SUM(COALESCE(actual_usd, reserved_usd)), 0.0) AS total "
        f"FROM cost_ledger WHERE {column} = ?",
        (value,),
    ).fetchone()
    return float(row["total"])


def reserve(
    model: str,
    max_output_tokens: int,
    *,
    input_tokens: int = 0,
    operation_id: str | None = None,
    context: str = "",
) -> Reservation:
    """Punto unico de entrada del guardarrail. Debe llamarse INMEDIATAMENTE
    antes de cualquier llamada pagada real (hoy: al principio de
    Council.consult_god(), justo tras el kill switch), con `messages` ya
    construidos localmente (permitido) pero SIN haber tocado la red
    todavia.

    `input_tokens` es la cota de CONTENIDO que el caller ya calculo con
    enlil.budget.estimate_content_tokens_from_messages() -- NO se
    confia en ese numero por si solo (ver enlil/input_accounting.py:
    esa cota de contenido nunca incluye framing/tools/reasoning/caching
    especificos del proveedor). Para que esta funcion acepte gastar
    dinero real con ese numero, el MODELO debe tener ademas un metodo
    de contabilizacion de input verificado (get_verified_accounting());
    sin eso, fail-closed, independientemente de si el pricing esta
    verificado. `max_output_tokens` es el techo de tokens de salida ya
    decidido para esta llamada. El coste reservado es SIEMPRE
    input+output juntos, el techo real de lo que podria facturarse.

    Si `operation_id` es None se genera uno nuevo automaticamente (la
    llamada no comparte presupuesto por-operacion con nada mas). Para
    que varios intentos/retries de UNA misma operacion cuenten juntos
    contra ENLIL_MAX_COST_PER_REQUEST_USD, el caller debe generar UN
    operation_id y pasarlo en cada intento (ver
    Council._consult_god_with_retry()).

    Lanza BudgetDeniedError (fail-closed) si no se puede aprobar la
    llamada; si no lanza, devuelve una Reservation que DEBE liquidarse
    despues con settle()/settle_uncertain()/release()."""
    op_id = operation_id or uuid.uuid4().hex

    config = load_config()
    if config is None:
        _logger.warning(
            "[COST_GUARD] DENY reason=config_unavailable_fail_closed model=%s "
            "operation_id=%s context=%s",
            model, op_id, context,
        )
        raise BudgetDeniedError(
            "config_unavailable_fail_closed",
            "ENLIL_MAX_COST_PER_REQUEST_USD/ENLIL_MAX_COST_DAILY_USD/ENLIL_MAX_COST_MONTHLY_USD "
            "ausentes o invalidas -- fail-closed",
        )

    # Gate independiente del pricing: sin un metodo de contabilizacion
    # de input VERIFICADO para este modelo concreto, no hay forma de
    # confiar en `input_tokens` como cota real del input facturable --
    # se comprueba ANTES de calcular ningun coste, y falla-cerrado
    # incluso si el pricing de este mismo modelo SI esta verificado.
    try:
        get_verified_accounting(model)
    except InputAccountingNotVerifiedError as exc:
        _logger.warning(
            "[COST_GUARD] DENY reason=input_accounting_not_verified_fail_closed model=%s "
            "operation_id=%s context=%s",
            model, op_id, context,
        )
        raise BudgetDeniedError("input_accounting_not_verified_fail_closed", model) from exc

    try:
        estimated = estimate_cost_usd(
            model,
            prompt_tokens=max(int(input_tokens), 0),
            completion_tokens=max(int(max_output_tokens), 0),
        )
    except PricingNotVerifiedError as exc:
        _logger.warning(
            "[COST_GUARD] DENY reason=pricing_not_verified_fail_closed model=%s "
            "operation_id=%s context=%s",
            model, op_id, context,
        )
        raise BudgetDeniedError("pricing_not_verified_fail_closed", model) from exc
    except Exception as exc:  # nunca dejar que un fallo de estimacion abra la puerta
        _logger.warning(
            "[COST_GUARD] DENY reason=cost_unknown_fail_closed model=%s operation_id=%s "
            "context=%s error=%s",
            model, op_id, context, type(exc).__name__,
        )
        raise BudgetDeniedError("cost_unknown_fail_closed", type(exc).__name__) from exc

    if not isinstance(estimated, (int, float)) or estimated != estimated or estimated < 0:
        # estimated != estimated descarta NaN sin importar math.isnan
        _logger.warning(
            "[COST_GUARD] DENY reason=cost_unknown_fail_closed model=%s operation_id=%s "
            "context=%s estimated=%r",
            model, op_id, context, estimated,
        )
        raise BudgetDeniedError("cost_unknown_fail_closed", f"estimated={estimated!r}")

    now = datetime.now(timezone.utc)
    day = now.strftime("%Y-%m-%d")
    month = now.strftime("%Y-%m")

    try:
        conn = _db(config.db_path)
    except Exception as exc:
        _logger.error(
            "[COST_GUARD] DENY reason=storage_unavailable_fail_closed model=%s "
            "operation_id=%s context=%s error=%s",
            model, op_id, context, type(exc).__name__,
        )
        raise BudgetDeniedError("storage_unavailable_fail_closed", type(exc).__name__) from exc

    try:
        conn.execute("BEGIN IMMEDIATE")
        try:
            operation_spent = _spent_usd(conn, column="operation_id", value=op_id)
            daily_spent = _spent_usd(conn, column="day", value=day)
            monthly_spent = _spent_usd(conn, column="month", value=month)

            if operation_spent + estimated > config.per_request_cap_usd:
                conn.execute("ROLLBACK")
                _logger.warning(
                    "[COST_GUARD] DENY reason=per_request_cap_exceeded model=%s "
                    "operation_id=%s context=%s estimated_usd=%.6f operation_spent_usd=%.6f "
                    "per_request_cap_usd=%.6f",
                    model, op_id, context, estimated, operation_spent, config.per_request_cap_usd,
                )
                raise BudgetDeniedError(
                    "per_request_cap_exceeded",
                    f"estimated_usd={estimated:.6f} operation_spent_usd={operation_spent:.6f} "
                    f"per_request_cap_usd={config.per_request_cap_usd:.6f}",
                )

            if daily_spent + estimated > config.daily_cap_usd:
                conn.execute("ROLLBACK")
                _logger.warning(
                    "[COST_GUARD] DENY reason=daily_cap_exceeded model=%s operation_id=%s "
                    "context=%s estimated_usd=%.6f daily_spent_usd=%.6f daily_cap_usd=%.6f",
                    model, op_id, context, estimated, daily_spent, config.daily_cap_usd,
                )
                raise BudgetDeniedError(
                    "daily_cap_exceeded",
                    f"estimated_usd={estimated:.6f} daily_spent_usd={daily_spent:.6f} "
                    f"daily_cap_usd={config.daily_cap_usd:.6f}",
                )

            if monthly_spent + estimated > config.monthly_cap_usd:
                conn.execute("ROLLBACK")
                _logger.warning(
                    "[COST_GUARD] DENY reason=monthly_cap_exceeded model=%s operation_id=%s "
                    "context=%s estimated_usd=%.6f monthly_spent_usd=%.6f monthly_cap_usd=%.6f",
                    model, op_id, context, estimated, monthly_spent, config.monthly_cap_usd,
                )
                raise BudgetDeniedError(
                    "monthly_cap_exceeded",
                    f"estimated_usd={estimated:.6f} monthly_spent_usd={monthly_spent:.6f} "
                    f"monthly_cap_usd={config.monthly_cap_usd:.6f}",
                )

            cur = conn.execute(
                "INSERT INTO cost_ledger "
                "(created_at, day, month, model, operation_id, context, status, "
                " reserved_usd, actual_usd) "
                "VALUES (?, ?, ?, ?, ?, ?, 'reserved', ?, NULL)",
                (now.isoformat(), day, month, model, op_id, context, estimated),
            )
            reservation_id = cur.lastrowid
            conn.execute("COMMIT")
        except BudgetDeniedError:
            raise
        except Exception:
            conn.execute("ROLLBACK")
            raise
    except BudgetDeniedError:
        raise
    except Exception as exc:
        _logger.error(
            "[COST_GUARD] DENY reason=storage_unavailable_fail_closed model=%s "
            "operation_id=%s context=%s error=%s",
            model, op_id, context, type(exc).__name__,
        )
        raise BudgetDeniedError("storage_unavailable_fail_closed", type(exc).__name__) from exc
    finally:
        conn.close()

    daily_remaining = config.daily_cap_usd - daily_spent - estimated
    monthly_remaining = config.monthly_cap_usd - monthly_spent - estimated
    _logger.info(
        "[COST_GUARD] RESERVE model=%s operation_id=%s context=%s estimated_usd=%.6f "
        "daily_remaining_usd=%.6f monthly_remaining_usd=%.6f reservation_id=%s",
        model, op_id, context, estimated, daily_remaining, monthly_remaining, reservation_id,
    )
    return Reservation(
        id=reservation_id,
        operation_id=op_id,
        estimated_usd=estimated,
        daily_remaining_usd=daily_remaining,
        monthly_remaining_usd=monthly_remaining,
    )


def _update_status(
    reservation_id: int, *, status: str, actual_usd: float | None, db_path: str | None,
) -> None:
    config = load_config()
    path = db_path or (config.db_path if config else _DEFAULT_DB_PATH)
    try:
        conn = _db(path)
        try:
            conn.execute(
                "UPDATE cost_ledger SET status=?, actual_usd=? WHERE id=?",
                (status, actual_usd, reservation_id),
            )
        finally:
            conn.close()
    except Exception as exc:
        # Liquidar/marcar es best-effort: si falla, la fila se queda como
        # estaba (reserved/attempting con reserved_usd) -- eso sigue
        # contando el worst-case completo via COALESCE(). El gasto nunca
        # desaparece del ledger por un fallo de almacenamiento aqui.
        _logger.error(
            "[COST_GUARD] %s_FAILED reservation_id=%s actual_usd=%s error=%s",
            status.upper(), reservation_id, actual_usd, type(exc).__name__,
        )


def mark_attempting(reservation_id: int, *, db_path: str | None = None) -> None:
    """Marca que la llamada de red va a intentarse AHORA. Puramente para
    forense de crash -- si el proceso muere despues de esto, la fila
    queda en 'attempting' para siempre y sigue contando el worst-case
    reservado (nadie la libera sola)."""
    _update_status(reservation_id, status="attempting", actual_usd=None, db_path=db_path)


def settle(reservation_id: int, actual_usd: float, *, db_path: str | None = None) -> None:
    """Liquida con el coste REAL conocido con confianza (usage fiable del
    proveedor). Puede ser menor que la reserva original."""
    _update_status(
        reservation_id, status="settled", actual_usd=float(actual_usd), db_path=db_path
    )


def settle_uncertain(reservation_id: int, reserved_usd: float, *, db_path: str | None = None) -> None:
    """La red fue tocada pero no se puede confiar en el resultado
    (timeout, excepcion tras iniciar la llamada, usage ausente). Se
    conserva el reserved_usd completo -- NUNCA se reduce el gasto
    contado ante incertidumbre."""
    _update_status(
        reservation_id, status="uncertain", actual_usd=float(reserved_usd), db_path=db_path
    )


def release(reservation_id: int, *, db_path: str | None = None) -> None:
    """Libera la reserva a coste 0 -- SOLO cuando se puede demostrar que
    la red nunca fue tocada para esta llamada (p.ex. circuit breaker
    abierto sin cliente de fallback disponible)."""
    _update_status(reservation_id, status="released", actual_usd=0.0, db_path=db_path)
