# Why We Run 9 LLMs in Parallel Instead of One (And Sign Every Output with Post-Quantum Crypto)

*The architecture behind ENLIL: deliberation over aggregation, and why tamper-proof AI outputs matter.*

---

Most "multi-agent" AI tools run models sequentially — one model reviews another's output, which reviews another's. It's a pipeline. ENLIL does something different: it runs up to 9 models *simultaneously*, in complete isolation from each other, then synthesizes their independent responses into a single signed output called a Decree.

This post covers why we built it this way, what the architecture actually looks like, and why we sign every Decree with ML-DSA-87 post-quantum signatures.

---

## The problem with asking one model

A single LLM is a brilliant generalist with consistent blind spots. Ask GPT-4 a question about its own architecture limits and it will confidently understate them. Ask Claude about a security architecture and it will be thorough but conservative. Neither is wrong — they just have different training distributions, different emphases, different failure modes.

When the decision is low-stakes, this doesn't matter. When you're reviewing a security architecture, evaluating a legal strategy, or making a hiring decision based on AI analysis — you want to know where models *disagree*. That's the signal. Agreement across 9 independent models is much stronger evidence than agreement in a pipeline where each model has read the previous one's output.

ENLIL is built around this idea: deliberation is better than aggregation.

---

## The architecture

ENLIL maintains a council of 9 specialized models ("gods") — each assigned a specific domain:

| Model | Domain |
|-------|--------|
| Claude Sonnet 5 | Context, alignment, coherence |
| DeepSeek v3 | Technical analysis, code, architecture |
| Qwen 235B | Adversarial audit, inspection |
| Mistral Large | Communication, decision, action |
| Gemini 2.5 Pro | Meta-reasoning, systemic patterns |
| Claude Opus 4 | Final verdict (full council mode) |
| DeepSeek R1 | Formal logic, verification |
| Grok 4 | Red team, devil's advocate |
| Llama 4 Maverick | Disruptive creativity, opportunities |

When you submit a query, all 9 models receive it simultaneously via async parallel execution. They reason independently — no model sees another's response. Then a synthesis step merges their outputs into a structured Decree with:

