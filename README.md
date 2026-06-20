# ENLIL — El Consejo de los Dioses

9 modelos de IA deliberando en paralelo. Cada decision firmada con criptografia post-cuantica.

**Live dashboard (decretos reales en produccion):** https://enlil-council.com/dashboard

ENLIL convoca un consejo de 9 modelos especializados (Claude, DeepSeek, Gemini, Mistral, Qwen, Llama, Grok) para analizar cualquier consulta desde angulos complementarios: tecnico, legal, estrategico, adversarial, creativo. El resultado es un Decreto: un documento estructurado con el razonamiento de cada dios, una sintesis final y una firma ML-DSA-87 irrevocable.

---

## El Consejo

| Dios     | Modelo            | Especialidad                            |
|----------|-------------------|-----------------------------------------|
| Claude   | Claude Sonnet 4.6 | Contexto, alineacion, coherencia        |
| Enki     | DeepSeek v3       | Analisis tecnico, codigo, arquitectura  |
| Ninurta  | Qwen 235B         | Auditoria, inspeccion adversarial       |
| Inanna   | Mistral Large     | Comunicacion, decision, accion          |
| Anu      | Gemini 2.5 Pro    | Meta-razonamiento, patrones sistemicos  |
| Marduk   | Claude Opus 4     | Juicio final -- tier completo           |
| Nabu     | DeepSeek R1       | Logica formal, verificacion             |
| Nergal   | Grok              | Red team, abogado del diablo            |
| Tiamat   | Llama 4 Maverick  | Creatividad disruptiva, oportunidades   |

---

## Por que es diferente

- **Firma ML-DSA-87 (NIST FIPS 204)**: cada Decreto lleva una firma post-cuantica irrevocable. Cualquier modificacion posterior invalida la firma. Funciona como prueba de diligencia ante auditorias, reguladores o jueces.
- **Disidencias capturadas**: si un dios discrepa del consenso, queda registrado en el Decreto.
- **Aprendizaje por reputacion**: el sistema rastrea que dioses aciertan en que tipo de consultas y ajusta el enrutamiento con el tiempo.
- **Self-hosted, BYOK**: tu controlas tus datos y usas tu propia API key de OpenRouter. Cero costes fijos para el operador.

---

## Requisitos

- Docker y Docker Compose
- Una cuenta en https://openrouter.ai (BYOK -- Bring Your Own Key)
- 2 GB RAM minimo (4 GB recomendado)

---

## Inicio rapido

```bash
git clone https://github.com/conchaestradamiguelangel-droid/enlil.git
cd enlil
cp .env.example .env
# Edita .env: anade tu OPENROUTER_API_KEY y una ENLIL_MASTER_KEY segura
docker-compose up -d
```

El Consejo arranca en http://localhost:8002.

### Crear tu primer cliente

```bash
curl -X POST http://localhost:8002/admin/clients \
  -H "X-Master-Key: TU_ENLIL_MASTER_KEY" \
  -H "Content-Type: application/json" \
  -d '{"name":"yo","email":"tu@email.com","plan":"standard"}'
```

### Lanzar un Decreto

```bash
curl -X POST http://localhost:8002/query \
  -H "X-Api-Key: enlil_TU_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"query":"Riesgos de adoptar IA generativa con datos sensibles"}'
```

---

## Estructura del proyecto

```
enlil/
├── docker-compose.yml     # Enlil + Qdrant
├── Dockerfile
├── .env.example
├── requirements.txt
├── main.py
├── api.py
└── enlil/
   ├── auth.py             # Autenticacion, rate limiting, uso
   ├── council.py          # Motor de deliberacion paralela
   ├── orchestrator.py     # Orquestacion: classify, route, sign, store
   ├── quantum.py          # Firma ML-DSA-87 (liboqs)
   ├── export.py           # Exportacion a PDF/HTML
   ├── document_rag.py     # RAG para documentos largos
   └── gods/
      ├── registry.py      # Los 9 dioses y sus perfiles
      └── base.py          # Tipos base
```

---

## Endpoints principales

| Metodo | Endpoint           | Auth       | Descripcion               |
|--------|--------------------|------------|---------------------------|
| POST   | /query             | API Key    | Lanzar un Decreto         |
| GET    | /history           | API Key    | Historial de Decretos     |
| GET    | /decree/{id}       | --         | Ver un Decreto publico    |
| GET    | /decree/{id}/pdf   | --         | Exportar Decreto a PDF    |
| GET    | /health            | --         | Estado del sistema        |
| POST   | /admin/clients     | Master Key | Crear cliente             |
| GET    | /admin/clients     | Master Key | Listar clientes           |
| GET    | /admin/usage       | Master Key | Uso y estadisticas        |

---

## Verificacion de firma

Cada Decreto incluye una firma ML-DSA-87 en base64. La clave publica esta disponible en GET /public-key.

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

## Licencia

GPL v3. Quien modifique y distribuya ENLIL debe publicar el codigo fuente.
Ver LICENSE.

---

## Construido con

- FastAPI -- https://fastapi.tiangolo.com
- OpenRouter -- https://openrouter.ai
- liboqs (ML-DSA-87 / NIST FIPS 204) -- https://github.com/open-quantum-safe/liboqs
- Qdrant -- https://qdrant.tech
- SQLite -- https://sqlite.org

---

## Companion Project: AEGIS

ENLIL deliberates. **AEGIS defends.**

[AEGIS](https://github.com/conchaestradamiguelangel-droid/aegis) is an autonomous 9-layer post-quantum cyber-defense system. When AEGIS detects a threat, ENLIL provides the strategic judgment -- documented, signed, auditable. Together they form a full autonomous security intelligence stack.

- Autonomous threat detection and response
- ML-KEM-1024, ML-DSA-87, SPHINCS+ (NIST FIPS 203/204/205)
- GPL v3 -- same license as ENLIL
- Live: https://aegis-pq.com
