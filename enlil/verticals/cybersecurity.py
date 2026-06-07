"""
Vertical de ciberseguridad — integración con AEGIS.
ENLIL analiza alertas de AEGIS con el Consejo y genera respuestas operativas.
"""
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class AegisAlert:
    alert_type: str
    severity: str
    source_ip: Optional[str] = None
    target: Optional[str] = None
    details: dict = field(default_factory=dict)
    raw_log: str = ""


@dataclass
class SecurityDecreeContext:
    alert: AegisAlert
    system_context: str = ""

    def to_query(self) -> str:
        classification = classify_threat(self.alert.alert_type, self.alert.details)
        indicators = self.alert.details.get("indicators", [])
        if isinstance(indicators, list):
            ind_str = "; ".join(str(i) for i in indicators[:4]) if indicators else "sin indicadores"
        else:
            ind_str = str(indicators)[:200] if indicators else "sin indicadores"
        actor          = classification["actor"]
        techniques     = ", ".join(classification["techniques"])
        score          = classification["threat_score"]
        ip             = self.alert.source_ip or "desconocida"
        target         = self.alert.target or "sistema"
        lines = [
            f"Alerta AEGIS — Tipo: {self.alert.alert_type} | Severidad: {self.alert.severity} | Actor inferido: {actor} | Técnicas MITRE: {techniques} | Threat score: {score} | IP origen: {ip} | Objetivo: {target}",
            f"Indicadores del detector: {ind_str}",
            f"Detalles: {self.alert.details}",
            f"Log: {self.alert.raw_log[:500]}",
        ]
        return chr(10).join(lines)

    def to_context(self) -> str:
        return (
            "Eres el Consejo de ENLIL analizando una alerta del sistema AEGIS "
            "(plataforma de ciberdefensa autónoma post-cuántica de 10 capas). "
            "Tu misión: analizar la amenaza, evaluar severidad real, "
            "proponer contramedidas concretas y decidir si escalar. "
            f"{self.system_context}"
        )


_ACTOR_MAP = {
    "MINE_CONTACT":  "SCANNER",
    "RECON_PATTERN": "RECON_BOT",
    "EXPLORATION":   "PORT_SCANNER",
    "AUTOMATED":     "AUTOMATED_BOT",
    "COORDINATED":   "BOTNET",
}

_MITRE_MAP = {
    "MINE_CONTACT":  ["T1046 - Network Service Discovery", "T1595 - Active Scanning"],
    "RECON_PATTERN": ["T1595 - Active Scanning", "T1592 - Gather Victim Host Info"],
    "EXPLORATION":   ["T1046 - Network Service Discovery", "T1595.002 - Vulnerability Scanning"],
    "AUTOMATED":     ["T1190 - Exploit Public-Facing Application", "T1133 - External Remote Services"],
    "COORDINATED":   ["T1498 - Network DoS", "T1583 - Acquire Infrastructure"],
}

_CONFIDENCE_SCORE = {
    "CONFIRMED": 0.95,
    "HIGH":      0.75,
    "MEDIUM":    0.50,
    "LOW":       0.25,
}


def classify_threat(detection_type: str, details: dict) -> dict:
    actor      = _ACTOR_MAP.get(detection_type, "UNKNOWN")
    techniques = list(_MITRE_MAP.get(detection_type, []))
    confidence = details.get("confidence", "MEDIUM")
    score      = _CONFIDENCE_SCORE.get(confidence, 0.50)

    rps = details.get("requests_per_second")
    if rps:
        try:
            if float(rps) > 50:
                actor = "DDOS_BOT"
                if "T1498 - Network DoS" not in techniques:
                    techniques.insert(0, "T1498 - Network DoS")
                score = max(score, 0.85)
        except (ValueError, TypeError):
            pass

    paths = details.get("paths_touched", [])
    if paths:
        paths_str = " ".join(str(p) for p in paths).lower()
        if any(kw in paths_str for kw in ["admin", "wp-", ".env", "config", "passwd", "shell", "login"]):
            actor = "WEBSHELL_SCANNER"
            if "T1505.003 - Web Shell" not in techniques:
                techniques.insert(0, "T1505.003 - Web Shell")
            score = max(score, 0.80)

    ports = details.get("ports_touched", [])
    if ports:
        try:
            if len(ports) >= 5 and "T1046 - Network Service Discovery" not in techniques:
                techniques.insert(0, "T1046 - Network Service Discovery")
        except TypeError:
            pass

    _raw_ips = details.get("all_ips", [])
    n_ips = len(_raw_ips) if isinstance(_raw_ips, list) else 1
    if n_ips >= 3 and actor != "DDOS_BOT":
        actor = "DISTRIBUTED_" + actor
        score = max(score, 0.80)

    return {
        "actor":        actor,
        "techniques":   techniques[:3],
        "threat_score": round(score, 2),
    }


