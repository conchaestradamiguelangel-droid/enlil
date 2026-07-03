import asyncio
import os
from contextlib import asynccontextmanager
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Header, Depends
from pydantic import Field
from enlil.auth import (
    init_auth_tables, require_auth, require_master,
    create_client, list_clients, toggle_client,
    list_keys, revoke_key, add_key,
    all_clients_usage, client_usage_log, log_usage,
    monthly_tokens_used,
)
from fastapi.responses import HTMLResponse, StreamingResponse
import json as _json
from pydantic import BaseModel
from typing import Optional

load_dotenv()

from enlil import Orchestrator
from enlil.verticals.cybersecurity import parse_aegis_webhook, build_aegis_query, resolve_aegis_tier
from enlil.verticals.legal import parse_legal_request, build_legal_query

enlil: Orchestrator | None = None


def _get_enlil() -> Orchestrator:
    if enlil is None:
        raise HTTPException(503, "ENLIL inicializandose, reintenta en segundos")
    return enlil


@asynccontextmanager
async def lifespan(app: FastAPI):
    global enlil
    enlil = Orchestrator()
    init_auth_tables()
    yield


app = FastAPI(title="ENLIL", lifespan=lifespan)


# --- Modelos ---

class QueryRequest(BaseModel):
    query: str = Field(..., max_length=20000)
    context: str = Field("", max_length=50000)
    budget_tier: str | None = None
    parent_decree_id: str | None = None


class FeedbackRequest(BaseModel):
    useful: bool


# --- API ---

@app.post("/query")
async def run_query(req: QueryRequest, client: dict = Depends(require_auth)):
    decree = await _get_enlil().query(
        req.query, req.context, req.budget_tier, req.parent_decree_id,
        client_id=client["id"],
    )
    log_usage(
        client_id=client["id"],
        decree_id=decree.id,
        tokens=decree.total_tokens,
        budget_tier=decree.budget_tier,
        gods_count=len(decree.gods_convened),
        query_preview=req.query,
    )
    return {
        "decree_id": decree.id,
        "domains": decree.domains,
        "gods_convened": decree.gods_convened,
        "synthesis": decree.synthesis,
        "total_tokens": decree.total_tokens,
        "budget_tier": decree.budget_tier,
        "has_dissent": decree.has_dissent(),
        "dissenting_gods": decree.dissenting_gods(),
        "pq_signed": bool(decree.pq_signature),
        "voices": [
            {
                "god": v.god_name,
                "content": v.content,
                "tokens": v.tokens_used,
                "latency_ms": v.latency_ms,
                "dissent": v.dissent,
            }
            for v in decree.voices
        ],
    }


@app.post("/query/stream")
async def run_query_stream(req: QueryRequest, client: dict = Depends(require_auth)):
    async def _gen():
        try:
            async for ev in _get_enlil().query_stream(
                req.query, req.context, req.budget_tier, req.parent_decree_id,
                client_id=client["id"],
            ):
                data = _json.loads(ev)
                if data["type"] == "done":
                    log_usage(
                        client_id=client["id"],
                        decree_id=data["decree_id"],
                        tokens=data["total_tokens"],
                        budget_tier=data["budget_tier"],
                        gods_count=len(data["gods_convened"]),
                        query_preview=req.query,
                    )
                yield "data: " + ev + "\n\n"
        except Exception as exc:
            _err = _json.dumps({"type": "error", "message": str(exc)})
            yield "data: " + _err + "\n\n"
    return StreamingResponse(
        _gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/feedback/{decree_id}")
async def give_feedback(decree_id: str, req: FeedbackRequest):
    _get_enlil().feedback(decree_id, req.useful)
    return {"ok": True}


@app.get("/history")
async def get_history(limit: int = 20):
    decrees = _get_enlil().history(limit)
    return [
        {
            "id": d.id,
            "timestamp": d.timestamp,
            "query": d.query[:120],
            "domains": d.domains,
            "gods_convened": d.gods_convened,
            "total_tokens": d.total_tokens,
            "has_dissent": d.has_dissent(),
            "budget_tier": d.budget_tier,
        }
        for d in decrees
    ]


@app.get("/decree/{decree_id}")
async def get_decree(decree_id: str):
    decree = _get_enlil().get_decree(decree_id)
    if not decree:
        raise HTTPException(404, "Decreto no encontrado")
    return {
        "id": decree.id,
        "timestamp": decree.timestamp,
        "query": decree.query,
        "domains": decree.domains,
        "gods_convened": decree.gods_convened,
        "synthesis": decree.synthesis,
        "total_tokens": decree.total_tokens,
        "budget_tier": decree.budget_tier,
        "has_dissent": decree.has_dissent(),
        "dissenting_gods": decree.dissenting_gods(),
        "parent_decree_id": decree.parent_decree_id,
        "voices": [
            {
                "god": v.god_name,
                "model": v.model,
                "content": v.content,
                "tokens": v.tokens_used,
                "latency_ms": v.latency_ms,
                "dissent": v.dissent,
            }
            for v in decree.voices
        ],
        "pq_signature": decree.pq_signature,
        "pq_signed": bool(decree.pq_signature),
    }


@app.get("/decree/{decree_id}/verify")
async def verify_decree(decree_id: str):
    from enlil.quantum import public_key_b64, is_available
    result = _get_enlil().store.verify(decree_id)
    result["pq_available"] = is_available()
    result["public_key"] = public_key_b64()
    return result




@app.get("/decree/{decree_id}/export")
async def export_decree(decree_id: str, format: str = "pdf"):
    decree = _get_enlil().get_decree(decree_id)
    if not decree:
        raise HTTPException(404, "Decreto no encontrado")
    from enlil.export import generate_pdf, generate_html
    if format == "html":
        html = generate_html(decree)
        return Response(
            content=html,
            media_type="text/html",
            headers={"Content-Disposition": f'inline; filename="decreto-{decree_id[:8]}.html"'},
        )
    try:
        pdf_bytes = generate_pdf(decree)
    except RuntimeError as e:
        raise HTTPException(501, str(e))
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="decreto-{decree_id[:8]}.pdf"'},
    )

@app.get("/quantum")
async def quantum_status():
    from enlil.quantum import is_available, public_key_b64
    return {
        "pq_available": is_available(),
        "algorithm": "ML-DSA-87 (NIST FIPS 204)",
        "public_key": public_key_b64(),
        "description": "Todos los Decretos emitidos desde ENLIL S7 están firmados con criptografía post-cuántica irrevocable.",
    }


@app.get("/pantheon")
async def get_pantheon():
    orch = _get_enlil()
    reputation = orch.pantheon_status()
    gods = []
    for name, god in orch.pantheon.items():
        gods.append({
            "name": name,
            "display_name": god.name,
            "model": god.model,
            "role": god.role,
            "domains": god.domains,
            "reputation": reputation.get(name, {}),
        })
    return gods


@app.post("/aegis/analyze")
async def aegis_analyze(
    payload: dict,
    x_aegis_token: Optional[str] = Header(None),
):
    """
    Recibe una alerta de AEGIS y la analiza con el Consejo de Dioses.
    Retorna un Decreto con contramedidas concretas.
    """
    _aegis_token = os.environ.get("AEGIS_ENLIL_TOKEN", "")
    if _aegis_token and x_aegis_token != _aegis_token:
        raise HTTPException(403, "Token AEGIS inválido")

    alert = parse_aegis_webhook(payload)
    query, context = build_aegis_query(alert)
    tier = resolve_aegis_tier(alert.severity)

    decree = await _get_enlil().query(
        text=query,
        context=context,
        budget_tier=tier,
        client_id="aegis",
    )
    return {
        "decree_id": decree.id,
        "alert_type": alert.alert_type,
        "severity": alert.severity,
        "budget_tier": tier,
        "synthesis": decree.synthesis,
        "gods_convened": decree.gods_convened,
        "total_tokens": decree.total_tokens,
        "has_dissent": decree.has_dissent(),
        "dissenting_gods": decree.dissenting_gods(),
        "pq_signed": bool(decree.pq_signature),
        "voices": [
            {"god": v.god_name, "content": v.content, "tokens": v.tokens_used,
             "latency_ms": v.latency_ms, "dissent": v.dissent}
            for v in decree.voices
        ],
    }


