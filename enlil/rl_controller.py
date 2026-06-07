import sqlite3
import time
import hashlib


class RLController:
    """
    Controlador de Reinforcement Learning auto-supervisado para ENLIL.
    Señal de recompensa: score 0-10 del SynthesisEvaluator → normalizado a 0-1.
    Policy gradient simple: EMA de rewards acumula policy_weight por dios/dominio.
    """

    _EMA_ALPHA = 0.1        # factor EMA para update de policy weights
    _BUFFER_WINDOW_DAYS = 7  # ventana de rewards para policy update
    _WEIGHT_MIN = 0.1
    _WEIGHT_MAX = 2.0

    def __init__(self, connection: sqlite3.Connection):
        self._db = connection
        self._init_tables()

    def _init_tables(self):
        self._db.execute("""
            CREATE TABLE IF NOT EXISTS rl_buffer (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                god_name TEXT NOT NULL,
                domain TEXT NOT NULL,
                state_hash TEXT NOT NULL,
                reward REAL NOT NULL,
                timestamp REAL NOT NULL
            )
        """)
        self._db.execute("""
            CREATE TABLE IF NOT EXISTS rl_policy (
                god_name TEXT NOT NULL,
                domain TEXT NOT NULL,
                policy_weight REAL NOT NULL DEFAULT 1.0,
                last_updated REAL NOT NULL,
                PRIMARY KEY (god_name, domain)
            )
        """)
        self._db.execute("""
            CREATE TABLE IF NOT EXISTS rl_prediction_errors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                god_name TEXT NOT NULL,
                domain TEXT NOT NULL,
                prediction_error REAL NOT NULL,
                actual_score REAL NOT NULL,
                timestamp REAL NOT NULL
            )
        """)
        self._db.execute(
            "CREATE INDEX IF NOT EXISTS idx_rl_buffer_ts ON rl_buffer(timestamp)"
        )
        self._db.execute(
            "CREATE INDEX IF NOT EXISTS idx_rl_errors_ts ON rl_prediction_errors(timestamp)"
        )
        self._db.commit()

    def _state_hash(self, god_name: str, domains: list[str]) -> str:
        state = f"{god_name}:{','.join(sorted(domains))}"
        return hashlib.md5(state.encode()).hexdigest()[:8]

    def record_reward(
        self,
        god_names: list[str],
        domains: list[str],
        synthesis_score: float,
    ) -> None:
        """Score 0-10 → reward 0-1, acumulado por dios y dominio en SQLite."""
        reward = max(0.0, min(1.0, synthesis_score / 10.0))
        now = time.time()
        rows = [
            (god_name, domain, self._state_hash(god_name, domains), reward, now)
            for god_name in god_names
            for domain in domains
        ]
        self._db.executemany(
            "INSERT INTO rl_buffer (god_name, domain, state_hash, reward, timestamp) VALUES (?,?,?,?,?)",
            rows,
        )
        self._db.commit()

    def update_policy(self, pantheon) -> None:
        """Policy gradient: ajusta routing_weight por dios/dominio con EMA de rewards recientes."""
        cutoff = time.time() - self._BUFFER_WINDOW_DAYS * 86400
        rows = self._db.execute("""
            SELECT god_name, domain, AVG(reward) as avg_reward
            FROM rl_buffer
            WHERE timestamp > ?
            GROUP BY god_name, domain
        """, (cutoff,)).fetchall()

        now = time.time()
        for god_name, domain, avg_reward in rows:
            row = self._db.execute(
                "SELECT policy_weight FROM rl_policy WHERE god_name=? AND domain=?",
                (god_name, domain),
            ).fetchone()
            current = row[0] if row else 1.0
            new_weight = round(
                current + self._EMA_ALPHA * (avg_reward - current), 4
            )
            new_weight = max(self._WEIGHT_MIN, min(self._WEIGHT_MAX, new_weight))
            self._db.execute(
                "INSERT OR REPLACE INTO rl_policy (god_name, domain, policy_weight, last_updated) VALUES (?,?,?,?)",
                (god_name, domain, new_weight, now),
            )
        # Purgar registros fuera de ventana doble — evita crecimiento indefinido
        purge_cutoff = time.time() - self._BUFFER_WINDOW_DAYS * 2 * 86400
        self._db.execute("DELETE FROM rl_buffer WHERE timestamp < ?", (purge_cutoff,))
        self._db.execute("DELETE FROM rl_prediction_errors WHERE timestamp < ?", (purge_cutoff,))
        self._db.commit()

    def get_policy_weight(self, god_name: str, domain: str) -> float:
        """Policy weight actual para un dios/dominio. Default 1.0 (neutral)."""
        row = self._db.execute(
            "SELECT policy_weight FROM rl_policy WHERE god_name=? AND domain=?",
            (god_name, domain),
        ).fetchone()
        return row[0] if row else 1.0

    def record_prediction_errors(
        self,
        errors: dict[str, float],
        domains: list[str],
        actual_score: float,
    ) -> None:
        """Stores prediction errors per god/domain for routing audit and convergence tracking."""
        now = time.time()
        rows = [
            (god_name, domain, error, actual_score, now)
            for god_name, error in errors.items()
            for domain in domains
        ]
        self._db.executemany(
            "INSERT INTO rl_prediction_errors (god_name, domain, prediction_error, actual_score, timestamp) VALUES (?,?,?,?,?)",
            rows,
        )
        self._db.commit()

    def avg_prediction_error(self, window_days: int = 7) -> dict[str, float]:
        """Average prediction error per god over recent window. Lower = better calibration."""
        cutoff = time.time() - window_days * 86400
        rows = self._db.execute("""
            SELECT god_name, AVG(prediction_error) as avg_err
            FROM rl_prediction_errors
            WHERE timestamp > ?
            GROUP BY god_name
        """, (cutoff,)).fetchall()
        return {r[0]: round(r[1], 3) for r in rows}

    def health_check(self, pantheon, window_hours: int = 24) -> list[str]:
        """Retorna lista de alertas: dioses sin feedback RL en las últimas N horas."""
        cutoff = time.time() - window_hours * 3600
        alerts = []
        for god_name in pantheon:
            row = self._db.execute(
                "SELECT MAX(timestamp) FROM rl_buffer WHERE god_name=?",
                (god_name,),
            ).fetchone()
            last_ts = row[0] if row and row[0] else None
            if last_ts is None:
                alerts.append(f"{god_name.upper()} sin feedback RL registrado")
            elif last_ts < cutoff:
                hours_ago = int((time.time() - last_ts) / 3600)
                alerts.append(f"{god_name.upper()} sin feedback RL en las últimas {hours_ago}h")
        return alerts

    def status_report(self, pantheon) -> dict:
        """Métricas RL: policy weights, reward history, health."""
        weights: dict = {}
        for row in self._db.execute(
            "SELECT god_name, domain, policy_weight, last_updated FROM rl_policy"
        ).fetchall():
            god_name, domain, weight, last_updated = row
            weights.setdefault(god_name, {})[domain] = {
                "weight": weight,
                "last_updated": last_updated,
            }

        history = [
            {"god": r[0], "domain": r[1], "reward": r[2], "timestamp": r[3]}
            for r in self._db.execute(
                "SELECT god_name, domain, reward, timestamp FROM rl_buffer ORDER BY timestamp DESC LIMIT 100"
            ).fetchall()
        ]

        buffer_size = self._db.execute("SELECT COUNT(*) FROM rl_buffer").fetchone()[0]

        return {
            "policy_weights": weights,
            "reward_history": history,
            "health_alerts": self.health_check(pantheon),
            "buffer_size": buffer_size,
            "avg_prediction_error": self.avg_prediction_error(),
        }
