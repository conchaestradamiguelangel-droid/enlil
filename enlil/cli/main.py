"""
ENLIL CLI -- El Consejo de los Dioses desde la terminal.

Uso rapido:
    enlil "tu consulta aqui"

Comandos:
    enlil init                    Configurar servidor y API key
    enlil "consulta"              Convocar al Consejo (atajo directo)
    enlil query "consulta"        Idem (forma explicita)
    enlil history [-n N]          Ultimos N decretos (default: 10)
    enlil decree <id>             Ver un decreto especifico
    enlil status                  Estado del servidor y panteon
"""
import argparse
import sys

from enlil.cli import config, client, render
from enlil.gods.registry import build_default_pantheon


def cmd_init(_args):
    print()
    print("  ENLIL CLI -- Configuracion inicial")
    print()
    url = input("  URL del servidor ENLIL [http://localhost:8002]: ").strip()
    if not url:
        url = "http://localhost:8002"
    api_key = input("  API Key (enlil_...): ").strip()
    if not api_key:
        render.err("API key requerida.")
        sys.exit(1)
    print()
    print("  Verificando conexion...", end="", flush=True)
    if client.health(url):
        print(" OK")
    else:
        print(" sin respuesta (guardando configuracion de todos modos)")
    config.save(url, api_key)
    print(f"  Configuracion guardada en: {config.CONFIG_FILE}")
    print()
    print('  Listo. Prueba: enlil "tu primera consulta"')
    print()


def cmd_query(args):
    cfg  = config.require()
    text = " ".join(args.query).strip()
    if not text:
        render.err("Consulta vacia.")
        sys.exit(1)
    in_synthesis = False
    try:
        peer_review = getattr(args, "review", False)
        for event in client.query_stream(cfg["url"], cfg["api_key"], text, getattr(args, "tier", None), peer_review=peer_review):
            etype = event.get("type")
            if etype == "init":
                render.council_init(event["gods"], event["domains"], event["budget_tier"])
            elif etype == "god":
                render.god_done(
                    event["god"], event["latency_ms"],
                    event["tokens"], event.get("dissent", False),
                )
            elif etype == "synthesis_token":
                if not in_synthesis:
                    render.synthesis_start()
                    in_synthesis = True
                render.synthesis_chunk(event["token"])
            elif etype == "peer_review_init":
                render.peer_review_init(event["reviewers"])
            elif etype == "peer_critique":
                render.peer_critique(event["god"], event["content"], event["latency_ms"])
            elif etype == "done":
                render.decree_footer(event)
            elif etype == "error":
                render.err(event.get("message", "Error desconocido del servidor"))
                sys.exit(1)
    except KeyboardInterrupt:
        print()
        sys.exit(0)
    except Exception as e:
        render.err(str(e))
        sys.exit(1)


def cmd_history(args):
    cfg = config.require()
    try:
        decrees = client.history(cfg["url"], cfg["api_key"], args.n)
        render.history_table(decrees)
    except Exception as e:
        render.err(str(e))
        sys.exit(1)


def cmd_decree(args):
    cfg = config.require()
    try:
        d = client.get_decree(cfg["url"], cfg["api_key"], args.id)
        render.single_decree(d)
    except Exception as e:
        render.err(str(e))
        sys.exit(1)


def cmd_status(args):
    cfg = config.require()
    try:
        s = client.server_status(cfg["url"], cfg["api_key"])
        print()
        print(f"  Servidor  : {cfg['url']}")
        print(f"  Modo      : {s.get('council_mode', '?')}")
        print(f"  Memoria   : {s.get('memory_backend', '?')}")
        print(f"  OpenRouter: {'configurado' if s.get('openrouter_key_set') else 'NO configurado'}")
        print()
        print("  Panteon:")
        for god, model in s.get("gods_models", {}).items():
            print(f"    {god:<14}  {model}")
        print()
    except Exception as e:
        render.err(str(e))
        sys.exit(1)


def cmd_gods(_args):
    pantheon = build_default_pantheon()

    print()
    print(f"{'God':<10} {'Model':<40} Domain")
    print("-" * 90)

    for god in pantheon.values():
        domain = ", ".join(god.domains[:3])
        print(
            f"{god.name:<10} "
            f"{god.model:<40} "
            f"{domain}"
        )

    print()

def main():
    # Atajo: si el primer arg no es un subcomando conocido, es una consulta directa
    _known = {"init", "query", "history", "decree", "status", "gods", "-h", "--help", "--version"}
    argv = sys.argv[1:]
    if argv and argv[0] not in _known:
        argv = ["query"] + argv

    parser = argparse.ArgumentParser(
        prog="enlil",
        description="ENLIL -- El Consejo de los Dioses",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--version", action="version", version="enlil 1.0.0")
    sub = parser.add_subparsers(dest="cmd")

    sub.add_parser("init", help="Configurar servidor y API key")

    p_q = sub.add_parser("query", help="Consultar al Consejo")
    p_q.add_argument("query", nargs="+", help="Texto de la consulta")
    p_q.add_argument("--tier", default=None, choices=["light", "standard", "full"],
                     help="Tier de presupuesto (tokens)")
    p_q.add_argument("--review", action="store_true", default=False,
                     help="Activar revision de pares: cada dios critica las voces del resto")

    p_h = sub.add_parser("history", help="Ultimos decretos")
    p_h.add_argument("-n", type=int, default=10, metavar="N",
                     help="Numero de decretos a mostrar (default: 10)")

    p_d = sub.add_parser("decree", help="Ver un decreto especifico")
    p_d.add_argument("id", help="ID del decreto")

    sub.add_parser("status", help="Estado del servidor y panteon activo")
    
    sub.add_parser(
    "gods",
    help="List available gods and their models"
    )

    args = parser.parse_args(argv)

    dispatch = {
        "init":    cmd_init,
        "query":   cmd_query,
        "history": cmd_history,
        "decree":  cmd_decree,
        "status":  cmd_status,
        "gods":    cmd_gods,
    }
    fn = dispatch.get(args.cmd)
    if fn:
        fn(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
