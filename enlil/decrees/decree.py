from dataclasses import dataclass, field
from typing import Optional
import uuid
import time


@dataclass
class GodVoice:
    god_name: str
    model: str
    content: str
    tokens_used: int
    latency_ms: float
    dissent: Optional[str] = None



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

    def has_dissent(self) -> bool:
        return any(v.dissent for v in self.voices)

    def dissenting_gods(self) -> list[str]:
        return [v.god_name for v in self.voices if v.dissent]
