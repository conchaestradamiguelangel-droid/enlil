import logging
import json
import re


logger = logging.getLogger("enlil.evaluator")

class SynthesisEvaluator:
    """Evalúa síntesis de decretos con Claude como juez. Score 0-10 → alimenta reputación."""

    _PROMPT_TEMPLATE = (
        "Evalúa esta síntesis del Consejo de Dioses de ENLIL.\n\n"
        "Consulta original: {query}\n\n"
        "Síntesis generada: {synthesis}\n\n"
        "Evalúa la calidad de la síntesis en una escala del 0 al 10:\n"
        "- 0-3: Respuesta vaga, incorrecta o sin valor\n"
        "- 4-5: Respuesta aceptable pero incompleta\n"
        "- 6-7: Buena respuesta, útil y concisa\n"
        "- 8-10: Excelente respuesta, precisa, completa y accionable\n\n"
        'Responde EXCLUSIVAMENTE en este formato JSON:\n'
        '{{"score": <número del 0 al 10>, "reasoning": "<una frase corta de justificación>"}}'
    )

    _ERROR_RESULT = {"score": None, "reasoning": "evaluation_failed", "useful": None}

    def __init__(self, council, reputation, pantheon):
        self.council = council
        self.reputation = reputation
        self.pantheon = pantheon

    async def evaluate(self, decree) -> dict:
        """Retorna: {"score": 7, "reasoning": "...", "useful": True}
        Si falla: {"score": None, "reasoning": "evaluation_failed", "useful": None}"""
        try:
            client = self.council._anthropic_client or self.council._client
            model = "claude-sonnet-5" if self.council._anthropic_client else self.council._resolve_model("anthropic/claude-sonnet-5")
            prompt = self._PROMPT_TEMPLATE.format(
                query=decree.query,
                synthesis=decree.synthesis,
            )
            resp = await client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=200,
            )
            raw = resp.choices[0].message.content or ""
            parsed = self._parse_response(raw)
            if parsed is None:
                return dict(self._ERROR_RESULT)
            score = parsed.get("score")
            reasoning = parsed.get("reasoning", "")
            if score is None or not isinstance(score, (int, float)):
                return dict(self._ERROR_RESULT)
            useful = score >= 6
            self.reputation.record_feedback(
                decree.gods_convened, decree.domains, useful, self.pantheon
            )
            return {"score": score, "reasoning": reasoning, "useful": useful}
        except Exception as e:
            logger.warning("SynthesisEvaluator failed: %s", e)
            return dict(self._ERROR_RESULT)

    def _parse_response(self, raw: str) -> dict | None:
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            pass
        match = re.search(r'\{[^}]+\}', raw)
        if match:
            try:
                return json.loads(match.group())
            except (json.JSONDecodeError, ValueError):
                pass
        return None