@app.get("/aegis/history")
async def aegis_history(limit: int = 10):
    """Últimos decretos relacionados con alertas AEGIS."""
    all_decrees = _get_enlil().history(limit=50)
    aegis = [d for d in all_decrees if any(kw in d.query for kw in ["AEGIS", "alerta", "firewall", "intrusion", "DDoS"])]
    return [
        {"id": d.id, "timestamp": d.timestamp, "query": d.query[:100],
         "synthesis": d.synthesis[:200], "gods_convened": d.gods_convened}
        for d in aegis[:limit]
    ]


@app.post("/legal/analyze")
async def legal_analyze(payload: dict, client: dict = Depends(require_auth)):
    """
    Analiza un documento legal con el Consejo de Dioses.
    Retorna un Decreto con análisis de riesgos y recomendaciones.

    Payload: {"type": "contrato", "text": "...", "jurisdiction": "España", "parties": [], "context": ""}
    """
    try:
        document = parse_legal_request(payload)
    except ValueError as e:
        raise HTTPException(400, str(e))

    query, context = build_legal_query(document)

    decree = await _get_enlil().query(
        text=query,
        context=context,
        budget_tier="standard",
    )
    return {
        "decree_id": decree.id,
        "doc_type": document.doc_type,
        "jurisdiction": document.jurisdiction,
        "synthesis": decree.synthesis,
        "gods_convened": decree.gods_convened,
        "has_dissent": decree.has_dissent(),
        "dissenting_gods": decree.dissenting_gods(),
        "voices": [
            {"god": v.god_name, "content": v.content, "dissent": v.dissent}
            for v in decree.voices
        ],
    }


@app.get("/legal/history")
async def legal_history(limit: int = 10):
    """Últimos análisis legales realizados."""
    all_decrees = _get_enlil().history(limit=50)
    legal = [
        d for d in all_decrees
        if any(kw in d.query for kw in ["Análisis legal", "contrato", "cláusula", "NDA", "acuerdo"])
    ]
    return [
        {
            "id": d.id,
            "timestamp": d.timestamp,
            "query": d.query[:100],
            "synthesis": d.synthesis[:200],
            "gods_convened": d.gods_convened,
        }
        for d in legal[:limit]
    ]


@app.get("/rl/status")
async def rl_status():
    """Métricas RL: policy weights, reward history, health por dios."""
    return _get_enlil().rl_status()


@app.post("/rl/update")
async def rl_update(_: dict = Depends(require_master)):
    """Fuerza un ciclo de policy gradient update (admin)."""
    return _get_enlil().rl_update()


@app.get("/mode")
async def system_mode():
    """Modo activo del sistema: council, Qdrant, modelos en uso."""
    return _get_enlil().system_mode()


@app.get("/evolution")
async def evolution_fitness():
    """Fitness evolutivo del panteón — presión de selección y decaimiento."""
    return _get_enlil().evolution_fitness()


@app.get("/meta")
async def meta_observer(limit: int = 200):
    """Patrones aprendidos por el Meta-Observador del panteón."""
    return _get_enlil().meta_patterns(limit)


@app.get("/corpus/status")
async def corpus_status():
    """Estado del corpus sumerio ancestral."""
    orch = _get_enlil()
    if not orch.corpus:
        return {"available": False, "texts": 0, "collection": "enlil_corpus"}
    return {
        "available": True,
        "texts": orch.corpus.count(),
        "collection": "enlil_corpus",
    }


@app.get("/stats")
async def get_stats():
    """Datos para gráficos del dashboard."""
    orch = _get_enlil()

    rep_history = orch.reputation.history(200)

    recent = orch.history(50)
    token_trend = [
        {"timestamp": d.timestamp, "tokens": d.total_tokens, "tier": d.budget_tier}
        for d in recent
    ]

    latency_sums: dict[str, list[float]] = {}
    domain_counts: dict[str, int] = {}
    for d in recent:
        for v in d.voices:
            if v.latency_ms > 0:
                latency_sums.setdefault(v.god_name, []).append(v.latency_ms)
        for domain in d.domains:
            domain_counts[domain] = domain_counts.get(domain, 0) + 1

    latency_avg = {
        god: round(sum(lats) / len(lats), 1)
        for god, lats in latency_sums.items()
    }

    return {
        "reputation_history": rep_history,
        "token_trend": token_trend,
        "latency_avg": latency_avg,
        "domain_distribution": domain_counts,
    }


@app.get("/health")
async def health():
    """Health check para monitorización."""
    orch = _get_enlil()
    mode = orch.system_mode()
    return {
        "status": "ok",
        "council_mode": mode["council_mode"],
        "qdrant_active": mode["qdrant_active"],
        "decree_count": len(orch.history(limit=1)),
    }



