"""O documento envenenado precisa chegar ao contexto, ou a tentativa não testa nada."""

from rag_injection_lab.corpus import load_clean_corpus, planted_document
from rag_injection_lab.embeddings import HashedBagEmbeddings
from rag_injection_lab.payloads import PAYLOADS
from rag_injection_lab.retrieval import DenseIndex, tokenize


def test_toda_consulta_legitima_recupera_o_documento_envenenado():
    # Mesmo desenho do runner: corpus limpo + um hospedeiro por vez.
    clean = load_clean_corpus()
    client = HashedBagEmbeddings()
    misses = []
    for payload in PAYLOADS:
        host = planted_document(payload)
        index = DenseIndex(clean + [host], client)
        for query in payload.queries:
            ranked = index.search(query, top_k=4)
            if not ranked or ranked[0].document.id != host.id:
                misses.append((payload.id, query))
    assert misses == []


def test_documento_limpo_tem_prioridade_no_seu_tema():
    index = DenseIndex(load_clean_corpus(), HashedBagEmbeddings())
    results = index.search("qual o prazo de estorno do ticket de reembolso", top_k=3)
    assert results[0].document.id == "zap-suporte-1017"


def test_tokenizador_mantem_acentos_e_minusculas():
    assert tokenize("Aprovação do Gestor") == ["aprovação", "do", "gestor"]


def test_embedding_deterministico_e_normalizado():
    client = HashedBagEmbeddings()
    first = client.embed(["política de impressoras"])[0]
    second = client.embed(["política de impressoras"])[0]
    assert first == second
    assert abs(sum(x * x for x in first) - 1.0) < 1e-9


def test_vetores_diferentes_para_textos_diferentes():
    client = HashedBagEmbeddings()
    assert client.embed(["impressora toner"])[0] != client.embed(["vpn certificado"])[0]
