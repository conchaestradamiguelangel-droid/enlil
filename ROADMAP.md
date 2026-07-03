# ENLIL Roadmap

This roadmap reflects the current direction of ENLIL. Priorities are set by production feedback and contributor interest. Open an issue to propose changes or pick up a task.

---

## v1.1 — Security Hardening (Q3 2026)

Planned issues — all open for contributors:

- [ ] BYOK key audit — ensure API key never appears in logs or error paths ([#11](../../issues/11))
- [ ] Prompt injection defense — god agents must reject injected instructions ([#12](../../issues/12))
- [ ] SSE stream sanitization — sanitize god responses before emitting as SSE events ([#13](../../issues/13))
- [ ] Rate limiting on /council endpoint to protect user OpenRouter quotas ([#14](../../issues/14))

---

## v1.2 — Developer Experience (Q3 2026)

- [ ] Integration tests for `POST /council` with mocked OpenRouter ([#7](../../issues/7))
- [ ] `--timeout` flag for per-god response timeout ([#8](../../issues/8))
- [ ] Webhook support for async Decree delivery
- [ ] Auto-generated OpenAPI documentation page

---

## v1.3 — Intelligence Layer (Q4 2026)

- [ ] Benchmark v2 with updated model versions
- [ ] God reputation dashboard (which gods are right, on which query types)
- [ ] Dynamic god selection based on detected query domain
- [ ] Decree export to Markdown and JSON

---

## v2.0 — Scale (2027)

- [ ] AEGIS integration: ENLIL as strategic council for threat incidents
- [ ] Multi-tenant SaaS mode
- [ ] Decree semantic search across history
- [ ] Streaming Decree output (token by token per god)

---

## Architectural constraints (non-negotiable)

- Self-hosted, BYOK — no mandatory cloud dependency
- Post-quantum signing chain (ML-DSA-87) must remain intact on every Decree
- GPL v3 — derivative works must remain open source
- No features that reduce auditability of the deliberation process