ADMIN_HTML = """<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ENLIL Admin</title>
<style>
:root{--bg:#07040f;--s:#0f0a1e;--s2:#150f28;--b:#231a3d;--a:#a78bfa;--gold:#fbbf24;--green:#34d399;--red:#f87171;--cyan:#22d3ee;--text:#ede9fe;--muted:#6b5a8a;}
*{margin:0;padding:0;box-sizing:border-box;}
body{background:var(--bg);color:var(--text);font-family:"Segoe UI",system-ui,sans-serif;font-size:0.9rem;}
nav{display:flex;align-items:center;gap:1rem;padding:1rem 2rem;border-bottom:1px solid var(--b);background:rgba(7,4,15,0.97);}
.nav-title{font-weight:900;letter-spacing:0.15em;color:var(--a);font-size:1.1rem;}
.nav-tag{font-size:0.65rem;color:var(--muted);letter-spacing:0.1em;text-transform:uppercase;}
.nav-right{margin-left:auto;display:flex;gap:0.5rem;align-items:center;}
#key-input{background:var(--s2);border:1px solid var(--b);color:var(--text);padding:0.35rem 0.8rem;font-size:0.78rem;font-family:monospace;width:340px;}
.btn{background:linear-gradient(135deg,var(--a),#f472b6);color:#fff;border:none;padding:0.35rem 1rem;font-size:0.78rem;font-weight:700;cursor:pointer;}
.btn-sm{background:transparent;border:1px solid var(--b);color:var(--muted);padding:0.25rem 0.7rem;font-size:0.72rem;cursor:pointer;transition:all 0.2s;}
.btn-sm:hover{border-color:var(--a);color:var(--a);}
.btn-danger{border-color:var(--red)!important;color:var(--red)!important;}
.btn-success{border-color:var(--green)!important;color:var(--green)!important;}
main{max-width:1200px;margin:0 auto;padding:2rem;}
.gate{display:flex;flex-direction:column;align-items:center;justify-content:center;min-height:60vh;gap:1rem;text-align:center;}
.gate h2{font-size:1.5rem;color:var(--a);}
.gate input{background:var(--s2);border:1px solid var(--b);color:var(--text);padding:0.6rem 1rem;font-size:0.9rem;font-family:monospace;width:380px;}
.section{margin-bottom:2.5rem;}
.section-title{font-size:0.7rem;letter-spacing:0.2em;text-transform:uppercase;color:var(--a);margin-bottom:1rem;padding-bottom:0.4rem;border-bottom:1px solid var(--b);}
.stats-row{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:1rem;margin-bottom:2rem;}
.stat-card{background:var(--s);border:1px solid var(--b);border-top:2px solid var(--a);padding:1rem;}
.stat-val{font-size:1.8rem;font-weight:900;color:var(--a);}
.stat-lbl{font-size:0.65rem;color:var(--muted);text-transform:uppercase;letter-spacing:0.08em;margin-top:0.2rem;}
table{width:100%;border-collapse:collapse;background:var(--s);border:1px solid var(--b);}
th{background:var(--s2);color:var(--muted);font-size:0.65rem;letter-spacing:0.1em;text-transform:uppercase;padding:0.6rem 0.8rem;text-align:left;border-bottom:1px solid var(--b);}
td{padding:0.6rem 0.8rem;border-bottom:1px solid var(--b);font-size:0.82rem;vertical-align:middle;}
tr:last-child td{border-bottom:none;}
.badge{display:inline-block;padding:0.15rem 0.5rem;font-size:0.62rem;font-weight:700;letter-spacing:0.08em;}
.badge-on{background:rgba(52,211,153,0.1);border:1px solid var(--green);color:var(--green);}
.badge-off{background:rgba(248,113,113,0.1);border:1px solid var(--red);color:var(--red);}
.modal{display:none;position:fixed;inset:0;background:rgba(0,0,0,0.7);z-index:100;align-items:center;justify-content:center;}
.modal.open{display:flex;}
.modal-box{background:var(--s2);border:1px solid var(--b);border-top:2px solid var(--a);padding:2rem;width:440px;max-width:95vw;}
.modal-title{font-size:0.8rem;font-weight:700;letter-spacing:0.1em;text-transform:uppercase;color:var(--a);margin-bottom:1.2rem;}
.form-row{display:flex;flex-direction:column;gap:0.3rem;margin-bottom:0.8rem;}
.form-row label{font-size:0.65rem;color:var(--muted);text-transform:uppercase;letter-spacing:0.08em;}
.form-row input,.form-row select,.form-row textarea{background:var(--bg);border:1px solid var(--b);color:var(--text);padding:0.45rem 0.8rem;font-size:0.85rem;font-family:inherit;width:100%;}
.key-box{background:var(--bg);border:1px solid var(--green);color:var(--green);padding:0.8rem;font-family:monospace;font-size:0.78rem;word-break:break-all;margin:0.5rem 0;}
.log-table td{font-size:0.75rem;}
.detail-panel{display:none;background:var(--s);border:1px solid var(--b);border-top:2px solid var(--cyan);padding:1.5rem;margin-top:1rem;}
.detail-panel.open{display:block;}
.error{color:var(--red);font-size:0.82rem;padding:0.5rem;}
</style>
</head>
<body>
<nav>
  <div>
    <div class="nav-title">ENLIL <span style="color:var(--gold)">ADMIN</span></div>
    <div class="nav-tag">Panel de Control — Solo para el Creador</div>
  </div>
  <div class="nav-right">
    <input id="key-input" type="password" placeholder="Master Key..." oninput="storeKey(this.value)">
    <button class="btn" onclick="loadDashboard()">Entrar</button>
  </div>
</nav>
<main id="main">
  <div class="gate" id="gate">
    <h2>⚡ Panel de Administración</h2>
    <p style="color:var(--muted)">Introduce tu Master Key arriba para acceder.</p>
  </div>
</main>

<!-- Modal nuevo cliente -->
<div class="modal" id="modal-new">
  <div class="modal-box">
    <div class="modal-title">Nuevo Cliente</div>
    <div class="form-row"><label>Nombre</label><input id="f-name" placeholder="Empresa o persona"></div>
    <div class="form-row"><label>Email</label><input id="f-email" type="email" placeholder="cliente@empresa.com"></div>
    <div class="form-row"><label>Plan</label>
      <select id="f-plan">
        <option value="standard">Standard — hasta 4 dioses</option>
        <option value="full">Full — 9 dioses</option>
        <option value="enterprise">Enterprise</option>
      </select>
    </div>
    <div class="form-row"><label>Budget mensual (tokens)</label><input id="f-budget" type="number" value="500000"></div>
    <div class="form-row"><label>Max consultas/hora</label><input id="f-rph" type="number" value="30"></div>
    <div class="form-row"><label>Máx decretos trial (vacío = sin límite)</label><input id="f-maxreq" type="number" placeholder="ej: 3, 5, 10"></div>
    <div class="form-row"><label>Notas internas</label><textarea id="f-notes" rows="2"></textarea></div>
    <div id="new-result"></div>
    <div style="display:flex;gap:0.5rem;margin-top:1rem;">
      <button class="btn" onclick="createClient()">Crear y generar key</button>
      <button class="btn-sm" onclick="closeModal()">Cancelar</button>
    </div>
  </div>
</div>

<script>
let MK = sessionStorage.getItem("enlil_mk") || "";
if (MK) { document.getElementById("key-input").value = MK; loadDashboard(); }

function storeKey(v){ MK = v; sessionStorage.setItem("enlil_mk", v); }

async function api(path, method="GET", body=null){
  const opts = { method, headers:{"X-Master-Key": MK, "Content-Type":"application/json"} };
  if (body) opts.body = JSON.stringify(body);
  const r = await fetch(path, opts);
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

async function apiQ(path, params={}){
  const q = new URLSearchParams(params).toString();
  return api(path + (q ? "?"+q : ""));
}

async function loadDashboard(){
  if (!MK){ alert("Introduce la Master Key"); return; }
  const main = document.getElementById("main");
  main.innerHTML = "<p style='color:var(--muted);padding:2rem'>Cargando...</p>";
  try {
    const clients = await api("/admin/clients");
    renderDashboard(clients);
  } catch(e){
    main.innerHTML = "<p class='error'>Error: " + e.message + "</p>";
  }
}

function renderDashboard(clients){
  const totalClients = clients.length;
  const activeClients = clients.filter(c=>c.active).length;
  const totalTokens = clients.reduce((a,c)=>a+c.tokens_month,0);
  const totalReq = clients.reduce((a,c)=>a+c.requests_month,0);

  document.getElementById("main").innerHTML = `
    <div class="section">
      <div class="section-title">Resumen este mes</div>
      <div class="stats-row">
        <div class="stat-card"><div class="stat-val">${activeClients}</div><div class="stat-lbl">Clientes activos</div></div>
        <div class="stat-card"><div class="stat-val">${totalReq.toLocaleString()}</div><div class="stat-lbl">Consultas totales</div></div>
        <div class="stat-card"><div class="stat-val">${(totalTokens/1000).toFixed(0)}K</div><div class="stat-lbl">Tokens consumidos</div></div>
        <div class="stat-card"><div class="stat-val">${totalClients}</div><div class="stat-lbl">Total clientes</div></div>
      </div>
    </div>

    <div class="section">
      <div class="section-title" style="display:flex;justify-content:space-between;align-items:center;">
        <span>Clientes</span>
        <button class="btn-sm btn-success" onclick="openNewModal()">+ Nuevo cliente</button>
      </div>
      <table>
        <thead><tr>
          <th>Cliente</th><th>Plan</th><th>Tokens este mes</th><th>Budget</th>
          <th>Consultas/h max</th><th>Consultas mes</th><th>Estado</th><th>Acciones</th>
        </tr></thead>
        <tbody>
          ${clients.map(c => `<tr>
            <td>
              <div style="font-weight:700;color:var(--text)">${c.name}</div>
              <div style="font-size:0.68rem;color:var(--muted)">${c.email}</div>
            </td>
            <td><span style="color:var(--a)">${c.plan}</span></td>
            <td>
              <div>${(c.tokens_month||0).toLocaleString()}</div>
              <div style="font-size:0.65rem;color:var(--muted)">${Math.round((c.tokens_month||0)*100/(c.monthly_token_budget||1))}% del budget</div>
            </td>
            <td style="color:var(--gold)">${(c.monthly_token_budget||0).toLocaleString()}</td>
            <td>${c.max_requests_per_hour}/h</td>
            <td>${(c.requests_month||0).toLocaleString()}</td>
            <td><span class="badge ${c.active ? 'badge-on':'badge-off'}">${c.active ? 'ACTIVO':'INACTIVO'}</span></td>
            <td style="display:flex;gap:0.4rem;flex-wrap:wrap;">
              <button class="btn-sm" onclick="showDetail('${c.id}')">Ver logs</button>
              <button class="btn-sm ${c.active ? 'btn-danger':'btn-success'}"
                onclick="toggleClient('${c.id}',${c.active ? 'false':'true'})">
                ${c.active ? 'Desactivar':'Activar'}
              </button>
              <button class="btn-sm" onclick="addKey('${c.id}')">+ Key</button>
            </td>
          </tr>
          <tr id="detail-${c.id}"><td colspan="8" style="padding:0;">
            <div class="detail-panel" id="dp-${c.id}"></div>
          </td></tr>`
          ).join("")}
        </tbody>
      </table>
    </div>
  `;
}

async function showDetail(clientId){
  const panel = document.getElementById("dp-"+clientId);
  const row = document.getElementById("detail-"+clientId);
  if (panel.classList.contains("open")){ panel.classList.remove("open"); return; }
  panel.innerHTML = "<p style='color:var(--muted);padding:1rem'>Cargando logs...</p>";
  panel.classList.add("open");
  try {
    const [logs, keys] = await Promise.all([
      api("/admin/clients/"+clientId+"/usage"),
      api("/admin/clients/"+clientId+"/keys"),
    ]);
    panel.innerHTML = `
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:2rem;">
        <div>
          <div class="section-title">API Keys</div>
          ${keys.map(k=>`<div style="display:flex;align-items:center;gap:0.5rem;margin-bottom:0.5rem;">
            <code style="font-size:0.7rem;color:${k.active?'var(--green)':'var(--red)'};">${k.key.slice(0,20)}...</code>
            <span style="font-size:0.62rem;color:var(--muted)">${k.label}</span>
            ${k.active ? "<button class='btn-sm btn-danger' onclick=\"revokeKey('"+k.key+"')\">Revocar</button>" : "<span style='font-size:0.62rem;color:var(--red)'>Revocada</span>"}
          </div>`).join("")}
        </div>
        <div>
          <div class="section-title">Últimos 50 decretos</div>
          <table class="log-table">
            <thead><tr><th>Fecha</th><th>Tokens</th><th>Tier</th><th>Consulta</th></tr></thead>
            <tbody>
              ${logs.map(l=>`<tr>
                <td>${new Date(l.timestamp*1000).toLocaleDateString("es")}</td>
                <td>${l.tokens_used.toLocaleString()}</td>
                <td>${l.budget_tier}</td>
                <td style="max-width:220px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--muted)">${l.query_preview}</td>
              </tr>`).join("")}
            </tbody>
          </table>
        </div>
      </div>
    `;
  } catch(e){
    panel.innerHTML = "<p class='error'>"+e.message+"</p>";
  }
}

async function toggleClient(id, active){
  try { await apiQ("/admin/clients/"+id+"/toggle", {active}); await loadDashboard(); }
  catch(e){ alert("Error: "+e.message); }
}

async function revokeKey(key){
  if (!confirm("¿Revocar esta key?")) return;
  try { await api("/admin/keys/"+encodeURIComponent(key), "DELETE"); alert("Key revocada."); await loadDashboard(); }
  catch(e){ alert("Error: "+e.message); }
}

async function addKey(clientId){
  const label = prompt("Etiqueta para la nueva key:", "extra") || "extra";
  try {
    const r = await apiQ("/admin/clients/"+clientId+"/keys", {label});
    alert("Nueva API key:\n\n" + r.api_key + "\n\nGuárdala ahora, no se volverá a mostrar completa.");
    await loadDashboard();
  } catch(e){ alert("Error: "+e.message); }
}

function openNewModal(){ document.getElementById("modal-new").classList.add("open"); document.getElementById("new-result").innerHTML = ""; }
function closeModal(){ document.getElementById("modal-new").classList.remove("open"); }

async function createClient(){
  const name = document.getElementById("f-name").value.trim();
  const email = document.getElementById("f-email").value.trim();
  const plan = document.getElementById("f-plan").value;
  const budget = parseInt(document.getElementById("f-budget").value)||500000;
  const rph = parseInt(document.getElementById("f-rph").value)||30;
  const notes = document.getElementById("f-notes").value;
  const maxreqVal = document.getElementById("f-maxreq").value;
  const maxreq = maxreqVal ? parseInt(maxreqVal) : null;
  if (!name||!email){ alert("Nombre y email son obligatorios"); return; }
  try {
    const params = {name,email,plan,monthly_token_budget:budget,max_requests_per_hour:rph,notes};
    if (maxreq !== null) params.max_total_requests = maxreq;
    const r = await apiQ("/admin/clients", params);
    document.getElementById("new-result").innerHTML =
      "<div class='section-title' style='margin-top:1rem'>Cliente creado</div>" +
      "<div class='key-box'>"+r.api_key+"</div>" +
      "<p style='font-size:0.72rem;color:var(--muted)'>ID: "+r.client_id+" — Envía esta key al cliente. No se volverá a mostrar completa.</p>";
    loadDashboard();
  } catch(e){
    document.getElementById("new-result").innerHTML = "<p class='error'>"+e.message+"</p>";
  }
}
</script>
</body>
</html>
"""


