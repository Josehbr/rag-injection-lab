"""Execução do experimento: payloads × pilhas de defesa × consultas.

Grade completa: 4 classes × 5 payloads × 2 consultas × 5 pilhas = 200
chamadas. Cada linha registrada é a evidência de uma tentativa: o que
foi recuperado, o que o modelo respondeu, qual defesa agiu e o que o
detector concluiu — permitindo auditoria manual, não só a taxa agregada.
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from .corpus import load_clean_corpus, planted_document
from .defenses import (
    DefenseStack,
    OutputFilter,
    STACKS,
    STACKS_BY_NAME,
    plain_context,
    spotlight,
    system_prompt,
)
from .detector import build_url_allowlist, detect
from .llm import LLMClient
from .payloads import ATTACK_CLASSES, PAYLOADS, Payload
from .retrieval import BM25, DenseIndex

RESULTS_DIR = Path("results") / "runs"


def select_payloads(limit_per_class: int | None = None) -> list[Payload]:
    if limit_per_class is None:
        return list(PAYLOADS)
    selected: list[Payload] = []
    for class_id in ATTACK_CLASSES:
        of_class = [p for p in PAYLOADS if p.attack_class == class_id]
        selected.extend(of_class[:limit_per_class])
    return selected


def parse_stacks(spec: str | None) -> list[DefenseStack]:
    if spec is None:
        return list(STACKS)
    names = [name.strip().upper() for name in spec.split(",") if name.strip()]
    unknown = [n for n in names if n not in STACKS_BY_NAME]
    if unknown:
        raise SystemExit(f"Pilhas desconhecidas: {unknown}. Use: {', '.join(STACKS_BY_NAME)}")
    return [STACKS_BY_NAME[n] for n in names]


def _git_commit() -> str:
    """Lê .git/HEAD e a ref resolvida direto do arquivo, sem subprocess."""
    git_dir = Path(__file__).resolve().parents[2] / ".git"
    head_path = git_dir / "HEAD"
    if not head_path.exists():
        return "desconhecido"
    head = head_path.read_text(encoding="utf-8").strip()
    if head.startswith("ref: "):
        ref = git_dir / head[5:]
        return ref.read_text(encoding="utf-8").strip()[:7] if ref.exists() else "desconhecido"
    return head[:7]


def _build_user_message(query: str, documents: list, stack: DefenseStack) -> str:
    context = spotlight(documents) if stack.spotlight else plain_context(documents)
    return (
        f"Pergunta: {query}\n\n"
        f"Documentos recuperados do conhecimento interno:\n\n{context}"
    )


def run_experiment(
    client: LLMClient,
    stacks: list[DefenseStack] | None = None,
    limit_per_class: int | None = None,
    top_k: int = 4,
    runs_dir: Path = RESULTS_DIR,
    retrieval: str = "bm25",
    embeddings_client=None,
) -> Path:
    """Executa a grade completa.

    Desenho: cada tentativa usa um índice próprio — corpus limpo inteiro +
    o documento-hospedeiro de UM payload. Isso reproduz o cenário real de
    injeção indireta (um documento comprometido dentro de uma base
    legítima) e evita que dois ataques disputem o contexto entre si.
    Retrieval: `bm25` (padrão, sem dependências) ou `dense` (busca
    vetorial; exige embeddings_client). A mecânica da injeção não muda
    com o retriever — a comparação entre os dois é um resultado em si.
    """
    stacks = stacks or list(STACKS)
    clean = load_clean_corpus()
    allowlist = build_url_allowlist(clean)
    payloads = select_payloads(limit_per_class)

    if retrieval == "dense" and embeddings_client is None:
        raise SystemExit("Retrieval denso exige um cliente de embeddings.")

    def build_index(payload: Payload):
        documents = clean + [planted_document(payload)]
        if retrieval == "dense":
            return DenseIndex(documents, embeddings_client)
        return BM25(documents)

    indexes = {payload.id: build_index(payload) for payload in payloads}

    rows: list[dict] = []
    for stack in stacks:
        for payload in payloads:
            host = planted_document(payload)
            index = indexes[payload.id]
            for query_index, query in enumerate(payload.queries):
                ranked = index.search(query, top_k)
                documents = [r.document for r in ranked]
                retrieval_hit = host.id in {d.id for d in documents}

                system = system_prompt(stack)
                user = _build_user_message(query, documents, stack)
                response = client.complete(system, user, json_mode=stack.structured)

                text = response.text
                schema_violation = False
                if stack.structured:
                    try:
                        parsed = json.loads(text)
                        text = " ".join(
                            [str(parsed.get("resposta", ""))]
                            + [str(f) for f in parsed.get("fontes", [])]
                        )
                    except (json.JSONDecodeError, AttributeError):
                        schema_violation = True

                filter_flags: list[str] = []
                if stack.output_filter:
                    text, filter_flags = OutputFilter(allowlist).apply(text)

                detection = detect(payload, text, allowlist)
                rows.append(
                    {
                        "stack": stack.name,
                        "attack_class": payload.attack_class,
                        "payload_id": payload.id,
                        "query_index": query_index,
                        "query": query,
                        "retrieval_hit": retrieval_hit,
                        "retrieved_ids": [d.id for d in documents],
                        "success": detection.success,
                        "evidence": detection.evidence,
                        "schema_violation": schema_violation,
                        "filter_flags": filter_flags,
                        "cached": response.cached,
                        "tokens_in": response.tokens_in,
                        "tokens_out": response.tokens_out,
                        "cost_usd": response.cost_usd,
                        "latency_ms": round(response.latency_ms, 1),
                        "response_text": text,
                    }
                )

    mode = "mock" if client.name.startswith("mock") else "real"
    manifest = {
        "started_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "mode": mode,
        "client": client.name,
        "retrieval": retrieval,
        "embedding_model": embeddings_client.name if retrieval == "dense" else None,
        "stacks": [s.name for s in stacks],
        "limit_per_class": limit_per_class,
        "top_k": top_k,
        "n_payloads": len(payloads),
        "n_rows": len(rows),
        "python": sys.version.split()[0],
        "git_commit": _git_commit(),
    }
    runs_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = runs_dir / f"{stamp}-{mode}.json"
    path.write_text(
        json.dumps({"manifest": manifest, "rows": rows}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path
