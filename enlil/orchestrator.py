import asyncio
import logging
import time
from enlil.telemetry import span, record_decree, record_batch
import sqlite3
import os

_logger = logging.getLogger("enlil.orchestrator")


def _on_eval_done(task: asyncio.Task) -> None:
    if not task.cancelled() and (exc := task.exception()):
        _logger.error("_evaluate_and_learn failed: %s", exc, exc_info=exc)
from .gods.base import GodProfile, GodResponse
from .gods.registry import build_default_pantheon
from .council import Council
from .router import classify_query, select_gods
from .budget import resolve_budget
from .decrees.decree import Decree, GodVoice
from .decrees.store import DecreeStore
from .reputation import ReputationStore
from .memory import MemoryStore
from .memory_qdrant import QdrantMemoryStore
from .document_rag import DocumentRAGStore, RAG_THRESHOLD
from .meta_observer import MetaObserver
from .evolution import apply_decay, fitness_report
from .rl_controller import RLController
from .verticals.legal import LEGAL_GOD_OVERRIDES
from .verticals.cybersecurity import CYBER_GOD_OVERRIDES
from .gods.registry import GOD_TIMEOUTS
from .reliability import (
    select_operative_attempt, select_operative_synthesis, compute_decree_status,
    aggregate_accounting_state, compute_known_subtotal, compute_observed_total,
    COMPATIBILITY_PROFILE, StreamingBehaviorProfile,
)

DEFAULT_DB = os.environ.get("ENLIL_DB", "enlil.db")


def _total_budget_seconds(god_names: list[str], pantheon: dict) -> float:
    """Presupuesto total ÚNICO para toda la consulta (V4 §2) -- cubre el
    peor caso de deliberación + 1 retry por voz + síntesis con su propio
    retry (240s x2). No es un objetivo de latencia, es un techo de
    seguridad: la política de retry ya evita lanzar un segundo intento
    si no queda margen real (ver Council._consult_god_with_retry)."""
    max_god_timeout = max((GOD_TIMEOUTS.get(n, 45.0) for n in god_names), default=90.0)
    return (2 * max_god_timeout) + 30.0 + (2 * 240.0)


