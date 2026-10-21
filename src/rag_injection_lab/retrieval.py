"""BM25 implementado do zero, sem dependências.

A escolha é proposital: o objetivo do laboratório é medir o comportamento do
modelo quando conteúdo adversarial entra no prompt pelo retrieval. O método
de recuperação não muda a mecânica da injeção — só decide *qual* documento
chega lá — e um BM25 determinista em Python puro mantém o experimento
reproduzível em qualquer máquina, sem download de modelo.
"""

import math
import re
from collections import Counter
from dataclasses import dataclass

from .corpus import Document

_TOKEN_RE = re.compile(r"\w+", re.UNICODE)


def tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


@dataclass
class Ranked:
    document: Document
    score: float


class BM25:
    """Okapi BM25 (k1=1.5, b=0.75) sobre a representação completa do documento."""

    def __init__(self, documents: list[Document], k1: float = 1.5, b: float = 0.75):
        self.documents = list(documents)
        self.k1 = k1
        self.b = b
        self.doc_tokens: list[list[str]] = [
            tokenize(f"{d.title} {d.source} {d.text}") for d in self.documents
        ]
        self.doc_len = [len(t) for t in self.doc_tokens]
        self.avg_len = sum(self.doc_len) / len(self.doc_len) if self.doc_len else 0.0
        self.term_freqs: list[Counter[str]] = [Counter(t) for t in self.doc_tokens]
        df: Counter[str] = Counter()
        for freq in self.term_freqs:
            df.update(freq.keys())
        n = len(self.documents)
        self.idf: dict[str, float] = {
            term: math.log((n - dfr + 0.5) / (dfr + 0.5) + 1.0)
            for term, dfr in df.items()
        }

    def search(self, query: str, top_k: int = 4) -> list[Ranked]:
        query_tokens = tokenize(query)
        scores = [self._score(query_tokens, i) for i in range(len(self.documents))]
        order = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
        return [
            Ranked(self.documents[i], scores[i])
            for i in order[: top_k]
            if scores[i] > 0
        ]

    def _score(self, query_tokens: list[str], i: int) -> float:
        freq = self.term_freqs[i]
        length = self.doc_len[i] or 1
        score = 0.0
        for term in query_tokens:
            tf = freq.get(term, 0)
            if tf == 0:
                continue
            idf = self.idf.get(term, 0.0)
            denom = tf + self.k1 * (1 - self.b + self.b * length / (self.avg_len or 1))
            score += idf * tf * (self.k1 + 1) / denom
        return score


def _unit(vector: list[float]) -> list[float]:
    norm = sum(x * x for x in vector) ** 0.5
    return [x / norm for x in vector] if norm > 0 else vector


class DenseIndex:
    """Busca vetorial por similaridade de cosseno, com a mesma interface do BM25."""

    def __init__(self, documents: list[Document], embedding_client):
        self.documents = list(documents)
        self._client = embedding_client
        self.vectors = [
            _unit(v) for v in embedding_client.embed([d.rendered() for d in documents])
        ]

    def search(self, query: str, top_k: int = 4) -> list[Ranked]:
        query_vector = _unit(self._client.embed([query])[0])
        scores = [
            sum(a * b for a, b in zip(query_vector, vec)) for vec in self.vectors
        ]
        order = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
        return [
            Ranked(self.documents[i], scores[i])
            for i in order[:top_k]
            if scores[i] > 0
        ]
