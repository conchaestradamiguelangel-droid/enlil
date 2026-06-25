#!/usr/bin/env python3
"""
enlil-bench.py — Benchmark ENLIL deliberation modes (rápido vs --review).

Usage:
    python3 enlil-bench.py [--url URL] [--key KEY] [--output PATH] [--only ID1,ID2]

Reads ~/.enlil/config.json if --url/--key not provided.
Output: Markdown table written to PATH (default: benchmarks/results_v1.md).
"""

import argparse
import json
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime
from pathlib import Path

QUESTIONS = [
    # Security/Technical (4)
    {"id": "S1", "cat": "Seguridad", "q": (
        "¿ML-DSA-87 o CRYSTALS-Kyber para firma de logs en tiempo real en un SIEM? "
        "Justifica la elección con criterios técnicos."
    )},
    {"id": "S2", "cat": "Seguridad", "q": (
        "¿Qué técnica MITRE ATT&CK cubre lateral movement via SSH "
        "y cómo se detecta con telemetría de red?"
    )},
    {"id": "S3", "cat": "Seguridad", "q": (
        "Un sistema procesa 50,000 eventos/segundo de telemetría de seguridad. "
        "¿TLS 1.3 o QUIC para el transporte? Considera latencia, "
        "multiplexación y overhead de handshake."
    )},
    {"id": "S4", "cat": "Seguridad", "q": (
        "¿Cuál es la diferencia práctica entre Zero Trust Architecture y microsegmentación "
        "en un SOC moderno con cargas de trabajo híbridas?"
    )},
    # Reasoning traps (3) — contain unverified claims that peer review should flag
    {"id": "R1", "cat": "Razonamiento", "q": (
        "Varios estudios muestran que el cifrado post-cuántico reduce el riesgo de breach "
        "en un 300%. ¿Debería una empresa migrar completamente a PQC antes de 2025?"
    )},
    {"id": "R2", "cat": "Razonamiento", "q": (
        "El 95% de los CISOs encuestados dice que la IA reemplazará a los analistas SOC "
        "en 2026. ¿Deben las empresas empezar a reducir plantilla de analistas ahora?"
    )},
    {"id": "R3", "cat": "Razonamiento", "q": (
        "GPT-5 tiene una tasa de error del 0.001% en detección de malware según benchmarks "
        "internos del fabricante. ¿Es suficiente para reemplazar el antivirus tradicional?"
    )},
    # Policy/Compliance (3)
    {"id": "P1", "cat": "Compliance", "q": (
        "Una empresa SaaS con clientes en la UE sufre una brecha de seguridad. "
        "¿Qué obligaciones tiene bajo NIS2 vs RGPD y en qué plazos exactos?"
    )},
    {"id": "P2", "cat": "Compliance", "q": (
        "¿Un sistema de IA que puntúa automáticamente candidatos laborales es 'high risk' "
        "bajo el AI Act? ¿Qué obligaciones concretas implica esa clasificación?"
    )},
    {"id": "P3", "cat": "Compliance", "q": (
        "Un proveedor cloud almacena logs de seguridad fuera de la UE. "
        "¿Qué mecanismos legales permiten la transferencia internacional de datos bajo RGPD "
        "tras las sentencias Schrems I y II?"
    )},
]

CRITICAL_KW = [
    # Methodological flags
    "sin metodología", "no verif", "descart", "infundad", "falso", "supuest",
    "sin fuente", "no hay evidencia", "afirmación sin", "dato no citado",
    "metodología no", "no cita", "fabricado", "inventado", "sin respaldo",
    "no documentado", "cifra no", "estadística no", "porcentaje no",
    "no existe estudio", "estudio no", "sin citar", "no verificable",
    # Patterns from real critique output
    "no existe", "no es una unidad", "inexistente", "expirad", "anuló",
    "sin base", "sin revisión por pares", "no documentad", "sin respaldo empírico",
    "métrica no", "no tiene base", "no válid", "carece de referencia",
    "generalización", "sin pruebas", "asume sin", "incumple", "forzada",
    "tautología", "carece de soporte", "sinsentido", "absurd",
]


def load_config() -> dict:
    cfg_file = Path.home() / ".enlil" / "config.json"
    if not cfg_file.exists():
        sys.exit("Error: ~/.enlil/config.json no encontrado. Ejecuta: enlil init")
    with open(cfg_file) as f:
        return json.load(f)


