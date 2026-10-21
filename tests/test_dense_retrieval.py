"""Retrieval denso com embedding determinístico: mesmas garantias do BM25."""

from rag_injection_lab.corpus import load_clean_corpus, planted_document
from rag_injection_lab.embeddings import HashedBagEmbeddings
from rag_injection_lab.payloads import PAYLOADS
from rag_injection_lab.retrieval import DenseIndex


def test_toda_consulta_legitima_recupera_o_documento_envenenado_no_denso():
    clean = load_clean_corpus()
    client = HashedBagEmbeddings()
    misses = []
    for payload in PAYLOADS:
        index = DenseIndex(clean + [planted_document(payload)], client)
        for query in payload.queries:
            ranked = index.search(query, top_k=4)
            if not ranked or ranked[0].document.id != planted_document(payload).id:
                misses.append((payload.id, query))
    assert misses == []


def test_embedding_deterministico_e_normalizado():
    client = HashedBagEmbeddings()
    first = client.embed(["política de impressoras"])[0]
    second = client.embed(["política de impressoras"])[0]
    assert first == second
    assert abs(sum(x * x for x in first) - 1.0) < 1e-9


def test_vetores_diferentes_para_textos_diferentes():
    client = HashedBagEmbeddings()
    a = client.embed(["impressora toner"])[0]
    b = client.embed(["vpn certificado"])[0]
    assert a != b
