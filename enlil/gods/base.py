from dataclasses import dataclass, field
from typing import Optional
import time

from ..reliability import AttemptResult


@dataclass
class GodResponse:
    god_name: str
    model: str
    content: str
    tokens_used: int          # SIN CAMBIOS de tipo/semántica — sigue alimentando billing/cuotas (v3/v4 §12)
    latency_ms: float         # SIN CAMBIOS — latencia del intento seleccionado, no la suma de ambos
    dissent: Optional[str] = None   # SIN CAMBIOS — nunca redefinido, ver v4 §12
    # --- campos nuevos, TEST 01B (aditivos, con default) ---
    voice_status: str = "unknown"
    finish_reason: Optional[str] = None
    retry_count: int = 0
    returned_model: Optional[str] = None
    reasoning_tokens: Optional[int] = None
    usage_state: str = "unknown"
    attempts: list[AttemptResult] = field(default_factory=list)


@dataclass
class GodProfile:
    name: str
    model: str
    role: str
    domains: list[str]
    cardinal_rule: str = ""   # Lo que este dios NO debe hacer jamás
    domain_mandate: str = ""  # Lo que este dios SÍ debe hacer, su misión específica
    mandatory_question: str = ""  # Pregunta que debe responder sí o sí
    voice_signature: str = ""    # Cómo habla este dios: tono, formato, estructura
    reputation: dict[str, float] = field(default_factory=dict)
    tier_required: Optional[str] = None

    def get_reputation(self, domain: str) -> float:
        return self.reputation.get(domain, 0.5)

    def update_reputation(self, domain: str, success: bool):
        current = self.get_reputation(domain)
        new_score = current + 0.1 * ((1.0 if success else 0.0) - current)
        self.reputation[domain] = round(new_score, 4)
