import os
import re
import unicodedata

try:
    import numpy as _np
    _NP_AVAILABLE = True
except ImportError:
    _NP_AVAILABLE = False

from .gods.base import GodProfile
from .evolution import weighted_selection as _weighted_selection

EVOLUTION_ENABLED = os.environ.get("ENLIL_EVOLUTION", "1") != "0"

# Mapa de keywords -> dominios (expandido con sinonimos, ingles y variantes)
DOMAIN_KEYWORDS: dict[str, list[str]] = {
    "security":      ["seguridad", "ataque", "vulnerabilidad", "exploit", "firewall", "threat",
                      "hack", "cve", "malware", "intrusion", "aegis", "ddos", "brute", "ransomware",
                      "phishing", "breach", "cifrado", "cifrar", "criptografia", "autenticacion",
                      "autorizacion", "zero day", "parche", "patch", "siem", "soc", "pentest",
                      "amenaza", "ciberataque", "ciberseguridad", "riesgo", "incidente", "forense",
                      "ens", "iso 27001", "gdpr", "dora", "nist", "mitre", "ttp", "injection",
                      "sql injection", "xss", "csrf", "owasp", "pentest", "red team"],
    "technical":     ["codigo", "bug", "error", "arquitectura", "api", "database", "algoritmo",
                      "funcion", "python", "docker", "test", "deploy", "server", "backend",
                      "frontend", "react", "fastapi", "sql", "base de datos", "endpoint",
                      "microservicio", "kubernetes", "ci cd", "pipeline", "refactor",
                      "rendimiento", "performance", "latencia", "optimizar", "memoria",
                      "async", "concurrencia", "thread", "modelo", "ml", "ia", "llm",
                      "programar", "implementar", "infraestructura", "nube", "cloud",
                      "javascript", "typescript", "java", "golang", "rust", "git", "github",
                      "servidor", "proceso", "servicio", "sistema", "software"],
    "communication": ["email", "correo", "cliente", "propuesta", "carta", "linkedin",
                      "mensaje", "redactar", "presentacion", "pitch", "comunicado",
                      "anuncio", "newsletter", "outreach", "redes sociales", "post",
                      "marketing", "contenido", "copywriting", "tono", "discurso",
                      "argumentar", "persuadir", "convencer", "audiencia", "reunion",
                      "negociacion", "respuesta", "seguimiento", "follow up"],
    "strategy":      ["estrategia", "decision", "prioridad", "plan", "negocio", "mercado",
                      "competencia", "producto", "modelo de negocio", "startup", "pivote",
                      "expansion", "crecimiento", "objetivo", "kpi", "roadmap",
                      "venture", "inversor", "funding", "revenue", "monetizar",
                      "partnership", "alianza", "go to market", "posicionamiento",
                      "oportunidad", "riesgo de negocio", "cuota", "traccion", "escalar"],
    "analysis":      ["analisis", "comparar", "evaluar", "estudiar", "investigar", "datos",
                      "estadistica", "metricas", "informe", "reporte", "tendencia",
                      "diagnostico", "auditoria", "revision", "benchmark", "validar",
                      "hipotesis", "correlacion", "causa", "efecto", "interpretar",
                      "dashboard", "grafico", "visualizar", "dataset", "muestra",
                      "encuesta", "feedback", "resultado", "conclusion", "hallazgo"],
    "context":       ["proyecto", "estado", "resumen", "que hay", "como va", "pendiente",
                      "situacion", "actualizacion", "novedad", "contexto", "overview",
                      "donde estamos", "progreso", "avance", "que falta", "status"],
    "supreme":       ["critico", "irreversible", "definitivo", "veredicto", "juicio supremo",
                      "decision final", "inapelable", "maximo riesgo", "no hay vuelta atras",
                      "consecuencias graves", "urgente y critico", "last resort", "definitivo"],
    "reasoning":     ["logica", "deduccion", "prueba", "teorema", "razonamiento",
                      "inferencia", "demostracion", "argumento", "contraargumento",
                      "premisa", "conclusion", "silogismo", "paradoja", "critica",
                      "refutar", "verificar", "comprobar", "demostrar", "por que",
                      "causa raiz", "explicar", "justificar"],
    "adversarial":   ["red team", "penetracion", "adversarial", "peor caso", "vector de ataque",
                      "bypass", "evasion", "punto debil", "fallo", "brecha", "contramedida",
                      "detectar fallos", "donde falla", "critica destructiva", "worst case",
                      "como podria fallar", "que podria salir mal", "adversario", "oponente"],
    "creative":      ["creativo", "imagen", "vision", "diseno", "genera", "multimodal",
                      "visual", "ilustra", "dibuja", "narrativa", "historia",
                      "storytelling", "marca", "identidad", "concepto", "innovar",
                      "propuesta de valor", "diferenciacion", "eslogan", "nombre",
                      "brainstorm", "ideas", "experiencia de usuario", "ux", "ui",
                      "prototipo", "mockup", "landing", "viral", "meme"],
}