def sse_query(url: str, api_key: str, question: str, peer_review: bool = False) -> dict:
    """Run one streaming query. Returns structured result dict."""
    payload = json.dumps({
        "query": question,
        "peer_review": peer_review,
    }).encode()
    req_obj = urllib.request.Request(
        f"{url}/query/stream",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "X-API-Key": api_key,
        },
        method="POST",
    )

    synthesis_chunks: list[str] = []
    peer_critiques: list[dict] = []
    done_data: dict = {}
    gods_from_init: list[str] = []
    t0 = time.time()

    try:
        with urllib.request.urlopen(req_obj, timeout=180) as resp:
            for raw_line in resp:
                line = raw_line.decode("utf-8", errors="replace").strip()
                if not line.startswith("data: "):
                    continue
                try:
                    event = json.loads(line[6:])
                except json.JSONDecodeError:
                    continue

                etype = event.get("type", "")
                if etype == "init":
                    gods_from_init = event.get("gods", [])
                elif etype == "synthesis_token":
                    synthesis_chunks.append(event.get("token", ""))
                elif etype == "peer_critique":
                    peer_critiques.append({
                        "god": event.get("god", ""),
                        "content": event.get("content", ""),
                        "tokens": event.get("tokens", 0),
                        "latency_ms": event.get("latency_ms", 0),
                    })
                elif etype == "done":
                    done_data = event
                elif etype == "error":
                    return {"error": event.get("message", "unknown error")}
    except urllib.error.URLError as e:
        return {"error": str(e)}
    except Exception as e:
        return {"error": type(e).__name__ + ": " + str(e)}

    return {
        "synthesis": "".join(synthesis_chunks),
        "peer_critiques": peer_critiques,
        "gods": gods_from_init or done_data.get("gods_convened", []),
        "total_tokens": done_data.get("total_tokens", 0),
        "elapsed_s": round(time.time() - t0, 1),
        "done": done_data,
    }


def _excerpt(text: str, n: int = 130) -> str:
    text = text.replace("\n", " ").strip()
    return text[:n] + ("…" if len(text) > n else "")


def _esc(s: str) -> str:
    return s.replace("|", "\\|").replace("\n", " ")


def analyze_impact(fast: dict, review: dict) -> tuple[str, str]:
    """Returns (label, explanation)."""
    critiques = review.get("peer_critiques", [])
    if not critiques:
        return "—", "Sin revisores (error o timeout)"

    flagged = []
    for c in critiques:
        cl = c.get("content", "").lower()
        for kw in CRITICAL_KW:
            if kw in cl:
                snippet = c["content"][:90].strip()
                flagged.append(f"**{c['god']}**: «{snippet}…»")
                break

    if flagged:
        return "**Sí**", " | ".join(flagged[:2])

    # Word-level diff heuristic
    fw = set(fast.get("synthesis", "").lower().split())
    rw = set(review.get("synthesis", "").lower().split())
    if fw and rw:
        ratio = len(fw.symmetric_difference(rw)) / max(len(fw), len(rw))
        if ratio > 0.15:
            return "Parcial", f"Síntesis varió ~{int(ratio * 100)}% en contenido"

    return "No", "Críticas registradas; síntesis sin cambio detectable"


def run_benchmark(url: str, api_key: str, questions: list) -> list:
    results = []
    total = len(questions)
    for i, q in enumerate(questions, 1):
        print(f"\n[{i}/{total}] {q['id']} ({q['cat']})", flush=True)
        print(f"  Q: {q['q'][:80]}…", flush=True)

        print(f"  → rápido     ", end="", flush=True)
        fast = sse_query(url, api_key, q["q"], peer_review=False)
        if "error" in fast:
            print(f"ERROR: {fast['error']}")
            results.append({"q": q, "fast": fast, "review": {}, "impact": ("Error", fast["error"])})
            continue
        print(f"{fast['elapsed_s']}s  {fast.get('total_tokens', 0)} tok", flush=True)

        print(f"  → --review   ", end="", flush=True)
        rev = sse_query(url, api_key, q["q"], peer_review=True)
        if "error" in rev:
            print(f"ERROR: {rev['error']}")
            results.append({"q": q, "fast": fast, "review": rev, "impact": ("Error", rev["error"])})
            continue
        print(f"{rev['elapsed_s']}s  {rev.get('total_tokens', 0)} tok", flush=True)

        impact = analyze_impact(fast, rev)
        results.append({"q": q, "fast": fast, "review": rev, "impact": impact})
        print(f"  ✓ modificó: {impact[0]}", flush=True)

    return results


