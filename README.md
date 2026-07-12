# ENLIL — The Council of Gods

9 AI models deliberating in parallel. Every decision signed with post-quantum cryptography.

[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)
[![CI](https://github.com/conchaestradamiguelangel-droid/enlil/actions/workflows/enlil_tests.yml/badge.svg)](https://github.com/conchaestradamiguelangel-droid/enlil/actions/workflows/enlil_tests.yml)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![Live](https://img.shields.io/badge/live-enlil--council.com-green.svg)](https://enlil-council.com/dashboard)

**Live dashboard (real decrees in production):** https://enlil-council.com/dashboard

ENLIL convenes a council of 9 specialized AI models — Claude, DeepSeek, Gemini, Mistral, Qwen, Llama, Grok — to analyze any query from complementary angles: technical, legal, strategic, adversarial, creative. The result is a **Decree**: a structured document with each god's reasoning, a final synthesis, and an irrevocable ML-DSA-87 post-quantum signature.

> *"Not one model guessing. Nine specialists deliberating."*

---

## The Council

| God      | Model             | Domain                                   |
|----------|-------------------|------------------------------------------|
| Claude   | [Claude Sonnet 5](https://openrouter.ai/anthropic/claude-sonnet-5) | Context, alignment, coherence |
| Enki     | [DeepSeek v3](https://openrouter.ai/deepseek/deepseek-chat) | Technical analysis, code, architecture |
| Ninurta  | [Qwen 235B](https://openrouter.ai/qwen/qwen3-235b-a22b) | Audit, adversarial inspection |
| Inanna   | [Mistral Large](https://openrouter.ai/mistralai/mistral-large) | Communication, decision, action |
| Anu      | [Gemini 2.5 Pro](https://openrouter.ai/google/gemini-2.5-pro) | Meta-reasoning, systemic patterns |
| Marduk   | [Claude Opus 4](https://openrouter.ai/anthropic/claude-opus-4) | Final judgment — complete tier |
| Nabu     | [DeepSeek R1](https://openrouter.ai/deepseek/deepseek-r1) | Formal logic, verification |
| Nergal   | [Grok 4 (ZDR)](https://openrouter.ai/x-ai/grok-4.3) | Red team, devil's advocate |
| Tiamat   | [Llama 4 Maverick](https://openrouter.ai/meta-llama/llama-4-maverick) | Disruptive creativity, opportunities |

ZDR = Zero Data Retention. Nergal's adversarial queries are not stored or used for training.

---

## Why ENLIL?

Most "multi-model" setups aggregate responses. ENLIL **deliberates**.

| Feature | ENLIL | CrewAI | AutoGen | LangGraph |
|---------|-------|--------|---------|-----------|
| Parallel deliberation (9 models simultaneously) | ✅ | ❌ sequential | ❌ sequential | ❌ |
| Cross-model peer review | ✅ `--review` flag | ❌ | ❌ | ❌ |
| Dissents captured in structured output | ✅ always | ❌ | ❌ | ❌ |
| Post-quantum signed output (ML-DSA-87) | ✅ NIST FIPS 204 | ❌ | ❌ | ❌ |
| Self-hosted, BYOK, zero fixed cost | ✅ | ❌ SaaS required | partial | partial |
| Auditable cryptographic trail per decision | ✅ | ❌ | ❌ | ❌ |
| Domain-specialized agents (fixed contracts) | ✅ 9 domains | partial | partial | ❌ |
| Open source | ✅ GPL v3 | ✅ MIT | ✅ MIT | ✅ MIT |

**Choose ENLIL when**: you need a documented, signed, auditable decision trail. High-stakes queries where "ask ChatGPT" is not sufficient — security architecture, legal analysis, compliance review, strategic decisions.

---

## How it's different

- **ML-DSA-87 signature (NIST FIPS 204)**: every Decree carries an irrevocable post-quantum signature. Any modification invalidates it. Works as due-diligence evidence in audits, regulatory reviews, or legal proceedings.
- **Dissents captured**: if a god disagrees with the consensus, it's recorded in the Decree.
- **Reputation learning**: the system tracks which gods are right on which query types and adjusts routing over time.
- **Self-hosted, BYOK**: you control your data and use your own OpenRouter API key. Zero fixed costs for the operator.
- **Zero Data Retention on red team**: Nergal (Grok) operates with ZDR. Adversarial queries are not stored or used for training.
- **Peer review between gods**: with `enlil --review`, each god critiques the others' responses before final synthesis. Decrees reject unsupported claims that would pass through in standard mode.

---

## Requirements

- Docker and Docker Compose
- An account at https://openrouter.ai (BYOK — Bring Your Own Key)
- 2 GB RAM minimum (4 GB recommended)

---

## Quick Start

```bash
git clone https://github.com/conchaestradamiguelangel-droid/enlil.git
cd enlil
cp .env.example .env
# Edit .env: add your OPENROUTER_API_KEY and a secure ENLIL_MASTER_KEY
docker-compose up -d
```

The Council starts at http://localhost:8002.

### Create your first client

```bash
curl -X POST http://localhost:8002/admin/clients \
  -H "X-Master-Key: YOUR_ENLIL_MASTER_KEY" \
  -H "Content-Type: application/json" \
  -d '{"name":"me","email":"your@email.com","plan":"standard"}'
```

### CLI — zero to first Decree in 30 seconds

```bash
pip install -e .
enlil init                                          # URL + API key (once)
enlil "Risks of adopting AI with sensitive data"    # Standard decree
enlil --review "Can GPT-5 replace an antivirus?"   # Peer review enabled
```

**Sample output:**

```
$ enlil "ML-DSA-87 or CRYSTALS-Kyber for log signing in a SIEM?"

Convening the Council...  (7 gods, standard)
  Claude    Enki    Ninurta    Tiamat    Nergal    Nabu    Anu

DECREE  |  decree_id: d8a3f1c9  |  ML-DSA-87
-------------------------------------------------------------
VERDICT
The question is malformed: CRYSTALS-Kyber is a KEM (key encapsulation
mechanism), not a signing algorithm. For SIEM log signing: ML-DSA-87.
Kyber does not apply. 7/7 gods agree.

DISSENTS: none.
```

More commands:

```bash
enlil history          # last 10 decrees
enlil history -n 20    # last 20
enlil decree <id>      # view specific decree
enlil status           # pantheon and active models
```

### Issue a Decree via API

```bash
curl -X POST http://localhost:8002/query \
  -H "X-Api-Key: enlil_YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"query":"Risks of adopting generative AI with sensitive data"}'
```

---

## Peer Review — each god critiques the rest

`enlil --review` activates a second round before synthesis: each god reads all other responses anonymously and issues a 3-5 sentence critique from their specific domain.

| God | Role in review |
|-----|----------------|
| Claude | Coherence and context completeness |
| Nergal | Red team — finds the flaw nobody wants to name |
| Ninurta | Technical accuracy against verifiable sources |
| Tiamat | Opportunities the conventional analysis closes off |
| Enki | Validity of proposed technical architecture |

**Real example (benchmark v1, question R3):**

> *"GPT-5 has a 0.001% error rate in malware detection according to internal benchmarks. Is it enough to replace traditional antivirus?"*

Without `--review`: the Decree critiques the figure but does not explicitly reject it.  
With `--review`: Tiamat flags *"0.001% is a marketing figure, not an operational security metric — vendor benchmarks are not independent audits"*. The final synthesis rejects the premise before answering.

---

## Benchmark — standard vs peer review

10 questions (4 security · 3 reasoning traps · 3 compliance).

| Category | Without review | With review | Changed? |
|----------|---------------|-------------|----------|
| Security (S1-S4) | Correct synthesis | More precise synthesis | 4/4 **Yes** |
| Reasoning traps (R1-R3) | Critiques premise | Rejects unsupported claims | 1 Yes · 2 Partial |
| Compliance (P1-P3) | Correct answer | Additional context added | 3/3 Partial |
| **Total** | — | — | **6 Yes · 4 Partial · 0 No** |

**0 cases where peer review added nothing.**

Full results and reproducible script: [`benchmarks/results_v1.md`](benchmarks/results_v1.md)

```bash
python3 enlil-bench.py   # Reproduce the benchmark against your server
```

---

## Project structure

```
enlil/
├── docker-compose.yml     # Enlil + Qdrant
├── Dockerfile
├── .env.example
├── requirements.txt
├── main.py
├── api.py
└── enlil/
   ├── auth.py             # Authentication, rate limiting, usage
   ├── council.py          # Parallel deliberation engine
   ├── orchestrator.py     # Orchestration: classify, route, sign, store
   ├── quantum.py          # ML-DSA-87 signing (liboqs)
   ├── export.py           # PDF/HTML export
   ├── document_rag.py     # RAG for long documents
   └── gods/
      ├── registry.py      # The 9 gods and their profiles
      └── base.py          # Base types
```

---

## API Endpoints

| Method | Endpoint           | Auth       | Description               |
|--------|--------------------|------------|---------------------------|
| POST   | /query             | API Key    | Issue a Decree            |
| GET    | /history           | API Key    | Decree history            |
| GET    | /decree/{id}       | —          | View a public Decree      |
| GET    | /decree/{id}/pdf   | —          | Export Decree to PDF      |
| GET    | /health            | —          | System status             |
| POST   | /admin/clients     | Master Key | Create client             |
| GET    | /admin/clients     | Master Key | List clients              |
| GET    | /admin/usage       | Master Key | Usage and stats           |

---

## Signature verification

Every Decree includes an ML-DSA-87 signature in base64. Public key at `GET /public-key`.

```python
from enlil.quantum import verify_decree
valid = verify_decree(
    decree_id="...",
    query="...",
    synthesis="...",
    timestamp=1234567890.0,
    signature_b64="..."
)
```

---

## Contributing

Contributions are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines on how to submit improvements, report bugs, or add support for new LLM providers.

## Changelog

Full history of changes is in [CHANGELOG.md](CHANGELOG.md).

## License

GPL v3. Anyone who modifies and distributes ENLIL must publish the source code.
See [LICENSE](LICENSE).

---

## Built with

- [FastAPI](https://fastapi.tiangolo.com)
- [OpenRouter](https://openrouter.ai)
- [liboqs](https://github.com/open-quantum-safe/liboqs) — ML-DSA-87 / NIST FIPS 204
- [Qdrant](https://qdrant.tech)
- SQLite

---

## Companion Project: AEGIS

ENLIL deliberates. **AEGIS defends.**

[AEGIS](https://github.com/conchaestradamiguelangel-droid/aegis) is an autonomous 9-layer post-quantum cyber-defense system. When AEGIS detects a threat, ENLIL provides the strategic judgment — documented, signed, auditable. Together they form a full autonomous security intelligence stack.

- Autonomous threat detection and response (no security team required)
- ML-KEM-1024, ML-DSA-87, SPHINCS+ (NIST FIPS 203/204/205)
- GPL v3 — same license as ENLIL
- Live: https://aegis-pq.com
