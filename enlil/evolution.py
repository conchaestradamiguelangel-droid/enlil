"""
Motor evolutivo del panteón.
Aplica selección natural al Consejo: no elimina dioses,
ajusta la presión de selección basándose en fitness histórico.
"""
import random
from .gods.base import GodProfile

EXPLORATION_RATE = 0.15   # probabilidad de explorar dios no-top
DECAY_RATE       = 0.02   # velocidad de regreso al neutral cuando inactivo
MIN_FITNESS      = 0.1    # floor para evitar extinción total
PENALTY_THRESHOLD = 0.25  # por debajo de esto, el dios queda penalizado


def _god_fitness(god: GodProfile, domains: list[str]) -> float:
    """Fitness de un dios para estos dominios. 0.1 mínimo para no extinguir."""
    if not domains:
        return god.get_reputation("context")
    relevant = [d for d in domains if d in god.domains]
    if not relevant:
        return MIN_FITNESS
    score = sum(god.get_reputation(d) for d in relevant) / len(relevant)
    return max(MIN_FITNESS, score)


_NERGAL_DOMAINS = {"adversarial", "attack", "exploit", "red-team", "security"}


def weighted_selection(
    domains: list[str],
    pantheon: dict[str, GodProfile],
    budget_tier: str = "standard",
) -> list[str]:
    """
    Selección evolutiva del Consejo.
    Claude siempre convocado (invariante del sistema).
    El resto se selecciona por ruleta ponderada por fitness + exploración.
    Pre-filtros:
      - MARDUK excluido si tier != full
      - NERGAL excluido si dominios no incluyen adversarial/attack/exploit/red-team/security
    """
    limits = {"minimal": 2, "standard": 4, "full": len(pantheon)}
    limit = limits.get(budget_tier, 4)

    selected = ["claude"]
    if limit <= 1:
        return selected

    domain_set = set(domains)
    nergal_active = bool(domain_set & _NERGAL_DOMAINS)

    candidates = [
        name for name in pantheon
        if name != "claude"
        and not (name == "marduk" and budget_tier != "full")
        and not (name == "nergal" and not nergal_active)
    ]
    if not candidates:
        return selected

    # Calcular fitness de cada candidato
    fitness_map = {
        name: _god_fitness(pantheon[name], domains)
        for name in candidates
    }

    # Penalizar dioses con fitness global bajo
    for name, fit in fitness_map.items():
        if fit < PENALTY_THRESHOLD:
            fitness_map[name] = fit * 0.3

    remaining = limit - 1
    pool = list(candidates)

    for _ in range(remaining):
        if not pool:
            break

        if random.random() < EXPLORATION_RATE:
            # Exploración: dios aleatorio del pool
            chosen = random.choice(pool)
        else:
            # Explotación: ruleta ponderada por fitness
            weights = [fitness_map[name] for name in pool]
            total = sum(weights)
            if total == 0:
                chosen = random.choice(pool)
            else:
                r = random.random() * total
                cumulative = 0.0
                chosen = pool[-1]
                for name, w in zip(pool, weights):
                    cumulative += w
                    if r <= cumulative:
                        chosen = name
                        break

        selected.append(chosen)
        pool.remove(chosen)

    return selected


def apply_decay(
    decree_gods: list[str],
    pantheon: dict[str, GodProfile],
) -> None:
    """
    Decaimiento por inactividad.
    Dioses NO convocados en este decreto regresan lentamente al neutral (0.5).
    Los convocados no se tocan — su reputación la gestiona ReputationStore.
    """
    for god_name, god in pantheon.items():
        if god_name in decree_gods:
            continue
        for domain in list(god.reputation.keys()):
            current = god.reputation[domain]
            god.reputation[domain] = round(
                current + DECAY_RATE * (0.5 - current), 4
            )


def fitness_report(pantheon: dict[str, GodProfile]) -> dict:
    """
    Reporte de fitness evolutivo de cada dios.
    Muestra fitness global, por dominio y presión de selección.
    """
    report = {}
    all_domains = list({d for god in pantheon.values() for d in god.domains})

    for name, god in pantheon.items():
        domain_fitness = {
            d: round(_god_fitness(god, [d]), 4)
            for d in god.domains
        }
        global_fitness = round(
            sum(domain_fitness.values()) / len(domain_fitness)
            if domain_fitness else 0.5,
            4,
        )
        penalized = global_fitness < PENALTY_THRESHOLD
        selection_pressure = round(
            global_fitness * (0.3 if penalized else 1.0), 4
        )
        report[name] = {
            "global_fitness":    global_fitness,
            "domain_fitness":    domain_fitness,
            "penalized":         penalized,
            "selection_pressure": selection_pressure,
        }

    return {
        "gods": report,
        "exploration_rate": EXPLORATION_RATE,
        "decay_rate": DECAY_RATE,
        "penalty_threshold": PENALTY_THRESHOLD,
    }