class Orchestrator:
    def __init__(self, db_path: str = DEFAULT_DB, pantheon: dict[str, GodProfile] | None = None):
        # Una sola conexión SQLite compartida — evita database locked bajo carga concurrente
        self._db = sqlite3.connect(db_path, check_same_thread=False)
        self._db.row_factory = sqlite3.Row  # todos los stores heredan Row desde aquí
        self.pantheon = pantheon or build_default_pantheon()
        self.store = DecreeStore(connection=self._db)
        self.reputation = ReputationStore(connection=self._db)
        self.memory = MemoryStore(connection=self._db)
        #  Qdrant: embedded si QDRANT_PATH, servidor si QDRANT_URL.
        qdrant_url = os.environ.get("QDRANT_URL", "")
        qdrant_path = os.environ.get("QDRANT_PATH", "")
        self.qdrant = QdrantMemoryStore(path=qdrant_path, url=qdrant_url)
        from .corpus import CorpusStore
        self.corpus = CorpusStore.from_qdrant_store(self.qdrant)
        self.rag = DocumentRAGStore(self.qdrant)
        self.council = Council(self.pantheon, rag_store=self.rag)
        self.reputation.load_into(self.pantheon)
        self.meta = MetaObserver(self.store)
        from .synthesis_evaluator import SynthesisEvaluator
        self.evaluator = SynthesisEvaluator(self.council, self.reputation, self.pantheon)
        self.rl = RLController(connection=self._db)

    async def query(
        self,
        text: str,
        context: str = "",
        budget_tier: str | None = None,
        parent_decree_id: str | None = None,
        client_id: str = "default",
        system_extra: str = "",
    ) -> Decree:
        t_start = time.monotonic()
        domains = classify_query(text)
        budget = resolve_budget(text, budget_tier)

        # Predictive routing: RL policy weights -> expected score per god (0-10 scale)
        # Weight range [0.1, 2.0]: neutral 1.0 -> 5.0, max 2.0 -> 10.0
        predicted_scores: dict[str, float] = {}
        if domains:
            for _name in self.pantheon:
                _avg_w = sum(self.rl.get_policy_weight(_name, d) for d in domains) / len(domains)
                predicted_scores[_name] = round((_avg_w / 2.0) * 10.0, 2)

        god_names = select_gods(domains, self.pantheon, budget.tier)

        # Búsqueda semántica (Qdrant) con fallback a FTS (SQLite) — aislada
        # por client_id (fix P0 2026-08-29): nunca memoria de otro cliente
        # ni memoria "default"/legacy para un cliente normal.
        if self.qdrant.is_available:
            memory_context = self.qdrant.search(text, limit=3, client_id=client_id)
        else:
            memory_context = self.memory.search(text, limit=3, client_id=client_id)
        if memory_context:
            context = context + "\n\nDecretos anteriores relevantes:\n" + memory_context

        if self.corpus:
            corpus_context = self.corpus.search(text, limit=2)
            if corpus_context:
                context = context + "\n\nSabiduría ancestral del panteón:\n" + corpus_context

        domain_set = set(domains)
        if "legal" in domain_set:
            god_overrides = LEGAL_GOD_OVERRIDES
        elif "security" in domain_set:
            god_overrides = CYBER_GOD_OVERRIDES
        else:
            god_overrides = None
        doc_id = None
        if context and len(context) > RAG_THRESHOLD and self.rag.is_available:
            doc_id = self.rag.ingest(context)

        # Deadline único para toda la consulta (V4 §2) -- deliberación,
        # reintentos de voz y síntesis (con su propio reintento) comparten
        # el mismo presupuesto absoluto, nunca uno propio por función.
        deadline = time.monotonic() + _total_budget_seconds(god_names, self.pantheon)
        # Fix de un bug real (V3 §1.2): /query usaba SIEMPRE max_tokens=2048
        # por voz sin importar el tier, mientras /query/stream ya ajustaba a
        # 3000 para tier "full" -- inconsistencia directamente relevante
        # para la fiabilidad que mide TEST 01B, no una mejora de calidad.
        max_tok_god = 3000 if budget.tier == "full" else 2048
        responses: list[GodResponse] = await self.council.convene(
            god_names, text, context, god_overrides=god_overrides, doc_id=doc_id,
            global_system_extra=system_extra, max_tokens=max_tok_god, deadline=deadline,
        )
        synthesis_content, synthesis_attempts = await self.council.synthesize(
            responses, text, budget_tier=budget.tier, system_extra=system_extra, deadline=deadline,
        )

        voices = [
            GodVoice(
                god_name=r.god_name, model=r.model, content=r.content,
                tokens_used=r.tokens_used, latency_ms=r.latency_ms, dissent=r.dissent,
                voice_status=r.voice_status, finish_reason=r.finish_reason,
                retry_count=r.retry_count, returned_model=r.returned_model,
                reasoning_tokens=r.reasoning_tokens, usage_state=r.usage_state,
                attempts=r.attempts,
            )
            for r in responses
        ]

        voice_states = [r.voice_status for r in responses]
        synthesis_operative = select_operative_synthesis(synthesis_attempts)
        status = compute_decree_status(voice_states, synthesis_operative.state)

        all_components = [a for r in responses for a in r.attempts] + list(synthesis_attempts)
        accounting_state = aggregate_accounting_state([c.usage_state for c in all_components])
        known_subtotal = compute_known_subtotal(all_components)
        observed_total = compute_observed_total(accounting_state, known_subtotal)

        wall_clock_ms = round((time.monotonic() - t_start) * 1000, 1)

        decree = Decree(
            query=text, domains=domains, gods_convened=god_names,
            voices=voices, synthesis=synthesis_content,
            total_tokens=sum(r.tokens_used for r in responses),   # SIN CAMBIOS -- ver v3/v4 §12
            budget_tier=budget.tier, parent_decree_id=parent_decree_id,
            predicted_scores=predicted_scores,
            status=status,
            signature_payload_version=2,   # decreto nuevo -- Orchestrator decide, Store solo exige (V4 §8)
            wall_clock_ms=wall_clock_ms,
            accounting_state=accounting_state,
            known_token_subtotal=known_subtotal,
            observed_total_tokens=observed_total,
            synthesis_attempts=synthesis_attempts,
        )

        self.store.save(decree, client_id=client_id)

        # Telemetría -- wall_clock_ms real, NO la suma de latencias en
        # paralelo (bug real corregido, V6 riesgo declarado en v5/v6).
        _domain = decree.domains[0] if decree.domains else "general"
        record_decree(decree.budget_tier, _domain, wall_clock_ms, decree.total_tokens)
        with span(
            "enlil.query",
            decree_id=decree.id,
            budget_tier=decree.budget_tier,
            domain=_domain,
            gods_count=len(decree.gods_convened),
            total_tokens=decree.total_tokens,
            latency_ms=wall_clock_ms,
            status=decree.status,
        ):
            pass
        self.memory.store(decree)
        if self.qdrant.is_available:
            self.qdrant.store(decree)
        self.meta.observe(decree)
        apply_decay(god_names, self.pantheon)
        task = asyncio.create_task(self._evaluate_and_learn(decree))
        task.add_done_callback(_on_eval_done)
        return decree

    async def _evaluate_and_learn(self, decree) -> None:
        result = await self.evaluator.evaluate(decree)
        if result["score"] is not None:
            actual_score = result["score"]
            self.rl.record_reward(
                god_names=decree.gods_convened,
                domains=decree.domains,
                synthesis_score=actual_score,
            )
            # Prediction error audit: compare predicted vs actual per convened god
            if decree.predicted_scores:
                errors = {
                    g: round(abs(decree.predicted_scores.get(g, 5.0) - actual_score), 3)
                    for g in decree.gods_convened
                }
                self.rl.record_prediction_errors(errors, decree.domains, actual_score)
            self.rl.update_policy(self.pantheon)

    def feedback(self, decree_id: str, useful: bool):
        decree = self.store.get(decree_id)
        if decree:
            self.reputation.record_feedback(
                decree.gods_convened, decree.domains, useful, self.pantheon
            )

    def history(self, limit: int = 20, client_id: str | None = None) -> list[Decree]:
        return self.store.recent(limit, client_id=client_id)

    def decree_count(self) -> int:
        return self.store.count()

    def get_decree(self, decree_id: str) -> Decree | None:
        return self.store.get(decree_id)

    def pantheon_status(self) -> dict:
        return self.reputation.snapshot()

    def meta_patterns(self, limit: int = 200) -> dict:
        return self.meta.patterns(limit)

    def evolution_fitness(self) -> dict:
        return fitness_report(self.pantheon)

    def rl_status(self) -> dict:
        return self.rl.status_report(self.pantheon)

    def rl_update(self) -> dict:
        self.rl.update_policy(self.pantheon)
        return {"ok": True, "message": "Policy update completado"}


    async def query_stream(
        self,
        text: str,
        context: str = "",
        budget_tier: str | None = None,
        parent_decree_id: str | None = None,
        client_id: str = "default",
        voices_count: int | None = None,
        timeout_override: float | None = None,
        peer_review: bool = False,
        profile: StreamingBehaviorProfile = COMPATIBILITY_PROFILE,
    ):
        """Async generator -- yields JSON strings para SSE. Implementación
        CANÓNICA de streaming (V5/V6 §6) -- api.py::run_query_stream() es
        un delegado mínimo sobre este método. `profile` controla EXCLUSIVAMENTE
        los efectos laterales/campos documentados en la matriz de
        ENLIL_TEST01B_AUDITORIA_DISENO_V6.md §5; el contrato de campos base
        (`god`, `synthesis_token`/`token`, `done`) es el mismo que ya sirve
        /query/stream hoy en producción, congelado a propósito durante
        TEST 01B. peer_review/voices_count/timeout_override NO son parte
        del perfil -- son parámetros de la petición, implementados aquí
        completos (antes solo existían en la ruta inline de api.py)."""
        import json as _json
        t_start = time.monotonic()
        domains = classify_query(text)
        _tier = budget_tier
        if voices_count == 2:
            _tier = "minimal"
        elif voices_count == 4:
            _tier = "standard"
        elif voices_count == 9:
            _tier = "full"
        budget = resolve_budget(text, _tier)

        predicted_scores: dict[str, float] = {}
        if profile.compute_predicted_scores and domains:
            for _name in self.pantheon:
                _avg_w = sum(self.rl.get_policy_weight(_name, d) for d in domains) / len(domains)
                predicted_scores[_name] = round((_avg_w / 2.0) * 10.0, 2)

        god_names = select_gods(domains, self.pantheon, budget.tier)

        # Memoria de entrada -- misma en ambos perfiles, verificado (V6 §5, fila 9).
        if self.qdrant.is_available:
            memory_context = self.qdrant.search(text, limit=3, client_id=client_id)
        else:
            memory_context = self.memory.search(text, limit=3, client_id=client_id)
        if memory_context:
            context = context + "\n\nDecretos anteriores relevantes:\n" + memory_context

        if profile.use_corpus and self.corpus:
            corpus_context = self.corpus.search(text, limit=2)
            if corpus_context:
                context = context + "\n\nSabiduria ancestral del panteon:\n" + corpus_context

        domain_set = set(domains)
        if "legal" in domain_set:
            god_overrides = LEGAL_GOD_OVERRIDES
        elif "security" in domain_set:
            god_overrides = CYBER_GOD_OVERRIDES
        else:
            god_overrides = None

        doc_id = None
        if profile.use_rag and context and len(context) > RAG_THRESHOLD and self.rag.is_available:
            doc_id = self.rag.ingest(context)

        if profile.emit_init_event:
            yield _json.dumps({"type": "init", "gods": god_names, "domains": domains, "budget_tier": budget.tier})

        deadline = t_start + _total_budget_seconds(god_names, self.pantheon)
        max_tok_god = 3000 if budget.tier == "full" else 2048

        responses: list[GodResponse] = []
        async for god_resp in self.council.convene_stream(
            god_names, text, context, god_overrides=god_overrides, doc_id=doc_id,
            max_tokens=max_tok_god, timeout_override=timeout_override, deadline=deadline,
        ):
            responses.append(god_resp)
            god_event = {
                "type": "god",
                "god": god_resp.god_name,
                "content": god_resp.content,
                "tokens": god_resp.tokens_used,
                "latency_ms": god_resp.latency_ms,
                "dissent": god_resp.dissent,
            }
            if profile.include_model_in_god_event:
                god_event["model"] = god_resp.model
            yield _json.dumps(god_event)

        peer_critiques = []
        if peer_review and responses:
            yield _json.dumps({
                "type": "peer_review_init",
                "reviewers": [r.god_name for r in responses],
                "total": len(responses),
            })
            async for critique in self.council.peer_review_stream(responses, text, deadline=deadline):
                peer_critiques.append(critique)
                yield _json.dumps({
                    "type": "peer_critique",
                    "god": critique.god_name,
                    "content": critique.content,
                    "tokens": critique.tokens_used,
                    "latency_ms": critique.latency_ms,
                })

        synthesis_attempts = []
        final_synthesis_attempt = None
        async for item in self.council.synthesize_stream(
            responses, text, budget_tier=budget.tier,
            peer_critiques=peer_critiques if peer_critiques else None,
            deadline=deadline,
        ):
            if isinstance(item, str):
                yield _json.dumps({"type": "synthesis_token", "token": item})
            else:
                # último elemento -- SynthesisAttempt terminal estructurado (V5 §6.1).
                final_synthesis_attempt = item
                synthesis_attempts.append(item)

        synthesis = final_synthesis_attempt.content if final_synthesis_attempt else ""

        voices = [
            GodVoice(
                god_name=r.god_name, model=r.model, content=r.content,
                tokens_used=r.tokens_used, latency_ms=r.latency_ms, dissent=r.dissent,
                voice_status=r.voice_status, finish_reason=r.finish_reason,
                retry_count=r.retry_count, returned_model=r.returned_model,
                reasoning_tokens=r.reasoning_tokens, usage_state=r.usage_state,
                attempts=r.attempts,
            )
            for r in responses
        ]

        voice_states = [r.voice_status for r in responses]
        synthesis_state = final_synthesis_attempt.state if final_synthesis_attempt else "unknown"
        status = compute_decree_status(voice_states, synthesis_state)

        all_components = [a for r in responses for a in r.attempts] + list(synthesis_attempts)
        accounting_state = aggregate_accounting_state([c.usage_state for c in all_components])
        known_subtotal = compute_known_subtotal(all_components)
        observed_total = compute_observed_total(accounting_state, known_subtotal)
        wall_clock_ms = round((time.monotonic() - t_start) * 1000, 1)

        decree = Decree(
            query=text, domains=domains, gods_convened=god_names,
            voices=voices, synthesis=synthesis,
            total_tokens=sum(r.tokens_used for r in responses),
            budget_tier=budget.tier,
            # V6 §5 fila 18/19 -- hallazgo real: api.py::run_query_stream()
            # ignora hoy parent_decree_id aunque el cliente lo envíe. Se
            # replica ese comportamiento TAL CUAL en COMPATIBILITY_PROFILE
            # (corregirlo sería un cambio funcional fuera de alcance de
            # TEST 01B, ver "No hacer" -- registrado como bug aparte).
            parent_decree_id=(parent_decree_id if profile.thread_parent_decree_id else None),
            predicted_scores=predicted_scores,
            status=status,
            signature_payload_version=2,
            wall_clock_ms=wall_clock_ms,
            accounting_state=accounting_state,
            known_token_subtotal=known_subtotal,
            observed_total_tokens=observed_total,
            synthesis_attempts=synthesis_attempts,
        )
        self.store.save(decree, client_id=client_id)

        if profile.record_decree_telemetry:
            _domain = decree.domains[0] if decree.domains else "general"
            record_decree(decree.budget_tier, _domain, wall_clock_ms, decree.total_tokens)
            with span("enlil.query", decree_id=decree.id, budget_tier=decree.budget_tier,
                      domain=_domain, gods_count=len(decree.gods_convened),
                      total_tokens=decree.total_tokens, latency_ms=wall_clock_ms,
                      status=decree.status):
                pass
        if profile.write_sqlite_memory:
            self.memory.store(decree)
        if self.qdrant.is_available:
            self.qdrant.store(decree)
        if profile.do_meta_observe:
            self.meta.observe(decree)
        if profile.do_reputation_decay:
            apply_decay(god_names, self.pantheon)
        if profile.do_rl_learning:
            task = asyncio.create_task(self._evaluate_and_learn(decree))
            task.add_done_callback(_on_eval_done)

        yield _json.dumps({
            "type": "done",
            "decree_id": decree.id,
            "pq_signed": bool(decree.pq_signature),
            "total_tokens": decree.total_tokens,
            "gods_convened": decree.gods_convened,
            "peer_review": [
                {"god": c.god_name, "content": c.content, "tokens": c.tokens_used}
                for c in peer_critiques
            ],
        })

    def system_mode(self) -> dict:
        """Estado del sistema: modo activo, modelos, Qdrant."""
        gods_models = {
            name: god.model
            for name, god in self.pantheon.items()
        }
        return {
            "council_mode":   self.council.mode,
            "qdrant_active":  self.qdrant.is_available,
            "qdrant_url":     os.environ.get("QDRANT_URL", "http://localhost:6333"),
            "memory_backend": "qdrant+fts" if self.qdrant.is_available else "fts",
            "gods_models":    gods_models,
            "openrouter_key_set": bool(os.environ.get("OPENROUTER_API_KEY")),
        }