- Individual reasoning from each model
- Explicit dissents (if a model disagrees, it's recorded — not hidden)
- A final synthesis
- A post-quantum signature

```python
# The core deliberation loop (simplified)
async def convene_council(query: str, gods: list[God]) -> list[GodResponse]:
    tasks = [god.deliberate(query) for god in gods]
    return await asyncio.gather(*tasks)  # True parallel execution

# Each god gets the query cold — no cross-contamination
async def deliberate(self, query: str) -> GodResponse:
    prompt = self.build_prompt(query)  # Uses only this god's domain context
    response = await self.client.chat(prompt)
    return GodResponse(god=self.name, reasoning=response, domain=self.domain)
```

The critical design constraint: models don't communicate during deliberation. No model reads another's output until the synthesis step. This eliminates the "anchoring" problem where early responses bias later ones.

---

## The peer review mode

With `enlil --review`, you get a second round before synthesis. After the initial deliberation, each model reads all other responses *anonymously* and emits a 3–5 sentence critique from its domain.

The effect is significant. Here's a real example from our benchmark:

**Query:** *"According to internal testing, GPT-5 has a 0.001% error rate on malware detection. Is this sufficient to replace traditional antivirus?"*

- **Without review:** The Decree critiques the figure but doesn't explicitly reject it
- **With review:** Grok (red team) flags that "0.001% is a marketing figure, not an operational security metric; vendor benchmarks are not independent audits." The final synthesis rejects the premise before answering.

The benchmark results across 10 questions (4 security, 3 reasoning traps, 3 compliance):

| Category | Without review | With review | Changed? |
|----------|---------------|-------------|----------|
| Security (S1-S4) | Correct synthesis | More precise | 4/4 Yes |
| Reasoning traps (R1-R3) | Critiques premise | Rejects unsupported claims | 1 Yes · 2 Partial |
| Compliance (P1-P3) | Correct | Additional context | 3/3 Partial |

0 cases where peer review added nothing.

---

## Why post-quantum signatures on AI outputs?

This is the part that gets the most questions.

An LLM output is text. Text can be modified. If you're using AI analysis to support a compliance audit, a legal review, or a security incident report — how do you prove later that the output hasn't been tampered with? How do you prove it came from the system you claim?

Classical HMAC requires a shared secret. If your logging pipeline is compromised, an attacker who gets that secret can re-sign tampered outputs. Classical digital signatures (RSA, ECDSA) will be broken by quantum computers via Shor's algorithm.

ENLIL signs every Decree with **ML-DSA-87** (NIST FIPS 204, finalized August 2024). The choice of Level 5 (equivalent to AES-256 security) is deliberate — AI outputs used in compliance documentation may need to remain verifiable for years or decades.

```python
from liboqs import Signature

class DecreeSigner:
    def __init__(self):
        self.signer = Signature("ML-DSA-87")
        self.private_key, self.public_key = self.signer.generate_keypair()
    
    def sign_decree(self, decree: Decree) -> str:
        # Canonical serialization: deterministic JSON, excludes signature field
        payload = decree.to_canonical_json().encode()
        signature = self.signer.sign(payload, self.private_key)
        return base64.b64encode(signature).decode()
    
    def verify(self, decree: Decree, signature_b64: str) -> bool:
        payload = decree.to_canonical_json().encode()
        sig = base64.b64decode(signature_b64)
        return self.signer.verify(payload, sig, self.public_key)
```

Verification doesn't require the private key — ship the public key to your auditors, your SIEM, your legal team. Any unmodified Decree verifies cleanly. Any tampered Decree fails.

ML-DSA-87 signatures are 4627 bytes. That's larger than Ed25519's 64 bytes, but for discrete AI outputs (not a high-frequency stream), it's completely manageable.

---

## What this looks like in practice

```bash
$ enlil --review "Evaluate this security architecture: [architecture description]"

Convening the Council... (9 gods, peer review)
  Claude  Enki  Ninurta  Tiamat  Nergal  Nabu  Anu  Inanna  Marduk

Running peer review round...

DECREE  |  decree_id: a7c2e4f1  |  ML-DSA-87
─────────────────────────────────────────────────────────────────
VERDICT
The architecture has three significant weaknesses: [synthesis of 9 analyses]

DISSENTS:
  Tiamat: The proposed mitigation for weakness #2 creates a new attack surface
  that the synthesis underweights. [full dissent reasoning]

SIGNATURE (ML-DSA-87):
  AAAAB3Nz... [4627-byte base64 signature]
  Verify with: GET /public-key
```

The dissent is recorded in the output, not collapsed into the consensus. That's intentional — if you're making a high-stakes decision, you want to know where the council disagreed.

---

## The EU AI Act angle

We didn't build ENLIL as a compliance tool. But a signed, structured, auditable Decree happens to satisfy several requirements that the EU AI Act imposes on high-risk AI systems:

- **Art. 12 (Logging/accountability):** Each Decree is an immutable timestamped record of the query, each model's reasoning, and the final synthesis
- **Art. 14 (Human oversight):** Dissents and confidence differences are surfaced explicitly, not hidden behind a single averaged response
- **Annex IV (Technical documentation):** The structured output can serve as supporting evidence in a technical file

This isn't a substitute for legal review or ISO 42001 certification. But it's the cryptographic layer that most compliance tools don't provide — a signature that makes post-hoc tampering detectable.

---

## Self-hosted, BYOK, GPL-3.0

ENLIL is fully self-hosted. You bring your own OpenRouter API key — ENLIL never touches your data. There are no fixed costs; you pay only for the model calls you make.

```bash
git clone https://github.com/conchaestradamiguelangel-droid/enlil.git
cd enlil
cp .env.example .env
# Add your OPENROUTER_API_KEY and ENLIL_MASTER_KEY
docker-compose up -d
```

The council starts at `http://localhost:8002`. The live instance runs at [enlil-council.com/dashboard](https://enlil-council.com/dashboard).

GPL-3.0: anyone who modifies and distributes ENLIL must publish their changes.

---

## Why not just use CrewAI or AutoGen?

The key difference is the isolation constraint. Most multi-agent frameworks are *sequential* — Agent A produces output, Agent B receives it and refines it. The agents communicate. ENLIL's deliberation phase prohibits this.

Sequential agents don't give you independent signals. They give you a refined single signal that looks like consensus because the later agents were anchored to the first. ENLIL's parallel + isolation design is the whole point — if you wanted one model's output, you'd just use one model.

The post-quantum signing is also unique in this space. We haven't found another multi-agent framework that signs its outputs.

---

If you're building anything where AI decisions need to be documented, auditable, or legally defensible — ENLIL's architecture might be worth a look.

Source: [github.com/conchaestradamiguelangel-droid/enlil](https://github.com/conchaestradamiguelangel-droid/enlil)  
Live demo: [enlil-council.com/dashboard](https://enlil-council.com/dashboard)

Happy to answer questions about the deliberation architecture, the ML-DSA-87 implementation, or the compliance angle.