_NERGAL_DOMAINS = {"adversarial", "attack", "exploit", "red-team", "security"}


def _norm_text(text: str) -> str:
    text = text.lower()
    text = "".join(
        c for c in unicodedata.normalize("NFD", text)
        if unicodedata.category(c) != "Mn"
    )
    return text


def _tokenize(text: str) -> list[str]:
    words = re.findall(r"\b\w+\b", _norm_text(text))
    unigrams = words
    bigrams = [words[i] + " " + words[i + 1] for i in range(len(words) - 1)]
    return unigrams + bigrams


# Build vocabulary and domain vectors at import time
_VOCAB: dict[str, int] = {}
for _terms in DOMAIN_KEYWORDS.values():
    for _term in _terms:
        for _tok in _tokenize(_term):
            if _tok not in _VOCAB:
                _VOCAB[_tok] = len(_VOCAB)

_DOMAIN_VECTORS: dict = {}
if _NP_AVAILABLE:
    for _domain, _terms in DOMAIN_KEYWORDS.items():
        v = _np.zeros(len(_VOCAB))
        for _term in _terms:
            for _tok in _tokenize(_term):
                if _tok in _VOCAB:
                    v[_VOCAB[_tok]] += 1.0
        _norm_val = _np.linalg.norm(v)
        if _norm_val > 0:
            v /= _norm_val
        _DOMAIN_VECTORS[_domain] = v


def classify_query(query: str, threshold: float = 0.08) -> list[str]:
    """Classifies query using cosine similarity against domain vectors.
    Returns domains sorted by relevance. Falls back to keyword matching if numpy unavailable.
    """
    if not _NP_AVAILABLE or not _DOMAIN_VECTORS:
        return _classify_keywords(query)

    toks = _tokenize(query)
    q_vec = _np.zeros(len(_VOCAB))
    for tok in toks:
        if tok in _VOCAB:
            q_vec[_VOCAB[tok]] += 1.0

    norm = _np.linalg.norm(q_vec)
    if norm == 0:
        return ["context"]
    q_vec /= norm

    scores = {
        domain: float(_np.dot(q_vec, dv))
        for domain, dv in _DOMAIN_VECTORS.items()
    }
    matched = sorted(
        [d for d, s in scores.items() if s >= threshold],
        key=lambda d: scores[d],
        reverse=True,
    )
    return matched if matched else ["context"]


def _classify_keywords(query: str) -> list[str]:
    q = _norm_text(query)
    matched = set()
    for domain, keywords in DOMAIN_KEYWORDS.items():
        if any(_norm_text(kw) in q for kw in keywords):
            matched.add(domain)
    return list(matched) if matched else ["context"]


def select_gods(
    domains: list[str],
    pantheon: dict[str, GodProfile],
    budget_tier: str = "standard",
) -> list[str]:
    """Returns the names of the gods to convene for the given domains and budget tier."""
    if EVOLUTION_ENABLED:
        selected = _weighted_selection(domains, pantheon, budget_tier)
    else:
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

    domain_set = set(domains)
    nergal_active = bool(domain_set & _NERGAL_DOMAINS)
    selected = [
        g for g in selected
        if not (g == "marduk" and budget_tier != "full")
        and not (g == "nergal" and not nergal_active)
    ]
    return selected
