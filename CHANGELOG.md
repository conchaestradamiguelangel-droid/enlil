# Changelog

All notable changes to ENLIL are documented here.

---

## [Unreleased]

- README translated to English
- ROADMAP added
- Security issues #11-#14 open for contributors

---

## [1.3.0] — 2026-07-01

### Changed
- Claude god updated from `claude-sonnet-4.6` to `claude-sonnet-5`
- Marduk display name corrected to `claude-opus-4` (was shown incorrectly in API)

### Fixed
- `synthesize()` in council.py now raises properly when budget retries are exhausted (was silently returning None)

---

## [1.2.0] — 2026-06-26

### Added
- CLI: `enlil init`, `enlil "query"`, `enlil --review`, `enlil history`, `enlil decree <id>`, `enlil status` (commit `b496718`)
- Peer review mode (`--review`): each god critiques other gods' responses before final synthesis (commit `f276cd0`)
- Benchmark v1: 10 questions, 2 modes — results: 6 Yes / 4 Partial / 0 No (commit `1ed1590`)
- AbuseIPDB enrichment integration

---

## [1.1.0] — 2026-06-15

### Added
- 9 individual god files under `enlil/gods/` (claude.py, enki.py, ninurta.py, inanna.py, marduk.py, nabu.py, nergal.py, tiamat.py, anu.py) — commit `66ed564`
- Streaming SSE endpoint: `POST /enlil/query/stream` (commit `6b734ba`)
- Semantic classifier with cosine similarity, 10 domains (commit `f60dcdb`)
- Document RAG for long documents (`document_rag.py`)

### Fixed
- ENLIL clone URL in README (was pointing to wrong org, caused 404)

---

## [1.0.0] — 2026-06-07

### Added
- Public OSS launch under GPL v3
- 9-god deliberation council with ML-DSA-87 signed Decrees (NIST FIPS 204)
- Docker Compose quick-start (ENLIL + Qdrant)
- Live dashboard at https://enlil-council.com/dashboard
- `POST /council` endpoint with parallel model execution
- Reputation tracking per god per query domain
- BYOK: operator uses own OpenRouter API key
- Zero Data Retention on Nergal (Grok) for adversarial queries
