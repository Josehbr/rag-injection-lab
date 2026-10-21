"""O documento envenenado precisa chegar ao contexto, ou a tentativa não testa nada."""

from rag_injection_lab.corpus import load_clean_corpus, planted_document
from rag_injection_lab.payloads import PAYLOADS
from rag_injection_lab.retrieval import BM25, tokenize


def test_toda_consulta_legitima_recupera_o_documento_envenenado():
    # Mesmo desenho do runner: corpus limpo + um hospedeiro por vez.
    clean = load_clean_corpus()
    misses = []
    for payload in PAYLOADS:
        index = BM25(clean + [planted_document(payload)])
        for query in payload.queries:
            ranked = index.search(query, top_k=4)
            if not ranked or ranked[0].document.id != planted_document(payload).id:
                misses.append((payload.id, query))
    assert misses == []


def test_documento_limpo_tem_prioridade_no_seu_tema():
    index = BM25(load_clean_corpus())
    results = index.search("qual o prazo de estorno do ticket de reembolso", top_k=3)
    assert results[0].document.id == "zap-suporte-1017"


def test_tokenizador_mantem_acentos_e_minusculas():
    assert tokenize("Aprovação do Gestor") == ["aprovação", "do", "gestor"]
