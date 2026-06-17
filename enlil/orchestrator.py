import asyncio
import logging
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

DEFAULT_DB = os.environ.get("ENLIL_DB", "enlil.db")


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
    ) -> Decree:
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

        # Búsqueda semántica (Qdrant) con fallback a FTS (SQLite)
        if self.qdrant.is_available:
            memory_context = self.qdrant.search(text, limit=3)
        else:
            memory_context = self.memory.search(text, limit=3)
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
        responses: list[GodResponse] = await self.council.convene(god_names, text, context, god_overrides=god_overrides, doc_id=doc_id)
        synthesis = await self.council.synthesize(responses, text, budget_tier=budget.tier)

        voices = [
            GodVoice(
                god_name=r.god_name, model=r.model, content=r.content,
                tokens_used=r.tokens_used, latency_ms=r.latency_ms, dissent=r.dissent,
            )
            for r in responses
        ]
        decree = Decree(
            query=text, domains=domains, gods_convened=god_names,
            voices=voices, synthesis=synthesis,
            total_tokens=sum(r.tokens_used for r in responses),
            budget_tier=budget.tier, parent_decree_id=parent_decree_id,
            predicted_scores=predicted_scores,
        )

        self.store.save(decree, client_id=client_id)

        # Telemetría
        _latency = sum(v.latency_ms for v in decree.voices)
        _domain = decree.domains[0] if decree.domains else "general"
        record_decree(decree.budget_tier, _domain, _latency, decree.total_tokens)
        with span(
            "enlil.query",
            decree_id=decree.id,
            budget_tier=decree.budget_tier,
            domain=_domain,
            gods_count=len(decree.gods_convened),
            total_tokens=decree.total_tokens,
            latency_ms=round(_latency, 1),
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
    ):
        """Async generator -- yields JSON strings for SSE events."""
        import json as _json
        domains = classify_query(text)
        budget = resolve_budget(text, budget_tier)

        predicted_scores: dict[str, float] = {}
        if domains:
            for _name in self.pantheon:
                _avg_w = sum(self.rl.get_policy_weight(_name, d) for d in domains) / len(domains)
                predicted_scores[_name] = round((_avg_w / 2.0) * 10.0, 2)

        god_names = select_gods(domains, self.pantheon, budget.tier)

        if self.qdrant.is_available:
            memory_context = self.qdrant.search(text, limit=3)
        else:
            memory_context = self.memory.search(text, limit=3)
        if memory_context:
            context = context + "\n\nDecretos anteriores relevantes:\n" + memory_context

        if self.corpus:
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
        if context and len(context) > RAG_THRESHOLD and self.rag.is_available:
            doc_id = self.rag.ingest(context)

        yield _json.dumps({"type": "init", "gods": god_names, "domains": domains, "budget_tier": budget.tier})

        responses = []
        async for god_resp in self.council.convene_stream(god_names, text, context, god_overrides=god_overrides, doc_id=doc_id):
            responses.append(god_resp)
            yield _json.dumps({
                "type": "god",
                "god": god_resp.god_name,
                "content": god_resp.content,
                "tokens": god_resp.tokens_used,
                "latency_ms": god_resp.latency_ms,
                "dissent": god_resp.dissent,
                "model": god_resp.model,
            })

        synthesis_parts = []
        async for chunk in self.council.synthesize_stream(responses, text, budget_tier=budget.tier):
            synthesis_parts.append(chunk)
            yield _json.dumps({"type": "synthesis_chunk", "text": chunk})

        synthesis = "".join(synthesis_parts)

        voices = [
            GodVoice(
                god_name=r.god_name, model=r.model, content=r.content,
                tokens_used=r.tokens_used, latency_ms=r.latency_ms, dissent=r.dissent,
            )
            for r in responses
        ]
        decree = Decree(
            query=text, domains=domains, gods_convened=god_names,
            voices=voices, synthesis=synthesis,
            total_tokens=sum(r.tokens_used for r in responses),
            budget_tier=budget.tier, parent_decree_id=parent_decree_id,
            predicted_scores=predicted_scores,
        )
        self.store.save(decree, client_id=client_id)
        _latency = sum(v.latency_ms for v in decree.voices)
        _domain = decree.domains[0] if decree.domains else "general"
        record_decree(decree.budget_tier, _domain, _latency, decree.total_tokens)
        with span("enlil.query", decree_id=decree.id, budget_tier=decree.budget_tier,
                  domain=_domain, gods_count=len(decree.gods_convened),
                  total_tokens=decree.total_tokens, latency_ms=round(_latency, 1)):
            pass
        self.memory.store(decree)
        if self.qdrant.is_available:
            self.qdrant.store(decree)
        self.meta.observe(decree)
        apply_decay(god_names, self.pantheon)
        task = asyncio.create_task(self._evaluate_and_learn(decree))
        task.add_done_callback(_on_eval_done)

        yield _json.dumps({
            "type": "done",
            "decree_id": decree.id,
            "domains": decree.domains,
            "gods_convened": decree.gods_convened,
            "total_tokens": decree.total_tokens,
            "budget_tier": decree.budget_tier,
            "has_dissent": decree.has_dissent(),
            "dissenting_gods": decree.dissenting_gods(),
            "pq_signed": bool(decree.pq_signature),
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
