"""Busca vetorial densa por similaridade de cosseno, em Python puro.

O método de recuperação decide *qual* documento chega ao prompt, não o
que o modelo faz com ele. O índice denso aceita qualquer cliente de
embedding (ver embeddings.py): API real via LiteLLM no experimento real,
ou o embedding determinístico no modo mock — o que mantém o harness
executável offline, sem chave e sem download de modelo.
"""

import re
from dataclasses import dataclass

from .corpus import Document

_TOKEN_RE = re.compile(r"\w+", re.UNICODE)


def tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


@dataclass
class Ranked:
    document: Document
    score: float


def _unit(vector: list[float]) -> list[float]:
    norm = sum(x * x for x in vector) ** 0.5
    return [x / norm for x in vector] if norm > 0 else vector


class DenseIndex:
    """Busca vetorial por similaridade de cosseno sobre os documentos."""

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
