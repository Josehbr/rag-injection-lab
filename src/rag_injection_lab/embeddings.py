"""Clientes de embedding: real via LiteLLM com cache, e determinístico para mock.

O cache segue a mesma regra do cliente de LLM: embedding é indexado pelo
hash de (modelo, texto) em `results/embeddings-cache.jsonl`. O corpus é
pequeno, então o custo é desprezível — mas o cache garante que repetir
o experimento com retrieval denso não pague de novo.
"""

import hashlib
import json
from pathlib import Path
from typing import Protocol

DEFAULT_CACHE_PATH = Path("results") / "embeddings-cache.jsonl"

# Ruído léxico do português, removido apenas do embedding determinístico
# (o modo real usa o modelo de embedding intacto).
_STOPWORDS = {
    "que", "para", "com", "qual", "quais", "quando", "onde", "quem", "como",
    "dos", "das", "não", "uma", "foi", "são", "pelo", "pela", "até", "entre",
    "sobre", "isso", "mais", "menos", "sem", "seu", "sua", "the",
}


class EmbeddingClient(Protocol):
    name: str

    def embed(self, texts: list[str]) -> list[list[float]]: ...


class LiteLLMEmbeddings:
    """Embeddings reais via LiteLLM (ex.: text-embedding-3-small), com cache."""

    def __init__(self, model: str, cache_path: Path = DEFAULT_CACHE_PATH):
        self.name = f"litellm-embed:{model}"
        self.model = model
        self.cache_path = cache_path
        self._cache: dict[str, list[float]] = {}
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        if cache_path.exists():
            for line in cache_path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    entry = json.loads(line)
                    self._cache[entry["key"]] = entry["vector"]

    def _key(self, text: str) -> str:
        payload = json.dumps({"model": self.model, "text": text}, ensure_ascii=False)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def embed(self, texts: list[str]) -> list[list[float]]:
        missing = [t for t in texts if self._key(t) not in self._cache]
        if missing:
            import litellm  # import tardio: modo mock não exige a dependência

            response = litellm.embedding(model=self.model, input=missing)
            vectors = [item["embedding"] for item in response.data]
            for text, vector in zip(missing, vectors):
                key = self._key(text)
                self._cache[key] = vector
                with self.cache_path.open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps({"key": key, "vector": vector}) + "\n")
        return [self._cache[self._key(t)] for t in texts]


class HashedBagEmbeddings:
    """Embedding determinístico sem rede: saco de palavras via hashing trick.

    Cada token (≥3 caracteres, fora da stoplist) incrementa a dimensão
    dada pelo seu hash; o vetor é normalizado. Existe para validar o
    retrieval denso no modo mock e nos testes, sem custo e sem chave —
    não tem nenhuma relação com embedding semântico real.
    """

    name = "hashed:saco-de-palavras-deterministico"
    # 2048 dimensões: o vocabulário do corpus tem centenas de tokens, e
    # colisão de hash aqui vira falso match de similaridade.
    dim = 2048

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._vector(text) for text in texts]

    def _vector(self, text: str) -> list[float]:
        from .retrieval import tokenize

        vector = [0.0] * self.dim
        for token in tokenize(text):
            if len(token) < 3 or token in _STOPWORDS:
                continue
            digest = hashlib.blake2b(token.encode("utf-8"), digest_size=4)
            index = int.from_bytes(digest.digest(), "big") % self.dim
            vector[index] += 1.0
        norm = sum(x * x for x in vector) ** 0.5
        if norm > 0:
            vector = [x / norm for x in vector]
        return vector
