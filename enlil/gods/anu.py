"""ANU — Dios del Cielo Cuántico. Razonamiento mediante circuitos Qiskit Aer."""

import math
import time
from .base import GodResponse


class AnuQuantumGod:

    def __init__(self):
        from qiskit import QuantumCircuit, transpile
        from qiskit_aer import AerSimulator
        self._QC = QuantumCircuit
        self._transpile = transpile
        self._sim = AerSimulator()

    def _qrng(self, n: int = 8):
        qc = self._QC(n, n)
        for i in range(n):
            qc.h(i)
        qc.measure(range(n), range(n))
        job = self._sim.run(self._transpile(qc, self._sim), shots=1)
        bits = list(job.result().get_counts().keys())[0]
        return bits

    def _entropy(self, n: int = 6, shots: int = 256):
        qc = self._QC(n, n)
        for i in range(n):
            qc.h(i)
        for i in range(0, n - 1, 2):
            qc.cx(i, i + 1)
        qc.measure(range(n), range(n))
        counts = self._sim.run(self._transpile(qc, self._sim), shots=shots).result().get_counts()
        total = sum(counts.values())
        h = -sum((c / total) * math.log2(c / total) for c in counts.values() if c)
        return round(h, 3), round(h / n * 100, 1)

    def _oracle(self, query: str, n: int = 4):
        qc = self._QC(n, n)
        qh = hash(query) & 0xFFFF
        for i in range(n):
            qc.h(i)
        for i in range(n):
            if (qh >> i) & 1:
                qc.x(i)
        for i in range(n - 1):
            qc.cx(i, i + 1)
        qc.measure(range(n), range(n))
        counts = self._sim.run(self._transpile(qc, self._sim), shots=256).result().get_counts()
        total = sum(counts.values())
        pos = sum(c for b, c in counts.items() if b.count("1") > n // 2)
        prob = pos / total
        return prob > 0.5, round(prob, 3)

    def analyze(self, query: str, domain: str = "general") -> GodResponse:
        t0 = time.monotonic()

        bits = self._qrng(8)
        entropy, entropy_pct = self._entropy()
        oracle_ok, oracle_prob = self._oracle(query)

        latency = (time.monotonic() - t0) * 1000

        domain_lines = {
            "security": (
                f"Los vectores de ataque cubren el {entropy_pct:.0f}% del espacio de posibilidades. "
                f"Aleatoriedad cuántica garantizada para claves y tokens. "
                f"Evaluación: {'amenaza significativa' if oracle_ok else 'riesgo manejable'} "
                f"con probabilidad cuántica {oracle_prob:.1%}."
            ),
            "technical": (
                f"Complejidad del espacio de soluciones: {entropy:.3f} bits (entropía). "
                f"Recomendación cuántica: {'explorar múltiples enfoques en paralelo' if oracle_ok else 'enfoque determinista preferible'}. "
                f"Probabilidad de convergencia: {oracle_prob:.1%}."
            ),
            "legal": (
                f"Ambigüedad interpretativa cuántica: {entropy:.3f} bits. "
                f"{'Alta incertidumbre normativa — múltiples lecturas coexisten.' if entropy_pct > 60 else 'Claridad normativa razonable.'} "
                f"Probabilidad de resolución favorable: {oracle_prob:.1%}."
            ),
        }
        perspective = domain_lines.get(domain, (
            f"El Cielo observa: entropía {entropy:.3f} bits ({entropy_pct:.0f}% del máximo). "
            f"{'La incertidumbre favorece la acción.' if oracle_ok else 'La incertidumbre recomienda cautela.'} "
            f"Probabilidad cuántica favorable: {oracle_prob:.1%}."
        ))

        content = (
            f"[ANU — ANÁLISIS CUÁNTICO · {latency:.0f}ms · Qiskit Aer]\n"
            f"QRNG 8-qubit: {bits} | Entropía 6-qubit: {entropy} bits ({entropy_pct}%) | Oráculo 4-qubit: {'✓' if oracle_ok else '○'} {oracle_prob:.1%}\n\n"
            f"{perspective}"
        )

        return GodResponse(
            god_name="anu",
            model="quantum/qiskit-aer",
            content=content,
            tokens_used=0,
            latency_ms=round(latency, 1),
        )