# ═══════════════════════════════════════════════════════════
# ADMIN API  (requiere header X-Master-Key)
# ═══════════════════════════════════════════════════════════

@app.post("/admin/clients")
async def admin_create_client(
    name: str,
    email: str,
    plan: str = "standard",
    monthly_token_budget: int = 500000,
    max_requests_per_hour: int = 30,
    max_total_requests: Optional[int] = None,
    notes: str = "",
    _=Depends(require_master),
):
    result = create_client(name, email, plan, monthly_token_budget, max_requests_per_hour, max_total_requests, notes)
    return result


@app.get("/admin/clients")
async def admin_list_clients(_=Depends(require_master)):
    return all_clients_usage()


@app.post("/admin/clients/{client_id}/toggle")
async def admin_toggle_client(client_id: str, active: bool, _=Depends(require_master)):
    toggle_client(client_id, active)
    return {"ok": True}


@app.get("/admin/clients/{client_id}/keys")
async def admin_list_keys(client_id: str, _=Depends(require_master)):
    return list_keys(client_id)


@app.post("/admin/clients/{client_id}/keys")
async def admin_add_key(client_id: str, label: str = "extra", _=Depends(require_master)):
    key = add_key(client_id, label)
    return {"api_key": key}


@app.delete("/admin/keys/{key}")
async def admin_revoke_key(key: str, _=Depends(require_master)):
    revoke_key(key)
    return {"ok": True}


@app.get("/admin/clients/{client_id}/usage")
async def admin_client_usage(client_id: str, limit: int = 100, _=Depends(require_master)):
    return client_usage_log(client_id, limit)


@app.get("/admin", response_class=HTMLResponse)
async def admin_panel():
    return HTMLResponse(ADMIN_HTML)


@app.get("/", response_class=HTMLResponse)
async def dashboard():
    return _dashboard_html()


