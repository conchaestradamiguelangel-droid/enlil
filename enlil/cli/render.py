"""Renderizado en terminal para el CLI de ENLIL."""
import sys


def _w(text=""):
    print(text, flush=True)


def _bar(char="-", width=62):
    return char * width


def council_init(gods: list, domains: list, budget: str) -> None:
    _w()
    _w(f"  Convocando consejo...")
    _w(f"  Dominios : {', '.join(domains) if domains else 'general'}")
    _w(f"  Dioses   : {', '.join(gods)} ({len(gods)})")
    _w(f"  Tier     : {budget}")
    _w()


def god_done(god: str, latency_ms: float, tokens: int, dissent: bool) -> None:
    flag = "  [DISIENTE]" if dissent else ""
    _w(f"  [{god:<12}]  listo ({latency_ms / 1000:.1f}s, {tokens} tokens){flag}")


def synthesis_start() -> None:
    _w()
    _w(_bar("="))
    _w("  DECRETO")
    _w(_bar("="))
    _w()


def synthesis_chunk(text: str) -> None:
    print(text, end="", flush=True)


def decree_footer(data: dict) -> None:
    _w()
    _w()
    _w(_bar("-"))
    tokens     = data.get("total_tokens", 0)
    gods       = ", ".join(data.get("gods_convened", []))
    signed     = "ML-DSA-87" if data.get("pq_signed") else "no firmado"
    dissent    = "  | DISIDENCIA" if data.get("has_dissent") else ""
    _w(f"  Tokens: {tokens:,}  |  Firmado: {signed}{dissent}")
    _w(f"  ID    : {data.get('decree_id', '')}  |  Tier: {data.get('budget_tier', '')}")
    _w(f"  Dioses: {gods}")
    _w(_bar("-"))
    _w()


def history_table(decrees: list) -> None:
    if not decrees:
        _w("  No hay decretos.")
        return
    _w()
    _w(f"  {'ID':<30}  {'Dominios':<22}  {'Tokens':>7}  {'Dioses':>6}")
    _w(_bar())
    for d in decrees:
        did     = (d.get("id") or d.get("decree_id", ""))[:28]
        domains = ", ".join(d.get("domains", []))[:20]
        tokens  = d.get("total_tokens", 0)
        gods    = len(d.get("gods_convened", []))
        _w(f"  {did:<30}  {domains:<22}  {tokens:>7,}  {gods:>6}")
    _w(_bar())
    _w()


def single_decree(d: dict) -> None:
    _w()
    _w(_bar("="))
    _w(f"  DECRETO  {d.get('id') or d.get('decree_id', '')}")
    _w(_bar("="))
    _w(f"  Consulta : {d.get('query', '')}")
    _w(f"  Dominios : {', '.join(d.get('domains', []))}")
    _w(f"  Dioses   : {', '.join(d.get('gods_convened', []))}")
    _w()
    for v in d.get("voices", []):
        _w(f"  [{v.get('god', '?')}]")
        body = v.get("content", "")
        _w(f"  {body[:600]}{'...' if len(body) > 600 else ''}")
        _w()
    _w(_bar("-"))
    _w("  SINTESIS")
    _w(_bar("-"))
    _w(d.get("synthesis", ""))
    _w(_bar("="))
    _w()


def err(msg: str) -> None:
    print(f"  Error: {msg}", file=sys.stderr)
