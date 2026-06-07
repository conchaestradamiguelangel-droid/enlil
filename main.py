import asyncio
import os
from dotenv import load_dotenv
from enlil import Orchestrator

load_dotenv()


async def main():
    enlil = Orchestrator()

    print("ENLIL v0.1 — Orquestador Multi-IA")
    print("=" * 50)
    print("Escribe tu consulta (o 'salir' para terminar):\n")

    while True:
        query = input(">> ").strip()
        if query.lower() in ("salir", "exit", "quit"):
            break
        if not query:
            continue

        print("\n[Convocando el Consejo...]\n")
        decree = await enlil.query(query)

        print(f"DECRETO [{decree.id[:8]}]")
        print(f"Dominios: {', '.join(decree.domains)}")
        print(f"Dioses convocados: {', '.join(decree.gods_convened)}")
        print(f"Tokens totales: {decree.total_tokens}")
        if decree.has_dissent():
            print(f"⚠ Disidencia registrada: {', '.join(decree.dissenting_gods())}")
        print(f"\n{decree.synthesis}\n")
        print("=" * 50)


if __name__ == "__main__":
    asyncio.run(main())
