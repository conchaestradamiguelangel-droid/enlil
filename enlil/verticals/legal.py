"""
Vertical legal — análisis de contratos, cláusulas y riesgos.
ENLIL analiza documentos legales con el Consejo y genera análisis con recomendaciones.
"""
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class LegalDocument:
    doc_type: str          # contrato, clausula, nda, acuerdo, regulacion, politica
    text: str              # texto del documento a analizar
    jurisdiction: str = "España"   # jurisdicción legal
    parties: list[str] = field(default_factory=list)   # partes involucradas
    context: str = ""      # contexto adicional


@dataclass
class LegalDecreeContext:
    document: LegalDocument

    def to_query(self) -> str:
        parties_str = ", ".join(self.document.parties) if self.document.parties else "partes no especificadas"
        header = (
            f"Análisis legal — Tipo: {self.document.doc_type} | "
            f"Jurisdicción: {self.document.jurisdiction} | "
            f"Partes: {parties_str}"
        )
        return header + chr(10)*2 + self.document.text

    def to_context(self) -> str:
        return (
            "Eres el Consejo de ENLIL analizando un documento legal. "
            "Tu misión: identificar cláusulas problemáticas, evaluar riesgos, "
            "detectar ambigüedades, y proponer mejoras o contramedidas concretas. "
            f"Jurisdicción: {self.document.jurisdiction}. "
            f"{self.document.context}\n\n"
            f"DOCUMENTO COMPLETO:\n{self.document.text}"
        )


# Configuración del panteón para análisis legal
LEGAL_GOD_OVERRIDES = {
    "claude": {
        "system_extra": (
            "Eres el Dios de Contexto y estrategia. Evalúa si el documento es coherente, "
            "si hay contradicciones internas, y si los compromisos son razonables. "
            "Identifica riesgos estratégicos para las partes."
        )
    },
    "enki": {
        "system_extra": (
            "Eres el analista técnico. Examina cláusulas específicas, "
            "detecta ambigüedades técnicas, evalúa viabilidad de los términos "
            "y propón redacciones alternativas más precisas."
        )
    },
    "inanna": {
        "system_extra": (
            "Eres la experta en comunicación. Analiza el tono y lenguaje del documento, "
            "identifica cláusulas desequilibradas o abusivas, "
            "y evalúa si la comunicación entre partes es clara y justa."
        )
    },
}


def build_legal_query(document: LegalDocument) -> tuple[str, str]:
    """Devuelve (query, context) listos para enlil.query()"""
    ctx = LegalDecreeContext(document=document)
    return ctx.to_query(), ctx.to_context()


_VALID_DOC_TYPES = {"contrato", "clausula", "nda", "acuerdo", "regulacion", "politica", "otro"}


def parse_legal_request(payload: dict) -> LegalDocument:
    """Convierte payload de la API en LegalDocument con sanitización."""
    doc_type = str(payload.get("type", "otro"))[:50].lower()
    if doc_type not in _VALID_DOC_TYPES:
        doc_type = "otro"

    text = str(payload.get("text", ""))[:5000]
    if not text.strip():
        raise ValueError("El campo 'text' es obligatorio y no puede estar vacío")

    jurisdiction = str(payload.get("jurisdiction", "España"))[:50]

    parties_raw = payload.get("parties", [])
    if not isinstance(parties_raw, list):
        parties_raw = []
    parties = [str(p)[:100] for p in parties_raw[:10]]

    context = str(payload.get("context", ""))[:500]

    return LegalDocument(
        doc_type=doc_type,
        text=text,
        jurisdiction=jurisdiction,
        parties=parties,
        context=context,
    )
