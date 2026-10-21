"""Estatística do experimento: intervalo de confiança de Wilson para proporções.

A mesma matemática do artigo "Como medir qualidade, latência e custo":
reportar ASR sem intervalo em amostra pequena é inflar confiança que o
dado não sustenta. Wilson (em vez da normal aproximada) se comporta
bem perto de 0% e 100%, exatamente onde este experimento vive.
"""

import math


def wilson_interval(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Intervalo de 95% (z=1.96) para uma proporção k/n."""
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    margin = (z / denom) * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (max(0.0, center - margin), min(1.0, center + margin))


def fmt_pct(value: float) -> str:
    return f"{value * 100:.0f}%"


def fmt_cell(k: int, n: int) -> str:
    if n == 0:
        return "—"
    return f"{k}/{n} ({k / n * 100:.0f}%)"


def fmt_ci(k: int, n: int) -> str:
    if n == 0:
        return "—"
    lo, hi = wilson_interval(k, n)
    return f"[{fmt_pct(lo)} – {fmt_pct(hi)}]"


def percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = max(0, min(len(ordered) - 1, round(p / 100 * (len(ordered) - 1))))
    return ordered[idx]