def _dashboard_html() -> str:
    return """<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>ENLIL — Consejo de los Dioses</title>
<script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');
  * { box-sizing: border-box; margin: 0; padding: 0; }
  :root {
    --bg: #07080f; --surface: #0e1018; --surface2: #141720;
    --border: #1e2330; --border2: #252c3a;
    --text: #c9d1d9; --muted: #6b7486; --muted2: #8b949e;
    --gold: #e6c97a; --gold-dim: rgba(230,201,122,0.12);
    --claude: #e6c97a; --enki: #4fc3f7; --ninurta: #ef5350; --inanna: #ce93d8;
    --green: #3fb950; --red: #da3633;
  }
  body { font-family: 'Inter', sans-serif; background: var(--bg); color: var(--text); min-height: 100vh; }

  /* HEADER */
  header {
    background: var(--surface); border-bottom: 1px solid var(--border);
    padding: 14px 32px; display: flex; align-items: center; justify-content: space-between;
  }
  .header-left { display: flex; align-items: center; gap: 16px; }
  .logo { font-size: 1.5rem; font-weight: 700; color: var(--gold); letter-spacing: 4px; }
  .logo-sub { font-size: 0.72rem; color: var(--muted); letter-spacing: 1px; text-transform: uppercase; }
  .header-right { display: flex; gap: 8px; align-items: center; }
  .status-dot { width: 7px; height: 7px; border-radius: 50%; background: var(--green);
    box-shadow: 0 0 6px var(--green); animation: pulse-dot 2s infinite; }
  @keyframes pulse-dot { 0%,100%{opacity:1} 50%{opacity:.5} }
  .status-label { font-size: 0.72rem; color: var(--muted); }

  /* LAYOUT */
  .layout { display: grid; grid-template-columns: 1fr 320px; gap: 20px; padding: 20px 32px; max-width: 1440px; }

  /* CARDS */
  .card { background: var(--surface); border: 1px solid var(--border); border-radius: 10px; padding: 20px; }
  .card-title { font-size: 0.72rem; color: var(--muted); text-transform: uppercase; letter-spacing: 1.5px; margin-bottom: 16px; font-weight: 500; }

  /* QUERY INPUT */
  textarea {
    width: 100%; background: var(--bg); border: 1px solid var(--border2);
    color: var(--text); border-radius: 8px; padding: 14px; font-size: 0.95rem;
    font-family: 'Inter', sans-serif; resize: vertical; min-height: 90px; line-height: 1.6;
    transition: border-color .2s;
  }
  textarea:focus { outline: none; border-color: var(--gold); }
  textarea::placeholder { color: var(--muted); }
  .controls { display: flex; gap: 10px; margin-top: 12px; align-items: center; flex-wrap: wrap; }
  select {
    background: var(--bg); border: 1px solid var(--border2); color: var(--text);
    padding: 8px 14px; border-radius: 6px; font-size: 0.82rem; font-family: 'Inter', sans-serif;
    cursor: pointer;
  }
  .btn-invoke {
    background: var(--gold); color: #07080f; border: none; padding: 9px 22px;
    border-radius: 6px; font-size: 0.85rem; font-weight: 700; cursor: pointer;
    transition: all .2s; letter-spacing: 0.5px;
  }
  .btn-invoke:hover { background: #f0d88a; transform: translateY(-1px); box-shadow: 0 4px 16px rgba(230,201,122,0.25); }
  .btn-invoke:disabled { opacity: .5; cursor: not-allowed; transform: none; box-shadow: none; }
  .btn-sm { padding: 6px 14px; border-radius: 5px; border: 1px solid var(--border2); background: var(--surface2);
    color: var(--text); font-size: 0.78rem; cursor: pointer; transition: all .15s; font-family: 'Inter', sans-serif; }
  .btn-sm:hover { border-color: var(--gold); color: var(--gold); }
  .btn-yes { border-color: var(--green) !important; color: var(--green) !important; }
  .btn-no  { border-color: var(--red)   !important; color: var(--red)   !important; }
  .btn-pdf { border-color: var(--gold) !important; color: var(--gold) !important; text-decoration: none; display: inline-flex; align-items: center; gap: 5px; }

  /* COUNCIL SECTION (deliberation) */
  #council { display: none; margin-top: 18px; }
  .council-title {
    font-size: 0.72rem; color: var(--muted); text-transform: uppercase; letter-spacing: 1.5px;
    margin-bottom: 12px; display: flex; align-items: center; gap: 8px;
  }
  .council-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }

  /* GOD CARD */
  .god-panel {
    background: var(--bg); border: 1px solid var(--border2); border-radius: 8px;
    padding: 14px; transition: border-color .3s, box-shadow .3s; position: relative; overflow: hidden;
  }
  .god-panel.active {
    box-shadow: 0 0 0 1px var(--god-color), 0 0 20px rgba(var(--god-rgb), 0.12);
    border-color: var(--god-color);
  }
  .god-panel.done { opacity: 1; }
  .god-header { display: flex; align-items: center; gap: 10px; margin-bottom: 10px; }
  .god-symbol {
    width: 36px; height: 36px; border-radius: 8px; display: flex; align-items: center;
    justify-content: center; font-size: 1.1rem; flex-shrink: 0;
    background: rgba(var(--god-rgb), 0.12); border: 1px solid rgba(var(--god-rgb), 0.25);
  }
  .god-info { flex: 1; min-width: 0; }
  .god-name-label { font-size: 0.85rem; font-weight: 600; color: var(--god-color); }
  .god-model { font-size: 0.68rem; color: var(--muted); font-family: 'JetBrains Mono', monospace; margin-top: 1px;
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .god-status { display: flex; align-items: center; gap: 6px; }
  .god-status-badge {
    font-size: 0.68rem; padding: 2px 8px; border-radius: 20px; font-weight: 500;
    background: rgba(var(--god-rgb), 0.1); color: var(--god-color); border: 1px solid rgba(var(--god-rgb), 0.2);
    white-space: nowrap;
  }
  .god-status-badge.idle { background: var(--surface2); color: var(--muted); border-color: var(--border2); }
  .god-status-badge.thinking { animation: badge-pulse 1.4s infinite; }
  @keyframes badge-pulse { 0%,100%{opacity:1} 50%{opacity:.45} }
  .god-metrics { font-size: 0.68rem; color: var(--muted); font-family: 'JetBrains Mono', monospace; }

  /* Response text */
  .god-response {
    margin-top: 10px; font-size: 0.82rem; line-height: 1.6; color: var(--text);
    max-height: 140px; overflow-y: auto; border-top: 1px solid var(--border);
    padding-top: 10px; display: none; white-space: pre-wrap;
  }
  .god-response.visible { display: block; }
  .god-response::-webkit-scrollbar { width: 3px; }
  .god-response::-webkit-scrollbar-thumb { background: var(--border2); border-radius: 2px; }

  /* Dissent */
  .god-dissent { margin-top: 6px; font-size: 0.72rem; color: var(--red); font-style: italic; display: none; }
  .god-dissent.visible { display: block; }

  /* Shimmer loading */
  .shimmer {
    background: linear-gradient(90deg, var(--surface2) 25%, var(--border2) 50%, var(--surface2) 75%);
    background-size: 200% 100%; animation: shimmer 1.5s infinite; border-radius: 4px;
    height: 10px; margin: 4px 0;
  }
  @keyframes shimmer { 0%{background-position:200% 0} 100%{background-position:-200% 0} }

  /* DECREE RESULT */
  #result { margin-top: 18px; display: none; }
  .decree-header {
    display: flex; align-items: flex-start; justify-content: space-between;
    margin-bottom: 14px; gap: 12px; flex-wrap: wrap;
  }
  .decree-badges { display: flex; gap: 6px; flex-wrap: wrap; }
  .tag {
    background: var(--surface2); border: 1px solid var(--border2); border-radius: 20px;
    padding: 3px 10px; font-size: 0.70rem; color: var(--muted2); white-space: nowrap;
  }
  .tag.gold { border-color: rgba(230,201,122,0.4); color: var(--gold); background: var(--gold-dim); }
  .tag.red  { border-color: rgba(218,54,51,0.4); color: var(--red); background: rgba(218,54,51,0.08); }
  .tag.pq   { border-color: rgba(63,185,80,0.4); color: var(--green); background: rgba(63,185,80,0.08); font-family: 'JetBrains Mono', monospace; }
  .pq-icon  { font-size: 0.8rem; margin-right: 2px; }

  .synthesis-block {
    background: var(--bg); border-left: 2px solid var(--gold);
    padding: 16px; border-radius: 0 8px 8px 0; font-size: 0.92rem; line-height: 1.7;
    margin-bottom: 14px;
  }
  .synthesis-block h1,.synthesis-block h2,.synthesis-block h3 { color: var(--gold); margin: 14px 0 6px; font-size: 1rem; }
  .synthesis-block p { margin-bottom: 10px; }
  .synthesis-block code { background: var(--surface2); padding: 2px 6px; border-radius: 4px; font-size: 0.83em; font-family: 'JetBrains Mono', monospace; }
  .synthesis-block pre { background: var(--surface2); padding: 12px; border-radius: 6px; overflow-x: auto; margin: 10px 0; }
  .synthesis-block table { border-collapse: collapse; width: 100%; margin: 10px 0; }
  .synthesis-block th,.synthesis-block td { border: 1px solid var(--border2); padding: 7px 12px; font-size: 0.85rem; }
  .synthesis-block th { background: var(--surface2); color: var(--gold); }
  .synthesis-block ul,.synthesis-block ol { padding-left: 20px; margin-bottom: 10px; }
  .synthesis-block blockquote { border-left: 2px solid var(--border2); margin: 0; padding-left: 14px; color: var(--muted2); }

  .feedback-row { display: flex; align-items: center; gap: 10px; margin-top: 14px; padding-top: 14px; border-top: 1px solid var(--border); }
  .feedback-label { font-size: 0.75rem; color: var(--muted); }

  /* SIDEBAR */
  .god-card-side {
    background: var(--bg); border: 1px solid var(--border2); border-radius: 8px;
    padding: 12px 14px; margin-bottom: 8px; transition: border-color .2s;
    border-left: 3px solid var(--god-color);
  }
  .god-card-side:hover { border-color: var(--god-color); }
  .god-side-header { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
  .god-side-symbol { font-size: 1rem; }
  .god-side-name { font-size: 0.82rem; font-weight: 600; color: var(--god-color); }
  .god-side-role { font-size: 0.68rem; color: var(--muted); margin-bottom: 8px; line-height: 1.4; }
  .rep-bar { background: var(--surface2); border-radius: 3px; height: 4px; overflow: hidden; margin-top: 2px; }
  .rep-fill { height: 100%; transition: width .6s cubic-bezier(.4,0,.2,1); border-radius: 3px; }
  .rep-label { display: flex; justify-content: space-between; font-size: 0.65rem; color: var(--muted); margin-bottom: 2px; }

  /* DECREE LIST */
  .decree-list { display: grid; gap: 6px; max-height: 360px; overflow-y: auto; }
  .decree-list::-webkit-scrollbar { width: 3px; }
  .decree-list::-webkit-scrollbar-thumb { background: var(--border2); border-radius: 2px; }
  .decree-item {
    background: var(--bg); border: 1px solid var(--border2); border-radius: 7px;
    padding: 10px 12px; cursor: pointer; transition: all .15s;
  }
  .decree-item:hover { border-color: rgba(230,201,122,0.3); background: var(--surface2); }
  .decree-q { font-size: 0.80rem; margin-bottom: 5px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; color: var(--text); }
  .decree-meta { font-size: 0.65rem; color: var(--muted); display: flex; gap: 6px; flex-wrap: wrap; }
  .decree-pq { color: var(--green); font-size: 0.65rem; }

  /* CHARTS */
  .charts-section { padding: 0 32px 32px; max-width: 1440px; }
  .charts-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }

  .loading { color: var(--muted); font-size: 0.82rem; padding: 8px 0; }
</style>
</head>
<body>
<header>
  <div class="header-left">
    <div class="logo">ENLIL</div>
    <div class="logo-sub">Consejo de los Dioses · Orquestador Multi-IA</div>
  </div>
  <div class="header-right">
    <div class="status-dot"></div>
    <span class="status-label">Sistema activo</span>
    <input id="clientApiKey" type="password" placeholder="Tu API key..." autocomplete="off"
      style="background:var(--surface2);border:1px solid var(--border2);color:var(--text);
             padding:5px 12px;font-size:0.75rem;border-radius:5px;font-family:monospace;
             width:230px;margin-left:14px;outline:none;"
      oninput="saveApiKey(this.value)">
  </div>
</header>

<div class="layout">
  <!-- MAIN COLUMN -->
  <div>
    <div class="card" style="margin-bottom:18px">
      <div class="card-title">Nueva consulta</div>
      <textarea id="queryInput" placeholder="Formula tu consulta al Consejo..."></textarea>
      <div class="controls">
        <select id="budgetTier">
          <option value="">Auto</option>
          <option value="minimal">Minimal · 2 dioses</option>
          <option value="standard">Standard · 4 dioses</option>
          <option value="full">Full · 9 dioses</option>
        </select>
        <button class="btn-invoke" id="invokeBtn" onclick="submitQuery()">⚡ Convocar el Consejo</button>
      </div>
    </div>

    <!-- COUNCIL DELIBERATION -->
    <div id="council" class="card" style="margin-bottom:18px">
      <div class="council-title">
        <span id="councilStatus">Convocando el Consejo...</span>
      </div>
      <div class="council-grid" id="councilGrid"></div>
    </div>

    <!-- DECREE RESULT -->
    <div id="result" class="card">
      <div class="card-title">Decreto emitido</div>
      <div class="decree-header">
        <div class="decree-badges" id="resultMeta"></div>
      </div>
      <div class="synthesis-block" id="resultSynthesis"></div>
      <div class="feedback-row">
        <span class="feedback-label">¿Fue útil este decreto?</span>
        <button class="btn-sm btn-yes" onclick="sendFeedback(true)">Sí</button>
        <button class="btn-sm btn-no" onclick="sendFeedback(false)">No</button>
        <a id="pdfDownloadBtn" class="btn-sm btn-pdf" href="#" target="_blank" style="display:none">&#x2B07; Descargar Decreto PDF</a>
      </div>
    </div>
  </div>

  <!-- SIDEBAR -->
  <div>
    <div class="card" style="margin-bottom:18px">
      <div class="card-title">Panteón</div>
      <div id="pantheonList"><div class="loading">Cargando...</div></div>
    </div>
    <div class="card">
      <div class="card-title">Últimos Decretos</div>
      <div id="decreeList" class="decree-list"><div class="loading">Cargando...</div></div>
    </div>
  </div>
</div>

<!-- CHARTS -->
<div class="charts-section">
  <div class="charts-grid">
    <div class="card"><div class="card-title">Tendencia de Tokens</div><canvas id="tokenChart" height="200"></canvas></div>
    <div class="card"><div class="card-title">Latencia por Dios (ms)</div><canvas id="latencyChart" height="200"></canvas></div>
    <div class="card"><div class="card-title">Dominios más Activos</div><canvas id="domainChart" height="200"></canvas></div>
    <div class="card"><div class="card-title">Evolución de Reputación</div><canvas id="reputationChart" height="200"></canvas></div>
  </div>
</div>

<script>
const GOD_META = {
  'claude':  { symbol: '⚡', color: '#e6c97a', rgb: '230,201,122', role: 'Estrategia y Contexto',      model: 'claude-sonnet-5' },
  'enki':    { symbol: '🌊', color: '#4fc3f7', rgb: '79,195,247',  role: 'Análisis Técnico',            model: 'deepseek-v4-pro' },
  'ninurta': { symbol: '🔥', color: '#ef5350', rgb: '239,83,80',   role: 'Seguridad y Defensa',         model: 'nemotron-253b' },
  'inanna':  { symbol: '🌙', color: '#ce93d8', rgb: '206,147,216', role: 'Comunicación y Ventas',       model: 'mistral-large-2512' },
  'anu':     { symbol: '✨', color: '#26c6da', rgb: '38,198,218',  role: 'Meta y Orquestación',         model: 'gemini-3.1-pro' },
  'marduk':  { symbol: '⚖️', color: '#ff8f00', rgb: '255,143,0',   role: 'Juicio Supremo (solo Full)',  model: 'claude-opus-4-8' },
  'nabu':    { symbol: '📿', color: '#26a69a', rgb: '38,166,154',  role: 'Razonamiento y Lógica',       model: 'deepseek-r1' },
  'nergal':  { symbol: '⚔️', color: '#d32f2f', rgb: '211,47,47',   role: 'Red Team Adversarial',        model: 'grok-4.3' },
  'tiamat':  { symbol: '🌀', color: '#9c27b0', rgb: '156,39,176',  role: 'Creatividad y Multimodal',    model: 'llama-4-maverick' },
};
const GOD_COLORS = {
  'Claude': '#e6c97a', 'Enki': '#4fc3f7', 'Ninurta': '#ef5350', 'Inanna': '#ce93d8',
  'Anu': '#26c6da', 'Marduk': '#ff8f00', 'Nabu': '#26a69a', 'Nergal': '#d32f2f', 'Tiamat': '#9c27b0',
};

let currentDecreeId = null;

function godKey(name) { return name.toLowerCase(); }

function buildCouncilCards(gods) {
  const grid = document.getElementById('councilGrid');
  grid.innerHTML = gods.map(name => {
    const k = godKey(name);
    const m = GOD_META[k] || { symbol: '✦', color: '#8b949e', rgb: '139,148,158', role: name, model: '' };
    return `
      <div class="god-panel active" id="gp-${k}"
           style="--god-color:${m.color};--god-rgb:${m.rgb}">
        <div class="god-header">
          <div class="god-symbol">${m.symbol}</div>
          <div class="god-info">
            <div class="god-name-label">${name}</div>
            <div class="god-model">${m.model}</div>
          </div>
          <div class="god-status">
            <span class="god-status-badge thinking" id="badge-${k}">Deliberando...</span>
          </div>
        </div>
        <div class="god-metrics" id="metrics-${k}" style="display:none"></div>
        <div class="shimmer" id="shimmer-${k}1"></div>
        <div class="shimmer" id="shimmer-${k}2" style="width:75%"></div>
        <div class="shimmer" id="shimmer-${k}3" style="width:55%"></div>
        <div class="god-response" id="resp-${k}"></div>
        <div class="god-dissent" id="dissent-${k}"></div>
      </div>`;
  }).join('');
}

function typewriter(el, text, speed, onDone) {
  el.classList.add('visible');
  const delay = text.length > 300 ? 4 : text.length > 100 ? 8 : 14;
  let i = 0;
  function tick() {
    el.textContent = text.slice(0, i);
    i++;
    if (i <= text.length) setTimeout(tick, delay);
    else {
      el.innerHTML = text.replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/\n/g,'<br>');
      if (onDone) onDone();
    }
  }
  tick();
}

function revealGod(voice, onDone) {
  const k = godKey(voice.god);
  const badge = document.getElementById(`badge-${k}`);
  const metrics = document.getElementById(`metrics-${k}`);
  const respEl = document.getElementById(`resp-${k}`);
  const dissentEl = document.getElementById(`dissent-${k}`);

  [1,2,3].forEach(i => {
    const s = document.getElementById(`shimmer-${k}${i}`);
    if (s) s.style.display = 'none';
  });

  if (badge) {
    if (voice.dissent === 'error') {
      badge.textContent = '⚠ Error';
      badge.style.background = 'rgba(218,54,51,0.12)';
      badge.style.color = '#ef5350';
      badge.style.borderColor = 'rgba(218,54,51,0.3)';
      badge.classList.remove('thinking');
    } else {
      badge.textContent = 'Respondido';
      badge.classList.remove('thinking');
    }
  }
  if (metrics) {
    metrics.textContent = `${voice.tokens} tokens · ${voice.latency_ms} ms`;
    metrics.style.display = 'block';
    metrics.style.marginBottom = '8px';
  }
  if (voice.dissent && voice.dissent !== 'error' && dissentEl) {
    dissentEl.textContent = `Disidencia: ${voice.dissent}`;
    dissentEl.classList.add('visible');
  }
  if (voice.content && respEl) {
    typewriter(respEl, voice.content, 0, onDone);
  } else if (onDone) {
    onDone();
  }
}

async function submitQuery() {
  const query = document.getElementById('queryInput').value.trim();
  if (!query) return;
  const tier = document.getElementById('budgetTier').value || null;
  const btn = document.getElementById('invokeBtn');
  btn.disabled = true;
  btn.textContent = 'Convocando...';

  document.getElementById('result').style.display = 'none';

  const councilEl = document.getElementById('council');
  councilEl.style.display = 'block';
  councilEl.scrollIntoView({behavior:'smooth', block:'start'});

  let elapsed = 0;
  const timer = setInterval(() => {
    elapsed++;
    document.getElementById('councilStatus').textContent = `El Consejo delibera... ${elapsed}s`;
  }, 1000);

  try {

  const allGods = ['Claude','Enki','Ninurta','Inanna','Anu','Marduk','Nabu','Nergal','Tiamat'];
  buildCouncilCards(allGods);

  if (!CLIENT_KEY) {
    clearInterval(timer);
    document.getElementById('councilStatus').textContent = '⚠ Introduce tu API key en la parte superior derecha';
    btn.disabled = false;
    btn.textContent = '⚡ Convocar el Consejo';
    return;
  }
  const resp = await fetch('/query', {
    method: 'POST',
    headers: {'Content-Type': 'application/json', 'X-Api-Key': CLIENT_KEY},
    body: JSON.stringify({query, budget_tier: tier})
  });
  const d = await resp.json();
  currentDecreeId = d.decree_id;

  const convened = new Set(d.gods_convened.map(g => g.toLowerCase()));
  allGods.forEach(name => {
    if (!convened.has(name.toLowerCase())) {
      const panel = document.getElementById(`gp-${name.toLowerCase()}`);
      if (panel) {
        panel.style.opacity = '0.35';
        panel.classList.remove('active');
        const badge = document.getElementById(`badge-${name.toLowerCase()}`);
        if (badge) { badge.textContent = 'No convocado'; badge.classList.remove('thinking'); badge.classList.add('idle'); }
        [1,2,3].forEach(i => { const s = document.getElementById(`shimmer-${name.toLowerCase()}${i}`); if (s) s.style.display='none'; });
      }
    }
  });

  document.getElementById('councilStatus').textContent = 'Voces recibidas — revelando respuestas';

  function revealSequential(voices, idx, onAllDone) {
    if (idx >= voices.length) { onAllDone(); return; }
    revealGod(voices[idx], () => revealSequential(voices, idx + 1, onAllDone));
  }

  revealSequential(d.voices, 0, () => {
      clearInterval(timer);
      document.getElementById('councilStatus').textContent = `Decreto emitido ✓ · ${elapsed}s`;
      showResult(d);
      btn.disabled = false;
      btn.textContent = '⚡ Convocar el Consejo';
      loadHistory();
    });
  } catch(e) {
    clearInterval(timer);
    document.getElementById('councilStatus').textContent = '⚠ Error al contactar el Consejo';
    btn.disabled = false;
    btn.textContent = '⚡ Convocar el Consejo';
    console.error(e);
  }
}

function showResult(d) {
  const resultEl = document.getElementById('result');
  resultEl.style.display = 'block';
  const pdfBtn = document.getElementById('pdfDownloadBtn');
  if (pdfBtn && d.decree_id) {
    pdfBtn.href = `/decree/${d.decree_id}/export`;
    pdfBtn.style.display = 'inline-flex';
  }
  const pqBadge = d.pq_signed
    ? `<span class="tag pq"><span class="pq-icon">🔐</span>ML-DSA-87 firmado</span>`
    : '';
  document.getElementById('resultMeta').innerHTML = `
    <span class="tag gold">Decreto ${d.decree_id.slice(0,8)}</span>
    ${d.domains.map(x => `<span class="tag">${x}</span>`).join('')}
    <span class="tag">${d.budget_tier}</span>
    <span class="tag">${d.total_tokens} tokens</span>
    ${d.has_dissent ? '<span class="tag red">⚠ Disidencia</span>' : ''}
    ${pqBadge}
  `;
  document.getElementById('resultSynthesis').innerHTML = typeof marked !== 'undefined'
    ? marked.parse(d.synthesis) : d.synthesis.replace(/\n/g,'<br>');
  resultEl.scrollIntoView({behavior:'smooth', block:'start'});
}

async function sendFeedback(useful) {
  if (!currentDecreeId) return;
  await fetch(`/feedback/${currentDecreeId}`, {
    method: 'POST', headers: {'Content-Type':'application/json'},
    body: JSON.stringify({useful})
  });
  loadPantheon();
}

async function loadPantheon() {
  const resp = await fetch('/pantheon');
  const gods = await resp.json();
  document.getElementById('pantheonList').innerHTML = gods.map(g => {
    const k = g.name ? g.name.toLowerCase() : (g.display_name || '').toLowerCase();
    const m = GOD_META[k] || { symbol: '✦', color: '#8b949e', rgb: '139,148,158', role: g.role || '', model: '' };
    const repEntries = Object.entries(g.reputation || {});
    const repHtml = repEntries.length
      ? repEntries.slice(0,2).map(([dom, v]) => `
          <div class="rep-label"><span>${dom}</span><span>${(v.score*100).toFixed(0)}%</span></div>
          <div class="rep-bar"><div class="rep-fill" style="width:${v.score*100}%;background:${m.color}"></div></div>
        `).join('')
      : `<div style="font-size:0.68rem;color:var(--muted)">Sin evaluaciones aún</div>`;
    return `
      <div class="god-card-side" style="--god-color:${m.color}">
        <div class="god-side-header">
          <span class="god-side-symbol">${m.symbol}</span>
          <span class="god-side-name">${g.display_name}</span>
        </div>
        <div class="god-side-role">${m.role}</div>
        ${repHtml}
      </div>`;
  }).join('');
}

async function loadHistory() {
  const resp = await fetch('/history?limit=15');
  const decrees = await resp.json();
  document.getElementById('decreeList').innerHTML = decrees.length
    ? decrees.map(d => `
      <div class="decree-item" onclick="loadDecree('${d.id}')">
        <div class="decree-q">${d.query.replace(/</g,'&lt;')}</div>
        <div class="decree-meta">
          <span>${d.gods_convened.join(', ')}</span>
          <span>${d.total_tokens}t</span>
          <span>${d.budget_tier}</span>
          ${d.has_dissent ? '<span style="color:var(--red)">⚠ disidencia</span>' : ''}
        </div>
      </div>`).join('')
    : '<div class="loading">Sin decretos aún</div>';
}

async function loadDecree(id) {
  const resp = await fetch(`/decree/${id}`);
  const d = await resp.json();
  currentDecreeId = d.id;
  document.getElementById('queryInput').value = d.query;
  document.getElementById('council').style.display = 'none';
  showResult({
    decree_id: d.id, domains: d.domains, budget_tier: d.budget_tier,
    total_tokens: d.total_tokens, has_dissent: d.has_dissent,
    synthesis: d.synthesis, pq_signed: d.pq_signed, voices: d.voices || [],
  });
}

document.getElementById('queryInput').addEventListener('keydown', e => {
  if (e.ctrlKey && e.key === 'Enter') submitQuery();
});

let CLIENT_KEY = localStorage.getItem("enlil_api_key") || "";
(function(){ const ki = document.getElementById("clientApiKey"); if(ki && CLIENT_KEY) ki.value = CLIENT_KEY; })();
function saveApiKey(v){ CLIENT_KEY = v.trim(); localStorage.setItem("enlil_api_key", v.trim()); }

loadPantheon();
loadHistory();

let tokenChart=null, latencyChart=null, domainChart=null, repChart=null;

async function loadCharts() {
  try {
    const resp = await fetch('/stats');
    if (!resp.ok) return;
    const data = await resp.json();
    const chartOpts = {
      responsive:true,
      plugins:{legend:{labels:{color:'#6b7486',font:{size:11}}}},
      scales:{
        x:{ticks:{color:'#6b7486',font:{size:10}},grid:{color:'#1e2330'}},
        y:{ticks:{color:'#6b7486',font:{size:10}},grid:{color:'#1e2330'}}
      }
    };

    const tokenData = data.token_trend.slice().reverse();
    const tctx = document.getElementById('tokenChart').getContext('2d');
    if (tokenChart) tokenChart.destroy();
    tokenChart = new Chart(tctx, {
      type:'line',
      data:{
        labels: tokenData.map((_,i)=>`#${i+1}`),
        datasets:[{label:'Tokens',data:tokenData.map(d=>d.tokens),
          borderColor:'#e6c97a',backgroundColor:'rgba(230,201,122,0.08)',
          tension:0.4,fill:true,pointRadius:2}]
      },
      options: chartOpts
    });

    const gods = Object.keys(data.latency_avg);
    const lctx = document.getElementById('latencyChart').getContext('2d');
    if (latencyChart) latencyChart.destroy();
    latencyChart = new Chart(lctx, {
      type:'bar',
      data:{
        labels:gods,
        datasets:[{label:'ms',data:gods.map(g=>data.latency_avg[g]),
          backgroundColor:gods.map(g=>GOD_COLORS[g]||'#6b7486'),
          borderRadius:4}]
      },
      options: chartOpts
    });

    const domains = Object.keys(data.domain_distribution);
    const dctx = document.getElementById('domainChart').getContext('2d');
    if (domainChart) domainChart.destroy();
    domainChart = new Chart(dctx, {
      type:'doughnut',
      data:{
        labels:domains,
        datasets:[{data:domains.map(d=>data.domain_distribution[d]),
          backgroundColor:['#e6c97a','#4fc3f7','#ef5350','#ce93d8','#81c784','#ffb74d'],
          borderWidth:0}]
      },
      options:{responsive:true,plugins:{legend:{position:'right',labels:{color:'#6b7486',font:{size:11},boxWidth:10}}}}
    });

    const byGod = {};
    data.reputation_history.slice().reverse().forEach(r=>{
      if(!byGod[r.god_name]) byGod[r.god_name]=[];
      byGod[r.god_name].push(r.score);
    });
    const maxLen = Math.max(...Object.values(byGod).map(a=>a.length),1);
    const rctx = document.getElementById('reputationChart').getContext('2d');
    if (repChart) repChart.destroy();
    repChart = new Chart(rctx, {
      type:'line',
      data:{
        labels:Array.from({length:maxLen},(_,i)=>`${i+1}`),
        datasets:Object.entries(byGod).map(([god,scores])=>({
          label:god,data:scores,borderColor:GOD_COLORS[god]||'#6b7486',
          backgroundColor:'transparent',tension:0.4,pointRadius:2
        }))
      },
      options:{...chartOpts,scales:{...chartOpts.scales,y:{...chartOpts.scales.y,min:0,max:1}}}
    });
  } catch(e) { console.warn('Charts error:', e); }
}

loadCharts();
const _origLoad = loadHistory;
loadHistory = async function() { await _origLoad(); loadCharts(); };
</script>
</body>
</html>"""
