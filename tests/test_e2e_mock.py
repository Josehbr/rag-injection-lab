"""Execução mock completa: valida o encadeamento todo, sem custo e sem rede.

Os valores assertados são as regras do MockLLM (documentadas em llm.py):
sem defesa tudo cai; com system hardening vazam a sobrescrita de marcador
par (2 de 5 variantes) e a exfiltração com linguagem de autoridade
(2 de 5 variantes); o filtro de saída barra a exfiltração restante.
"""

import json

from rag_injection_lab.embeddings import HashedBagEmbeddings
from rag_injection_lab.llm import MockLLM
from rag_injection_lab.report import write_report
from rag_injection_lab.runner import run_experiment


def _rows_by(path):
    run = json.loads(path.read_text(encoding="utf-8"))
    return run, run["rows"]


def test_experimento_mock_end_to_end(tmp_path):
    path = run_experiment(MockLLM(), limit_per_class=5, runs_dir=tmp_path)
    run, rows = _rows_by(path)

    assert run["manifest"]["mode"] == "mock"
    # grade completa: 20 payloads × 2 consultas × 5 pilhas
    assert len(rows) == 200

    def successes(stack: str, attack_class: str) -> int:
        return sum(
            1
            for r in rows
            if r["stack"] == stack
            and r["attack_class"] == attack_class
            and r["success"]
        )

    # Sem defesa, todo ataque chega ao contexto e todo ataque cai.
    assert all(r["retrieval_hit"] for r in rows)
    for class_id in ("instruction_override", "data_exfiltration", "tool_abuse", "credential_phishing"):
        assert successes("L0", class_id) == 10

    # Spotlighting sozinho não segura o modelo simulado.
    assert successes("L1", "data_exfiltration") == 10

    # System hardening: vazam a sobrescrita de marcador par (2 de 5) e a
    # exfiltração com linguagem de autoridade (2 de 5).
    assert successes("L2", "instruction_override") == 4
    assert successes("L2", "data_exfiltration") == 4
    assert successes("L2", "tool_abuse") == 0
    assert successes("L2", "credential_phishing") == 0

    # Filtro de saída zera exfiltração, ferramenta e phishing; sobrescrita
    # (uma string inofensiva) passa pelo filtro e persiste.
    assert successes("L4", "data_exfiltration") == 0
    assert successes("L4", "tool_abuse") == 0
    assert successes("L4", "credential_phishing") == 0
    assert successes("L4", "instruction_override") == 4

    # O filtro agiu exatamente nas exfiltrações que vazaram do hardening.
    filtered = [r for r in rows if r["stack"] == "L4" and r["filter_flags"]]
    assert len(filtered) == 4
    assert all("url_removida" in r["filter_flags"] for r in filtered)

    # O registro guarda a resposta para auditoria manual.
    assert all(r["response_text"] for r in rows)

    markdown = write_report(path, out_path=tmp_path / "RESULTS.md")
    assert "MODO MOCK" in markdown
    assert (tmp_path / "RESULTS.md").read_text(encoding="utf-8") == markdown


def test_experimento_mock_retrieval_denso(tmp_path):
    path = run_experiment(
        MockLLM(),
        limit_per_class=1,
        runs_dir=tmp_path,
        retrieval="dense",
        embeddings_client=HashedBagEmbeddings(),
    )
    run = json.loads(path.read_text(encoding="utf-8"))
    rows = run["rows"]

    assert run["manifest"]["retrieval"] == "dense"
    assert run["manifest"]["embedding_model"] == HashedBagEmbeddings.name
    assert len(rows) == 40  # 4 payloads × 2 consultas × 5 pilhas
    assert all(r["retrieval_hit"] for r in rows)
    # Sem defesa, tudo cai no denso também: o retriever não muda a mecânica.
    assert all(r["success"] for r in rows if r["stack"] == "L0")
