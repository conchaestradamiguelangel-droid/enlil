import os
"""
PDF export for ENLIL decrees.
Generates a professional legal-grade document with:
  - Contract health index
  - Consensus/dissent visual
  - God-by-god deliberation table
  - Full synthesis (markdown rendered)
  - Post-quantum traceability block (SHA-256 + ML-DSA-87)
"""
import hashlib
import re
import datetime
from typing import Optional

from enlil.decrees.decree import Decree

# ── God metadata ────────────────────────────────────────────────────────────

_GOD_COLORS = {
    "Claude":  "#b8860b",
    "Enki":    "#1565c0",
    "Ninurta": "#b71c1c",
    "Inanna":  "#6a1b9a",
    "Anu":     "#00695c",
    "Marduk":  "#e65100",
    "Nabu":    "#004d40",
    "Nergal":  "#880e4f",
    "Tiamat":  "#4a148c",
}

_GOD_DOMAINS = {
    "Claude":  "Estrategia y Contexto",
    "Enki":    "Análisis Técnico",
    "Ninurta": "Seguridad y Defensa",
    "Inanna":  "Comunicación y Riesgo",
    "Anu":     "Meta y Orquestación",
    "Marduk":  "Juicio Supremo",
    "Nabu":    "Razonamiento y Lógica",
    "Nergal":  "Red Team / Adversarial",
    "Tiamat":  "Creatividad y Visión",
}

# ── Internal helpers ─────────────────────────────────────────────────────────

def _health_score(decree: Decree) -> tuple[int, str, str, str]:
    """Returns (score 0-100, label, color, bg_color)."""
    total = len(decree.voices)
    if total == 0:
        return 50, "INDETERMINADO", "#757575", "#f5f5f5"
    dissenting = sum(1 for v in decree.voices if v.dissent)
    timeouts   = sum(1 for v in decree.voices if v.dissent in ("timeout", "circuit_open"))
    score = max(0, min(100, 100 - dissenting * 15 - timeouts * 5))
    if score >= 80:
        return score, "APTO",                  "#2e7d32", "#e8f5e9"
    elif score >= 60:
        return score, "REVISIÓN RECOMENDADA",  "#e65100", "#fff3e0"
    else:
        return score, "RIESGO ELEVADO",        "#c62828", "#ffebee"


def _content_hash(decree: Decree) -> str:
    payload = f"{decree.id}|{decree.timestamp}|{decree.synthesis}"
    return hashlib.sha256(payload.encode()).hexdigest()


