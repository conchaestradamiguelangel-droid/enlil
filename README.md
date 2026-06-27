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
| Nergal   | Grok (ZDR)        | Red team, abogado del diablo            |
| Tiamat   | Llama 4 Maverick  | Creatividad disruptiva, oportunidades   |

---

## Por que es diferente

- **Firma ML-DSA-87 (NIST FIPS 204)**: cada Decreto lleva una firma post-cuantica irrevocable. Cualquier modificacion posterior invalida la firma. Funciona como prueba de diligencia ante auditorias, reguladores o jueces.
- **Disidencias capturadas**: si un dios discrepa del consenso, queda registrado en el Decreto.
- **Aprendizaje por reputacion**: el sistema rastrea que dioses aciertan en que tipo de consultas y ajusta el enrutamiento con el tiempo.
- **Self-hosted, BYOK**: tu controlas tus datos y usas tu propia API key de OpenRouter. Cero costes fijos para el operador.
- **Zero Data Retention en red team**: Nergal (Grok) opera con ZDR en OpenRouter. Las consultas adversariales no se almacenan ni se usan para entrenamiento.
- **Peer review entre dioses**: con `enlil --review`, cada dios critica las respuestas del resto antes de la sintesis final. Los Decretos descartan afirmaciones sin metodologia que en modo estandar pasarian al consenso.

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

### CLI -- de cero a primer Decreto en 30 segundos

Instala el CLI una vez tras clonar el repo:

```bash
pip install -e .
```

Luego configura y consulta:

```bash
enlil init                                     # URL + API key (una vez)
enlil "Riesgos de adoptar IA con datos sensibles"     # Decreto estandar
enlil --review "GPT-5 puede reemplazar un antivirus"  # Peer review activado
```

Mas comandos:

```bash
enlil history          # ultimos 10 decretos
enlil history -n 20    # ultimos 20
enlil decree <id>      # ver decreto especifico
enlil status           # panteon y modelos activos
```

### Lanzar un Decreto via API (alternativa curl)

```bash
curl -X POST http://localhost:8002/query \
  -H "X-Api-Key: enlil_TU_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"query":"Riesgos de adoptar IA generativa con datos sensibles"}'
```

---


---

## Peer Review -- cada dios critica al resto

`enlil --review` activa una segunda ronda antes de la sintesis: cada dios lee las
respuestas de todos los demas en forma anonima ("Respuesta 1", "Respuesta 2"...) y
emite una critica de 3-5 frases desde su dominio especifico.

| Dios | Rol en la revision |
|------|--------------------|
| Claude | Coherencia y completitud de contexto |
| Nergal | Red team -- busca el fallo que nadie quiere nombrar |
| Ninurta | Precision tecnica contra fuentes verificables |
| Tiamat | Oportunidades que el analisis convencional cierra |
| Enki | Validez de la arquitectura tecnica propuesta |

La sintesis final incorpora tanto las respuestas originales como las criticas.

**Ejemplo real (benchmark v1, pregunta R3):**

> *"GPT-5 tiene una tasa de error del 0.001% en deteccion de malware segun benchmarks
> internos del fabricante. Es suficiente para reemplazar el antivirus tradicional?"*

Sin `--review`: el Decreto critica el dato pero no lo descarta explicitamente.
Con `--review`: Tiamat marca *"0.001% es una cifra de marketing, no una metrica de
seguridad operacional -- benchmarks del propio fabricante no son auditoria independiente"*.
La sintesis final descarta la premisa antes de responder la pregunta.

```bash
enlil --review "GPT-5 puede reemplazar un antivirus"
```

---

## Benchmark -- modo estandar vs. peer review

10 preguntas (4 seguridad · 3 razonamiento con trampa · 3 compliance).
Cada una lanzada dos veces: modo rapido y con `--review`.

| Categoria | Sin review | Con review | Modifico? |
|-----------|-----------|------------|-----------|
| Seguridad (S1-S4) | Sintesis correcta | Sintesis mas precisa | 4/4 **Si** |
| Razonamiento con trampa (R1-R3) | Critica la premisa | Descarta afirmaciones sin fuente | 1 Si · 2 Parcial |
| Compliance (P1-P3) | Respuesta correcta | Contexto adicional aportado | 3/3 Parcial |
| **Total** | -- | -- | **6 Si · 4 Parcial · 0 No** |

**0 casos donde el peer review no aporto nada.**

Resultados completos y script reproducible: [`benchmarks/results_v1.md`](benchmarks/results_v1.md)

```bash
python3 enlil-bench.py   # Reproduce el benchmark contra tu servidor
```

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
