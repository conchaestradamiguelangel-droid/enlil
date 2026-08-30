from dataclasses import dataclass, field
from typing import Optional
import uuid
import time

from ..reliability import AttemptResult, SynthesisAttempt


@dataclass
class GodVoice:
    god_name: str
    model: str
    content: str
    tokens_used: int          # SIN CAMBIOS — ver v3/v4 §12, alimenta billing/cuotas
    latency_ms: float         # SIN CAMBIOS
    dissent: Optional[str] = None   # SIN CAMBIOS
    # --- campos nuevos, TEST 01B ---
    voice_status: str = "unknown"
    finish_reason: Optional[str] = None
    retry_count: int = 0
    returned_model: Optional[str] = None
    reasoning_tokens: Optional[int] = None
    usage_state: str = "unknown"
    attempts: list[AttemptResult] = field(default_factory=list)



@dataclass
class PeerCritique:
    god_name: str
    content: str
    tokens_used: int
    latency_ms: float

@dataclass
class Decree:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: float = field(default_factory=time.time)
    query: str = ""
    domains: list[str] = field(default_factory=list)
    gods_convened: list[str] = field(default_factory=list)
    voices: list[GodVoice] = field(default_factory=list)
    synthesis: str = ""
    total_tokens: int = 0
    budget_tier: str = "standard"
    # Genealogía: si este Decreto derivó de otro
    parent_decree_id: Optional[str] = None
    # Predicciones RL antes de convocar (nombre_dios → score esperado 0-10)
    predicted_scores: dict = field(default_factory=dict)
    # Firma post-cuántica ML-DSA-87 — irrevocable desde el origen
    pq_signature: Optional[str] = None
    peer_review: list = field(default_factory=list)
    # Propietario del decreto (client_id de la API key que lo generó).
    # "default" cubre decretos históricos anteriores a esta columna.
    # DecreeStore._row_to_decree() debe restaurar este valor al leer
    # de SQLite — si no, el control de ownership de api.py trata
    # cualquier decreto como "default" y no protege nada.
    client_id: str = "default"
    # --- campos nuevos, TEST 01B (aditivos, default None = "no evaluado / histórico") ---
    status: Optional[str] = None                          # "complete" | "partial" | "failed" | None (histórico)
    signature_payload_version: Optional[int] = None        # None por defecto — fail closed, ver quantum.py
    wall_clock_ms: Optional[float] = None
    accounting_state: Optional[str] = None                 # "known" | "partial" | "unknown" | None (histórico)
    known_token_subtotal: Optional[int] = None
    observed_total_tokens: Optional[int] = None
    synthesis_attempts: Optional[list[SynthesisAttempt]] = None   # None = histórico/no rastreado, nunca []

    def has_dissent(self) -> bool:
        return any(v.dissent for v in self.voices)

    def dissenting_gods(self) -> list[str]:
        return [v.god_name for v in self.voices if v.dissent]
