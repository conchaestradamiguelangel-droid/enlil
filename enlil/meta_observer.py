"""
Meta-Observador — el dios silencioso del panteón.
No se convoca. No habla en el Consejo. Solo observa y aprende.
Detecta patrones estadísticos en el historial de decretos.
"""
from collections import defaultdict, Counter
from .decrees.store import DecreeStore
from .decrees.decree import Decree


class MetaObserver:
    """
    Dios pasivo. Aprende qué dioses funcionan mejor por dominio,
    qué pares generan más disidencia, y cómo evoluciona el panteón.
    """

    def __init__(self, store: DecreeStore):
        self._store = store

    def observe(self, decree: Decree) -> None:
        pass

    def patterns(self, limit: int = 200) -> dict:
        """
        Analiza los últimos `limit` decretos y retorna patrones aprendidos.
        Se recalcula solo cuando hay nuevos datos.
        """
        decrees = self._store.recent(limit)
        if not decrees:
            return {
                "status": "learning",
                "decree_count": 0,
                "message": "El Meta-Observador necesita más decretos para detectar patrones.",
            }

        total = len(decrees)

        # Dioses más convocados por dominio
        domain_god_count: dict[str, Counter] = defaultdict(Counter)
        for d in decrees:
            for domain in d.domains:
                for god in d.gods_convened:
                    domain_god_count[domain][god] += 1

        top_god_per_domain = {
            domain: [{"god": g, "count": c} for g, c in counts.most_common(3)]
            for domain, counts in domain_god_count.items()
        }

        # Ratio de disidencia por dios
        god_dissent: Counter = Counter()
        god_invocations: Counter = Counter()
        for d in decrees:
            for voice in d.voices:
                god_invocations[voice.god_name] += 1
                if voice.dissent:
                    god_dissent[voice.god_name] += 1

        dissent_ratio = {
            god: round(god_dissent[god] / count, 3)
            for god, count in god_invocations.items()
            if count > 0
        }

        # Latencia promedio por dios
        god_latencies: dict[str, list] = defaultdict(list)
        for d in decrees:
            for voice in d.voices:
                if voice.latency_ms > 0:
                    god_latencies[voice.god_name].append(voice.latency_ms)

        avg_latency_ms = {
            god: round(sum(lats) / len(lats), 1)
            for god, lats in god_latencies.items()
        }

        # Distribución de tiers de presupuesto
        tier_distribution = dict(Counter(d.budget_tier for d in decrees))

        # Dominios más frecuentes
        domain_counter: Counter = Counter()
        for d in decrees:
            for domain in d.domains:
                domain_counter[domain] += 1

        top_domains = [
            {"domain": dom, "count": cnt}
            for dom, cnt in domain_counter.most_common(5)
        ]

        # Pares de dioses en decretos con disidencia
        conflict_pairs: Counter = Counter()
        for d in decrees:
            if d.has_dissent():
                conflict_pairs[tuple(sorted(d.gods_convened))] += 1

        top_conflict_pairs = [
            {"gods": list(pair), "dissent_count": cnt}
            for pair, cnt in conflict_pairs.most_common(3)
        ]

        # Tendencia de tokens (mitad nueva vs mitad antigua)
        token_trend = "insufficient_data"
        if total >= 6:
            half = total // 2
            newer = [d.total_tokens for d in decrees[:half]]
            older = [d.total_tokens for d in decrees[half:]]
            newer_avg = sum(newer) / len(newer)
            older_avg = sum(older) / len(older)
            if newer_avg > older_avg * 1.1:
                token_trend = "up"
            elif newer_avg < older_avg * 0.9:
                token_trend = "down"
            else:
                token_trend = "stable"

        return {
            "status": "active",
            "decree_count": total,
            "top_god_per_domain": top_god_per_domain,
            "dissent_ratio": dissent_ratio,
            "avg_latency_ms": avg_latency_ms,
            "budget_distribution": tier_distribution,
            "top_domains": top_domains,
            "conflict_pairs": top_conflict_pairs,
            "token_trend": token_trend,
        }

    def recommend_gods(self, domains: list[str], available: list[str]) -> list[str]:
        """
        Sugiere qué dioses convocar basándose en efectividad histórica.
        Los dioses más frecuentemente convocados para esos dominios van primero.
        Falls back a `available` si no hay historial suficiente.
        """
        if not domains or not available:
            return available

        p = self.patterns()
        if p["status"] != "active":
            return available

        scores: Counter = Counter()
        top_per_domain = p.get("top_god_per_domain", {})

        for domain in domains:
            for entry in top_per_domain.get(domain, []):
                god = entry["god"]
                if god in available:
                    scores[god] += entry["count"]

        if not scores:
            return available

        ranked = [god for god, _ in scores.most_common() if god in available]
        rest = [god for god in available if god not in ranked]
        return ranked + rest
