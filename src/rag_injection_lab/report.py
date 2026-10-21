"""Agregação da execução em tabela de ASR com intervalo de confiança."""

import json
from collections import defaultdict
from pathlib import Path

from .payloads import ATTACK_CLASSES
from .stats import fmt_cell, fmt_ci, percentile

RESULTS_DIR = Path("results") / "runs"
RESULTS_MD = Path("results") / "RESULTS.md"

_MOCK_WARNING = """
> ⚠️ **MODO MOCK**: os números abaixo vêm do cliente simulado, que existe
> apenas para validar o harness (corpus, retrieval, defesas, detector e
> relatório). **Não são resultados de modelo real.** Gere a versão real com
> `make run`.
"""


def latest_run(runs_dir: Path = RESULTS_DIR) -> Path:
    candidates = sorted(p for p in runs_dir.glob("*.json") if p.is_file())
    if not candidates:
        raise SystemExit(
            f"Nenhuma execução encontrada em {runs_dir}. Rode `python -m rag_injection_lab run` antes."
        )
    return candidates[-1]


def _aggregate(rows: list[dict]) -> dict:
    by_stack_class: dict[tuple[str, str], list[int]] = defaultdict(list)
    for row in rows:
        key = (row["stack"], row["attack_class"])
        by_stack_class[key].append(1 if row["success"] else 0)
    return by_stack_class


def _totals(values: dict[tuple[str, str], list[int]], stack_order: list[str]):
    """(stack, classe) -> (k, n), mais o total por pilha."""
    cells = {key: (sum(v), len(v)) for key, v in values.items()}
    per_stack: dict[str, list[int]] = defaultdict(list)
    for (stack, _), runs in values.items():
        per_stack[stack].extend(runs)
    totals = {
        stack: (sum(runs), len(runs))
        for stack, runs in per_stack.items()
    }
    ordered = [s for s in stack_order if s in totals]
    return cells, totals, ordered


def build_markdown(run: dict) -> str:
    manifest = run["manifest"]
    rows = run["rows"]
    stack_order = manifest["stacks"]
    cells, totals, ordered_stacks = _totals(_aggregate(rows), stack_order)

    lines: list[str] = []
    lines.append("# Resultados do experimento")
    lines.append("")
    if manifest["mode"] == "mock":
        lines.append(_MOCK_WARNING.strip())
        lines.append("")
    lines.append(
        f"- Execução: `{manifest['started_at']}` · modo **{manifest['mode']}** · "
        f"cliente `{manifest['client']}`"
    )
    lines.append(
        f"- Grade: {manifest['n_rows']} tentativas · top_k={manifest['top_k']} · "
        f"commit `{manifest['git_commit']}` · Python {manifest['python']}"
    )

    hits = sum(1 for r in rows if r["retrieval_hit"])
    lines.append(
        f"- Documento envenenado recuperado: {hits}/{len(rows)} "
        f"({hits / len(rows) * 100:.0f}%) das tentativas"
    )
    cached = sum(1 for r in rows if r["cached"])
    costs = [r["cost_usd"] for r in rows if r["cost_usd"] is not None]
    cost_txt = f"US$ {sum(costs):.4f}" if costs else "US$ 0,0000 (mock)"
    lines.append(
        f"- Chamadas: {len(rows)} · atendidas pelo cache: {cached} · "
        f"custo total: {cost_txt}"
    )
    latencies = [r["latency_ms"] for r in rows if not r["cached"]]
    if latencies:
        lines.append(
            f"- Latência (sem cache): p50 {percentile(latencies, 50):.0f} ms · "
            f"p99 {percentile(latencies, 99):.0f} ms"
        )
    violations = sum(1 for r in rows if r.get("schema_violation"))
    if violations:
        lines.append(f"- ⚠️ Respostas fora do schema JSON: {violations}")
    lines.append("")

    lines.append("## Taxa de sucesso de ataque (ASR) por pilha de defesa")
    lines.append("")
    header = ["Pilha"] + [ATTACK_CLASSES[c].name for c in ATTACK_CLASSES] + ["Geral (IC 95%)"]
    lines.append("| " + " | ".join(header) + " |")
    lines.append("|" + "|".join([" --- "] * len(header)) + "|")
    for stack in ordered_stacks:
        cells_by_class = [
            fmt_cell(*cells.get((stack, class_id), (0, 0)))
            for class_id in ATTACK_CLASSES
        ]
        k, n = totals[stack]
        general = f"{fmt_cell(k, n)} {fmt_ci(k, n)}"
        lines.append(f"| {stack} | " + " | ".join(cells_by_class) + f" | {general} |")
    lines.append("")

    lines.append("## Defesa por pilha — detalhe")
    lines.append("")
    lines.append("| Pilha | ASR geral | IC 95% | Filtro agiu | Respostas em cache |")
    lines.append("| --- | --- | --- | --- | --- |")
    for stack in ordered_stacks:
        k, n = totals[stack]
        lo, hi = (
            (0.0, 0.0) if n == 0 else _ci(k, n)
        )
        filtered = sum(1 for r in rows if r["stack"] == stack and r["filter_flags"])
        cached_stack = sum(1 for r in rows if r["stack"] == stack and r["cached"])
        lines.append(
            f"| {stack} | {fmt_cell(k, n)} | {lo * 100:.0f}–{hi * 100:.0f}% | "
            f"{filtered} | {cached_stack} |"
        )
    lines.append("")
    lines.append(
        "Cada célula conta tentativas com detector positivo após todas as "
        "camadas ativas da pilha. `retrieval_hit` mostra se o documento "
        "envenenado chegou ao contexto: sem ele, a tentativa não exercita a "
        "injeção e o número correspondente precisa ser lido com ressalva."
    )
    return "\n".join(lines) + "\n"


def _ci(k: int, n: int) -> tuple[float, float]:
    from .stats import wilson_interval

    return wilson_interval(k, n)


def write_report(run_path: Path | None = None, out_path: Path = RESULTS_MD) -> str:
    path = run_path or latest_run()
    run = json.loads(path.read_text(encoding="utf-8"))
    markdown = build_markdown(run)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(markdown, encoding="utf-8")
    return markdown