CYBER_GOD_OVERRIDES = {
    "ninurta": {"system_extra": "Eres el experto en amenazas. Analiza patrones de ataque, vectores de intrusión y evalúa la severidad técnica real."},
    "claude":  {"system_extra": "Eres el Dios de Contexto. Evalúa si esta amenaza encaja con el perfil histórico del sistema, si hay patrones previos y si la respuesta propuesta es coherente con la política de seguridad."},
    "enki":    {"system_extra": "Eres el analista técnico. Propón contramedidas específicas: reglas de firewall, bloqueos de IP, cambios de configuración."},
    "inanna":  {"system_extra": "Eres la Diosa de Comunicación. Redacta el informe ejecutivo de la amenaza: qué ocurrió, impacto potencial, acciones recomendadas. Lenguaje claro para stakeholders no técnicos."},
    "anu":     {"system_extra": "Eres el Dios del Cielo. Evalúa el patrón sistémico: ¿es un ataque aislado o campaña coordinada? ¿Qué implica este tipo de amenaza para la evolución del Consejo?"},
    "marduk":  {"system_extra": "Eres el Dios Supremo. Emite el veredicto final: nivel de respuesta (contención / escalada / bloqueo permanente). Tu decisión es irreversible e inapelable."},
    "nabu":    {"system_extra": "Eres el Dios de la Sabiduría. Clasifica la amenaza por taxonomía MITRE ATT&CK, deduce la cadena de ataque (kill chain) y los TTPs del adversario."},
    "nergal":  {"system_extra": "Eres el Dios de la Destrucción. Actúa como red teamer: ¿qué haría el atacante a continuación? ¿Qué vectores secundarios quedan expuestos tras este primer movimiento?"},
    "tiamat":  {"system_extra": "Eres la Diosa del Caos Primordial. Genera los escenarios de impacto más extremos: qué combinación de vulnerabilidades podría amplificar este ataque. Piensa en cadenas de explotación no evidentes."},
}

_SEVERITY_TO_TIER = {"low": "standard", "medium": "standard", "high": "full", "critical": "full"}


def resolve_aegis_tier(severity: str) -> str:
    return _SEVERITY_TO_TIER.get(severity, "standard")


def build_aegis_query(alert: AegisAlert) -> tuple[str, str]:
    ctx = SecurityDecreeContext(alert=alert)
    return ctx.to_query(), ctx.to_context()


_VALID_SEVERITIES = {"low", "medium", "high", "critical"}


def parse_aegis_webhook(payload: dict) -> AegisAlert:
    alert_type = str(payload.get("type", "unknown"))[:50]
    severity   = str(payload.get("severity", "medium"))[:20]
    if severity not in _VALID_SEVERITIES:
        severity = "medium"

    source_ip = payload.get("source_ip")
    source_ip = str(source_ip)[:45] if source_ip else None

    target = payload.get("target")
    target = str(target)[:100] if target else None

    raw_details = payload.get("details", {})
    if not isinstance(raw_details, dict):
        raw_details = {}
    _LIST_FIELDS = {"all_ips", "indicators", "paths_touched", "ports_touched", "active_ips"}
    details = {}
    for k, v in list(raw_details.items())[:10]:
        k_str = str(k)[:30]
        if isinstance(v, list) and k_str in _LIST_FIELDS:
            details[k_str] = [str(item)[:100] for item in v[:10]]
        else:
            details[k_str] = str(v)[:200]

    raw_log = str(payload.get("log", ""))[:500]

    return AegisAlert(
        alert_type=alert_type,
        severity=severity,
        source_ip=source_ip,
        target=target,
        details=details,
        raw_log=raw_log,
    )
