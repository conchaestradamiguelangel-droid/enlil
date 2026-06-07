import os
from .gods.base import GodProfile
from .evolution import weighted_selection as _weighted_selection

EVOLUTION_ENABLED = os.environ.get("ENLIL_EVOLUTION", "1") != "0"

# Mapa de keywords → dominios
DOMAIN_KEYWORDS: dict[str, list[str]] = {
    "security":      ["seguridad", "ataque", "vulnerabilidad", "exploit", "firewall", "threat", "hack", "cve", "malware", "intrusion", "aegis", "ddos", "brute", "ransomware", "phishing"],
    "technical":     ["código", "bug", "error", "arquitectura", "api", "database", "algoritmo", "función", "python", "docker", "test", "deploy"],
    "communication": ["email", "correo", "cliente", "propuesta", "carta", "linkedin", "mensaje", "redactar", "presentación", "pitch"],
    "strategy":      ["estrategia", "decisión", "prioridad", "plan", "negocio", "mercado", "competencia", "producto"],
    "analysis":      ["análisis", "comparar", "evaluar", "estudiar", "investigar", "datos", "estadística"],
    "context":       ["proyecto", "estado", "resumen", "qué hay", "cómo va", "pendiente", "situación"],
    "supreme":       ["crítico", "irreversible", "definitivo", "veredicto", "juicio supremo", "decisión final", "inapelable"],
    "reasoning":     ["lógica", "deducción", "prueba", "teorema", "razonamiento", "inferencia", "demostración"],
    "adversarial":   ["red team", "penetración", "adversarial", "peor caso", "vector de ataque", "bypass", "evasión"],
    "creative":      ["creativo", "imagen", "visión", "diseño", "genera", "multimodal", "visual", "ilustra", "dibuja"],
}

# Dominios que activan a NERGAL
_NERGAL_DOMAINS = {"adversarial", "attack", "exploit", "red-team", "security"}


def classify_query(query: str) -> list[str]:
    q = query.lower()
    matched = set()
    for domain, keywords in DOMAIN_KEYWORDS.items():
        if any(kw in q for kw in keywords):
            matched.add(domain)
    return list(matched) if matched else ["context"]  # fallback al Dios de Contexto


def select_gods(
    domains: list[str],
    pantheon: dict[str, GodProfile],
    budget_tier: str = "standard",
) -> list[str]:
    """
    Devuelve los nombres de los dioses convocados.
    Con ENLIL_EVOLUTION=1 (default): selección por ruleta evolutiva con exploración.
    Con ENLIL_EVOLUTION=0: selección determinista por score.
    Guardas aplicadas post-selección:
      - MARDUK: solo en tier full
      - NERGAL: solo si dominios incluyen adversarial/attack/exploit/red-team/security
    """
    if EVOLUTION_ENABLED:
        selected = _weighted_selection(domains, pantheon, budget_tier)
    else:
        # Selección determinista (fallback / tests deterministas)
        limits = {"minimal": 2, "standard": 4, "full": len(pantheon)}
        limit = limits.get(budget_tier, 2)

        scores: dict[str, float] = {}
        for god_name, god in pantheon.items():
            score = sum(god.get_reputation(d) for d in domains if d in god.domains)
            if score > 0:
                scores[god_name] = score

        selected = ["claude"]
        for god_name, _ in sorted(scores.items(), key=lambda x: x[1], reverse=True):
            if len(selected) >= limit:
                break
            selected.append(god_name)

    # Guardas post-selección
    domain_set = set(domains)
    nergal_active = bool(domain_set & _NERGAL_DOMAINS)

    selected = [
        g for g in selected
        if not (g == "marduk" and budget_tier != "full")
        and not (g == "nergal" and not nergal_active)
    ]

    return selected
