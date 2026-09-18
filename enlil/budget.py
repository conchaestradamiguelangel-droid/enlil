from dataclasses import dataclass

# Coste aproximado por 1K tokens en USD (OpenRouter, mayo 2026)
MODEL_COSTS: dict[str, float] = {
    "anthropic/claude-sonnet-4-6":                 0.003,
    "anthropic/claude-sonnet-5":                   0.003,
    "anthropic/claude-opus-4-8":                   0.015,
    "deepseek/deepseek-v4-pro":                    0.0007,
    "deepseek/deepseek-r1":                        0.00055,
    "nvidia/llama-3.1-nemotron-ultra-253b-v1":     0.002,
    "mistralai/mistral-large-2512":                0.002,
    "google/gemini-3.1-pro-preview":               0.003,
    "x-ai/grok-4.3":                               0.003,
    "meta-llama/llama-4-maverick":                 0.0002,
    "anthropic/claude-opus-5":                     0.015,
    "x-ai/grok-4.5":                               0.004,
    "nvidia/nemotron-3-ultra-550b-a55b":           0.00135,
}

TIER_LIMITS: dict[str, int] = {
    "minimal":  2_000,   # 2 dioses
    "standard": 6_000,   # 4 dioses + síntesis
    "full":    16_000,   # 9 dioses + síntesis
}


@dataclass
class BudgetResult:
    tier: str
    max_tokens: int
    estimated_cost_usd: float


def resolve_budget(query: str, explicit_tier: str | None = None) -> BudgetResult:
    if explicit_tier:
        tier = explicit_tier
    elif len(query) > 300:
        tier = "full"
    elif len(query) > 30:
        tier = "standard"
    else:
        tier = "minimal"

    max_tokens = TIER_LIMITS[tier]
    avg_cost = sum(MODEL_COSTS.values()) / len(MODEL_COSTS)
    estimated = (max_tokens / 1000) * avg_cost

    return BudgetResult(tier=tier, max_tokens=max_tokens, estimated_cost_usd=round(estimated, 5))


def estimate_cost(tokens_used: dict[str, int]) -> float:
    total = 0.0
    for model, tokens in tokens_used.items():
        rate = MODEL_COSTS.get(model, 0.003)
        total += (tokens / 1000) * rate
    return round(total, 6)


# CONTENT bound, NO billing bound -- leer esto antes de tocarlo.
#
# `len(text.encode("utf-8"))` acota el numero de tokens que un
# tokenizer BPE a nivel de byte (tiktoken/OpenAI, Anthropic, y la
# mayoria de LLM modernos) puede producir para ESTE texto concreto:
# esos tokenizers incluyen los 256 valores de byte individuales en su
# vocabulario base como ultimo recurso, asi que ninguna secuencia de
# bytes necesita jamas MAS tokens que bytes tiene. Esa parte sigue
# siendo cierta y es una propiedad estructural, no una aproximacion.
#
# Lo que esta funcion NO puede afirmar -- y una version anterior de
# este modulo afirmaba incorrectamente -- es que sea una cota del
# INPUT FACTURABLE TOTAL de una llamada real. El texto que ENLIL
# construye (system+user ya serializados) es solo el CONTENIDO que
# controlamos. Un proveedor real puede facturar ademas, por encima de
# ese contenido:
#   - framing/roles propios de su formato de API (no es "+N tokens
#     fijos": varia por proveedor, version de API y hasta por request);
#   - system prompts internos que el proveedor inyecta y no vemos;
#   - definiciones de tools/funciones si se declaran;
#   - bloques de tool_use/tool_result;
#   - tokens de reasoning/thinking (visibles o no en la respuesta);
#   - mecanismos de prompt caching con su propia contabilidad;
#   - cualquier otro componente especifico del proveedor/modelo.
#
# Ninguno de esos componentes esta acotado aqui. Por eso esta funcion
# NUNCA debe usarse por si sola como base de una decision de gasto --
# ver enlil/input_accounting.py: antes de confiar en cualquier numero
# de tokens de entrada para gastar dinero real, el modelo/proveedor
# concreto debe tener un metodo de contabilizacion VERIFICADO (llamada
# real al endpoint de conteo del proveedor, tokenizer local
# model-aware, o una cota estatica documentada con fuente) -- el
# guardarrail economico (enlil/cost_guard.py) exige ese segundo gate
# ademas del pricing verificado, y hoy esta vacio para todos los
# modelos, asi que produccion sigue bloqueada independientemente de lo
# que esta funcion calcule.
def estimate_content_token_upper_bound(text: str) -> int:
    if not text:
        return 0
    return len(text.encode("utf-8", errors="replace"))


def estimate_content_tokens_from_messages(messages: list) -> int:
    """Suma la cota de CONTENIDO (ver estimate_content_token_upper_bound)
    de cada mensaje de una lista de chat ya construida. Sigue siendo
    solo una cota del contenido serializado que controlamos -- NO
    incluye ningun overhead de framing/tools/reasoning/caching del
    proveedor, porque no hay ninguna cifra fija que pueda garantizarse
    como universal para todos los proveedores (una version anterior de
    este modulo sumaba "+10 tokens/mensaje" presentandolo como un
    margen de seguridad garantizado -- no lo era, era un numero
    inventado sin fuente verificable, exactamente el tipo de cifra que
    la Regla XII de CLAUDE.md prohibe presentar como cierta). Ver
    enlil/input_accounting.py para el gate real que decide si este
    numero puede usarse para una decision de gasto."""
    total = 0
    for msg in messages:
        content = msg.get("content", "") if isinstance(msg, dict) else str(msg)
        total += estimate_content_token_upper_bound(content)
    return total