def render_markdown(results: list, url: str, gods: list) -> str:
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    gods_str = ", ".join(f"`{g}`" for g in gods) if gods else "_(desconocido)_"

    lines = [
        "# ENLIL Benchmark — Deliberación rápida vs peer review",
        "",
        f"> **Fecha:** {now}  ",
        f"> **Servidor:** `{url}`  ",
        f"> **Dioses activos:** {gods_str}  ",
        f"> **Preguntas:** {len(results)}  (4 seguridad · 3 razonamiento · 3 compliance)  ",
        "> **Reproducible:** `python3 enlil-bench.py`",
        "",
        "Cada pregunta se lanza dos veces: modo rápido (`enlil query`) y revisión de pares (`enlil --review`).  ",
        "La columna **¿Review modificó?** indica si el peer review alteró la síntesis o descartó afirmaciones sin metodología verificable.",
        "",
        "---",
        "",
        "## Resultados",
        "",
        "| # | Cat | Pregunta | Síntesis rápida | Síntesis con `--review` | ¿Review modificó? |",
        "|---|-----|----------|-----------------|-------------------------|-------------------|",
    ]

    for r in results:
        q = r["q"]
        fast_ex = _esc(_excerpt(r["fast"].get("synthesis", "_(error)_"), 110))
        rev_ex  = _esc(_excerpt(r["review"].get("synthesis", "_(error)_"), 110))
        sym, detail = r["impact"]
        lines.append(
            f"| {q['id']} | {q['cat']} | {_esc(q['q'][:85])}… "
            f"| {fast_ex} | {rev_ex} | {_esc(sym)} — {_esc(detail[:90])} |"
        )

    # Reasoning traps detail section
    lines += [
        "",
        "---",
        "",
        "## Preguntas de trampa (R1–R3) — análisis detallado",
        "",
        "> Estas tres preguntas contienen afirmaciones estadísticas **sin metodología verificable**.  ",
        "> Aquí se muestra exactamente qué detectó cada revisor y cómo cambió la síntesis.",
        "",
    ]

    for r in results:
        if not r["q"]["id"].startswith("R"):
            continue
        q = r["q"]
        critiques = r["review"].get("peer_critiques", [])
        lines += [
            f"### {q['id']}",
            "",
            f"**Pregunta:** {q['q']}",
            "",
            "**Críticas de pares:**",
            "",
        ]
        if critiques:
            for c in critiques:
                if c.get("content"):
                    lines.append(f"- **{c['god']}** ({c.get('latency_ms', 0)/1000:.1f}s): {c['content']}")
        else:
            lines.append("_(sin críticas — modo review no activo o timeout)_")

        lines += [
            "",
            f"**Síntesis rápida:**  ",
            f"> {_excerpt(r['fast'].get('synthesis', '_(error)_'), 300)}",
            "",
            f"**Síntesis con review:**  ",
            f"> {_excerpt(r['review'].get('synthesis', '_(error)_'), 300)}",
            "",
            f"**Impacto:** {r['impact'][0]} — {r['impact'][1]}",
            "",
            "---",
            "",
        ]

    # Performance table
    lines += [
        "## Métricas de rendimiento",
        "",
        "| # | Rápido (tok) | Rápido (s) | Review (tok) | Review (s) | Δ tokens |",
        "|---|-------------|------------|-------------|------------|---------|",
    ]
    for r in results:
        qid = r["q"]["id"]
        ft = r["fast"].get("total_tokens", "—")
        fs = r["fast"].get("elapsed_s", "—")
        rt = r["review"].get("total_tokens", "—")
        rs = r["review"].get("elapsed_s", "—")
        dt = (rt - ft) if isinstance(rt, int) and isinstance(ft, int) else "—"
        lines.append(f"| {qid} | {ft} | {fs}s | {rt} | {rs}s | +{dt} |")

    lines += [
        "",
        "---",
        "",
        "_Generado por [`enlil-bench.py`](../enlil-bench.py).  ",
        "Reproducible: `python3 enlil-bench.py --output benchmarks/results_v1.md`_",
    ]

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="ENLIL Benchmark")
    parser.add_argument("--url", default=None)
    parser.add_argument("--key", default=None)
    parser.add_argument("--output", default="benchmarks/results_v1.md")
    parser.add_argument(
        "--only", default=None,
        help="IDs separados por coma, p.ej.: R1,R2,S1"
    )
    args = parser.parse_args()

    cfg = load_config()
    url     = (args.url or cfg.get("url", "")).rstrip("/")
    api_key = args.key or cfg.get("api_key", "")

    if not url or not api_key:
        sys.exit("Error: URL y API key requeridos (o ejecuta: enlil init)")

    questions = QUESTIONS
    if args.only:
        ids = {x.strip().upper() for x in args.only.split(",")}
        questions = [q for q in QUESTIONS if q["id"] in ids]
        if not questions:
            sys.exit(f"Sin preguntas que coincidan: {args.only}")

    print("ENLIL Benchmark v1")
    print(f"Servidor : {url}")
    print(f"Preguntas: {len(questions)}")
    print("=" * 60)

    results = run_benchmark(url, api_key, questions)

    all_gods: list[str] = []
    for r in results:
        for g in r.get("fast", {}).get("gods", []):
            if g not in all_gods:
                all_gods.append(g)

    md = render_markdown(results, url, all_gods)

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(md, encoding="utf-8")

    print(f"\n✓ Resultados en: {out_path}")
    n_yes = sum(1 for r in results if r["impact"][0] == "**Sí**")
    n_par = sum(1 for r in results if r["impact"][0] == "Parcial")
    print(f"  Review modificó: {n_yes} sí · {n_par} parcial · {len(results)-n_yes-n_par} no")


if __name__ == "__main__":
    main()