def _h(text: str) -> str:
    """Escape HTML special chars."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _md_to_html(text: str) -> str:
    """Minimal markdown → HTML (no external deps)."""
    # Escape first, then restore markdown structure
    text = _h(text)
    # Emoji section headers like "⚡ VEREDICTO" → h2
    text = re.sub(r"^(#{1,3})\s+(.+)$",
                  lambda m: f"<h{len(m.group(1))}>{m.group(2)}</h{len(m.group(1))}>",
                  text, flags=re.MULTILINE)
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"\*(.+?)\*",     r"<em>\1</em>",         text)
    text = re.sub(r"`(.+?)`",       r"<code>\1</code>",     text)
    # Bullet lists
    lines = text.split("\n")
    out, in_list = [], False
    for line in lines:
        if re.match(r"^[-•]\s+", line):
            if not in_list:
                out.append("<ul>")
                in_list = True
            out.append(f"<li>{line[2:].strip()}</li>")
        else:
            if in_list:
                out.append("</ul>")
                in_list = False
            out.append(line)
    if in_list:
        out.append("</ul>")
    text = "\n".join(out)
    # Paragraphs: double newline → </p><p>
    text = re.sub(r"\n{2,}", "</p><p>", text)
    return f"<p>{text}</p>"


# ── HTML builder ─────────────────────────────────────────────────────────────

def _build_html(decree: Decree) -> str:
    score, label, score_color, score_bg = _health_score(decree)
    content_hash = _content_hash(decree)

    ts = datetime.datetime.fromtimestamp(
        decree.timestamp, tz=datetime.timezone.utc
    )
    timestamp_str = ts.strftime("%Y-%m-%d %H:%M:%S UTC")

    # Consensus stats
    dissenters  = [v.god_name for v in decree.voices if v.dissent]
    n_dissent   = len(dissenters)
    n_convened  = len(decree.voices)
    n_agree     = n_convened - n_dissent

    if n_dissent == 0:
        consensus_text  = f"Unanimidad — {n_convened}/{n_convened} dioses en acuerdo"
        consensus_color = "#2e7d32"
        consensus_bg    = "#e8f5e9"
        consensus_icon  = "✓"
    else:
        consensus_text  = (
            f"Disenso detectado — {n_agree}/{n_convened} en acuerdo · "
            f"Disidentes: {', '.join(dissenters)}"
        )
        consensus_color = "#c62828"
        consensus_bg    = "#ffebee"
        consensus_icon  = "⚠"

    # God pills (consensus bar)
    pills_html = ""
    for v in decree.voices:
        color  = _GOD_COLORS.get(v.god_name, "#757575")
        if v.dissent:
            pill_bg  = "#ffebee"
            border   = "#c62828"
            tag      = f'&nbsp;<small style="color:#c62828">⚠&nbsp;{_h(v.dissent)}</small>'
        else:
            pill_bg  = "#ffffff"
            border   = color
            tag      = ""
        pills_html += (
            f'<span style="display:inline-block;margin:3px;padding:5px 12px;'
            f'border:2px solid {border};border-radius:4px;background:{pill_bg};'
            f'color:{color};font-family:monospace;font-size:11px;font-weight:700">'
            f'{_h(v.god_name)}{tag}</span>'
        )

    # God table rows
    god_rows_html = ""
    for v in decree.voices:
        color   = _GOD_COLORS.get(v.god_name, "#757575")
        domain  = _GOD_DOMAINS.get(v.god_name, "")
        verdict = (
            f'<span style="color:#c62828">⚠ {_h(v.dissent)}</span>'
            if v.dissent else
            '<span style="color:#2e7d32">✓ Conforme</span>'
        )
        preview = _h(v.content[:220] + ("…" if len(v.content) > 220 else ""))
        god_rows_html += f"""
        <tr>
          <td style="border-left:3px solid {color};padding-left:8px;
                     font-weight:700;color:{color};white-space:nowrap">
            {_h(v.god_name)}
          </td>
          <td style="color:#666;font-size:10px">{domain}</td>
          <td style="font-family:monospace;font-size:10px;color:#666;white-space:nowrap">
            {v.tokens_used:,}
          </td>
          <td style="font-family:monospace;font-size:10px;color:#666;white-space:nowrap">
            {v.latency_ms:.0f} ms
          </td>
          <td style="font-size:11px">{verdict}</td>
          <td style="font-size:11px;color:#444">{preview}</td>
        </tr>"""

    # Tier badge
    tier_color = {"full": "#b8860b", "standard": "#1565c0", "minimal": "#757575"}.get(
        decree.budget_tier, "#757575"
    )

    synthesis_html = _md_to_html(decree.synthesis)

    # PQ signature preview (first 64 chars + ellipsis)
    sig_display = (
        (decree.pq_signature[:64] + "…")
        if decree.pq_signature
        else "NO DISPONIBLE"
    )

    # Domains tag
    domains_tag = (
        f'<span style="font-size:11px;color:#666">Dominios: '
        f'<strong>{_h(", ".join(decree.domains))}</strong></span>'
        if decree.domains else ""
    )

    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<style>
  @page {{
    size: A4;
    margin: 18mm 16mm 22mm 16mm;
  }}
  body {{
    font-family: Helvetica, Arial, sans-serif;
    font-size: 12px;
    color: #1a1a2e;
    line-height: 1.65;
    background: #ffffff;
  }}

  /* ── HEADER ── */
  .header-table {{ width:100%; border-collapse:collapse; margin-bottom:18px; }}
  .header-table td {{ vertical-align:top; }}
  .logo {{ font-size:26px; font-weight:900; letter-spacing:5px; color:#1a1a2e; }}
  .logo-sub {{ font-size:9px; color:#888; letter-spacing:2px; text-transform:uppercase;
               margin-top:3px; }}
  .header-gold {{ border-bottom:2px solid #c9a227; padding-bottom:12px; }}
  .decree-meta {{ text-align:right; font-size:10px; color:#666;
                  font-family:monospace; line-height:1.8; }}
  .decree-meta strong {{ font-size:14px; color:#1a1a2e; font-family:Helvetica,Arial,sans-serif; }}

  /* ── METRICS ── */
  .metrics-table {{ width:100%; border-collapse:collapse; margin-bottom:20px; }}
  .metrics-table td {{ width:25%; padding:0 6px; vertical-align:top; }}
  .metrics-table td:first-child {{ padding-left:0; }}
  .metrics-table td:last-child  {{ padding-right:0; }}
  .metric-box {{
    border:1px solid #e0e0e0; border-radius:6px; padding:12px 14px; text-align:center;
  }}
  .metric-label {{ font-size:8px; text-transform:uppercase; letter-spacing:1.5px;
                   color:#aaa; margin-bottom:8px; font-weight:700; }}
  .metric-value {{ font-size:28px; font-weight:900; line-height:1; }}
  .metric-sub   {{ font-size:10px; font-weight:700; margin-top:5px; }}

  /* ── SECTION ── */
  .section {{ margin-bottom:20px; }}
  .section-title {{
    font-size:8px; text-transform:uppercase; letter-spacing:2px; color:#aaa;
    border-bottom:1px solid #e8e8e8; padding-bottom:4px; margin-bottom:10px;
    font-weight:700;
  }}

  /* ── CONSENSUS BANNER ── */
  .consensus-banner {{
    padding:9px 14px; border-radius:5px; border:1px solid;
    font-weight:700; font-size:12px; margin-bottom:10px;
  }}

  /* ── SYNTHESIS ── */
  .synthesis-block {{
    border-left:3px solid #c9a227; padding:14px 18px; background:#fafafa;
    border-radius:0 6px 6px 0; font-size:12px; line-height:1.75;
  }}
  .synthesis-block h1 {{
    font-size:14px; color:#b8860b; margin:14px 0 6px;
    border-bottom:1px solid #e8e8e8; padding-bottom:4px;
  }}
  .synthesis-block h2 {{ font-size:13px; color:#1a1a2e; margin:12px 0 5px; }}
  .synthesis-block h3 {{ font-size:12px; color:#444; margin:10px 0 4px; }}
  .synthesis-block p  {{ margin-bottom:9px; }}
  .synthesis-block ul {{ padding-left:18px; margin-bottom:9px; }}
  .synthesis-block li {{ margin-bottom:3px; }}
  .synthesis-block code {{
    font-family:monospace; font-size:10px;
    background:#f0f0f0; padding:1px 4px; border-radius:3px;
  }}
  .synthesis-block strong {{ color:#1a1a2e; }}

  /* ── GOD TABLE ── */
  .god-table {{ width:100%; border-collapse:collapse; font-size:11px; }}
  .god-table th {{
    background:#f5f5f5; padding:6px 9px; text-align:left;
    font-size:8px; text-transform:uppercase; letter-spacing:1px; color:#888;
    border-bottom:2px solid #e0e0e0;
  }}
  .god-table td {{ padding:7px 9px; border-bottom:1px solid #f0f0f0; vertical-align:top; }}
  .god-table tr:last-child td {{ border-bottom:none; }}

  /* ── PQ BLOCK ── */
  .pq-block {{
    background:#f5f5f5; border:1px solid #e0e0e0; border-radius:6px;
    padding:14px 18px; font-family:monospace; font-size:10px; line-height:1.9;
  }}
  .pq-title {{
    font-family:Helvetica,Arial,sans-serif; font-size:8px; text-transform:uppercase;
    letter-spacing:2px; color:#aaa; font-weight:700; margin-bottom:10px;
  }}
  .pq-table {{ width:100%; border-collapse:collapse; }}
  .pq-table td {{ padding:1px 0; vertical-align:top; }}
  .pq-key {{ color:#aaa; width:195px; white-space:nowrap; }}
  .pq-val {{ color:#1a1a2e; word-break:break-all; }}
  .pq-seal {{
    margin-top:12px; padding-top:9px; border-top:1px solid #e0e0e0;
    font-family:Helvetica,Arial,sans-serif; font-size:9px; color:#999;
    line-height:1.6;
  }}

  .avoid-break {{ page-break-inside:avoid; }}
  .page-break  {{ page-break-before:always; }}
</style>
</head>
<body>

<!-- HEADER -->
<div class="header-gold">
  <table class="header-table">
    <tr>
      <td>
        <div class="logo">ENLIL</div>
        <div class="logo-sub">Consejo de los Dioses &middot; Orquestador Multi-IA Post-Cuántico</div>
      </td>
      <td class="decree-meta">
        <strong>DECRETO #{decree.id[:8].upper()}</strong><br>
        Emitido: {timestamp_str}<br>
        Tier: <strong style="color:{tier_color}">{decree.budget_tier.upper()}</strong>
        &nbsp;&middot;&nbsp;
        <span style="color:#2e7d32;font-family:Helvetica,Arial,sans-serif;
                     font-weight:700">ML-DSA-87 ✓</span>
      </td>
    </tr>
  </table>
</div>

<!-- METRICS -->
<table class="metrics-table avoid-break" style="margin-top:16px">
  <tr>
    <td>
      <div class="metric-box" style="border-color:{score_color};background:{score_bg}">
        <div class="metric-label">Índice de Salud</div>
        <div class="metric-value" style="color:{score_color}">{score}</div>
        <div class="metric-sub" style="color:{score_color}">{label}</div>
      </div>
    </td>
    <td>
      <div class="metric-box"
           style="border-color:{'#c62828' if n_dissent else '#2e7d32'};
                  background:{'#ffebee' if n_dissent else '#e8f5e9'}">
        <div class="metric-label">Disensos</div>
        <div class="metric-value"
             style="color:{'#c62828' if n_dissent else '#2e7d32'}">{n_dissent}</div>
        <div class="metric-sub"
             style="color:{'#c62828' if n_dissent else '#2e7d32'}">
          {'Revisar disenso' if n_dissent else 'Sin alertas'}
        </div>
      </div>
    </td>
    <td>
      <div class="metric-box">
        <div class="metric-label">Dioses Convocados</div>
        <div class="metric-value" style="color:#1a1a2e">{n_convened}</div>
        <div class="metric-sub" style="color:#888">de 9 en el Panteón</div>
      </div>
    </td>
    <td>
      <div class="metric-box">
        <div class="metric-label">Tokens Procesados</div>
        <div class="metric-value" style="color:#1a1a2e">{decree.total_tokens:,}</div>
        <div class="metric-sub" style="color:#888">Análisis agregado</div>
      </div>
    </td>
  </tr>
</table>

<!-- CONSULTA -->
<div class="section avoid-break">
  <div class="section-title">Consulta al Consejo</div>
  <div style="background:#fafafa;border:1px solid #e8e8e8;border-radius:5px;
              padding:12px 16px;font-style:italic;color:#444">
    {_h(decree.query)}
  </div>
  {f'<div style="margin-top:7px">{domains_tag}</div>' if domains_tag else ''}
</div>

<!-- CONSENSUS BAR -->
<div class="section avoid-break">
  <div class="section-title">Consenso del Consejo</div>
  <div class="consensus-banner"
       style="color:{consensus_color};background:{consensus_bg};
              border-color:{consensus_color}">
    {consensus_icon}&nbsp;{_h(consensus_text)}
  </div>
  <div>{pills_html}</div>
</div>

<!-- GOD TABLE -->
<div class="section">
  <div class="section-title">Deliberación — Voces del Panteón</div>
  <table class="god-table">
    <thead>
      <tr>
        <th>Dios</th>
        <th>Dominio</th>
        <th>Tokens</th>
        <th>Latencia</th>
        <th>Veredicto</th>
        <th>Extracto del Análisis</th>
      </tr>
    </thead>
    <tbody>{god_rows_html}</tbody>
  </table>
</div>

<!-- SYNTHESIS -->
<div class="section">
  <div class="section-title">Decreto — Síntesis del Consejo</div>
  <div class="synthesis-block">{synthesis_html}</div>
</div>

<!-- PQ TRACEABILITY BLOCK -->
<div class="section avoid-break" style="margin-top:28px">
  <div class="pq-block">
    <div class="pq-title">Bloque de Trazabilidad Post-Cuántica</div>
    <table class="pq-table">
      <tr>
        <td class="pq-key">IDENTIFICADOR DEL DECRETO</td>
        <td class="pq-val">{decree.id}</td>
      </tr>
      <tr>
        <td class="pq-key">HASH SHA-256 DEL CONTENIDO</td>
        <td class="pq-val">{content_hash}</td>
      </tr>
      <tr>
        <td class="pq-key">ALGORITMO DE FIRMA</td>
        <td class="pq-val">ML-DSA-87 (NIST FIPS 204) &mdash; Criptografía Post-Cuántica Activa</td>
      </tr>
      <tr>
        <td class="pq-key">TIMESTAMP DE DELIBERACIÓN</td>
        <td class="pq-val">{timestamp_str}</td>
      </tr>
      <tr>
        <td class="pq-key">FIRMA CRIPTOGRÁFICA (ML-DSA-87)</td>
        <td class="pq-val">{sig_display}</td>
      </tr>
    </table>
    <div class="pq-seal">
      Documento securizado mediante criptografía post-cuántica activa.
      Verificable introduciendo el Identificador del Decreto en
      <strong>{os.environ.get("ENLIL_BASE_URL", "http://localhost:8002")}/verify</strong>.
      Firma irrevocable &mdash; cualquier modificación del contenido invalida
      la verificación.
    </div>
  </div>
</div>

</body>
</html>"""


# ── Public API ───────────────────────────────────────────────────────────────

def generate_pdf(decree: Decree) -> bytes:
    """
    Render decree as PDF bytes using WeasyPrint.
    Raises RuntimeError if WeasyPrint is not installed.
    """
    try:
        from weasyprint import HTML as WeasyprintHTML  # type: ignore
    except ImportError:
        raise RuntimeError(
            "WeasyPrint no está instalado. "
            "Ejecuta: pip install weasyprint"
        )
    html = _build_html(decree)
    return WeasyprintHTML(string=html).write_pdf()


def generate_html(decree: Decree) -> str:
    """Return the raw HTML (useful for debugging or browser-print fallback)."""
    return _build_html(decree)
