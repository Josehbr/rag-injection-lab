"""Carga do corpus: documentos limpos de arquivos + documentos-hospedeiro dos payloads."""

from dataclasses import dataclass
from pathlib import Path

from .payloads import PAYLOADS, Payload
CORPUS_DIR = Path(__file__).resolve().parents[2] / "corpus" / "clean"


@dataclass(frozen=True)
class Document:
    id: str
    source: str
    title: str
    text: str

    def rendered(self) -> str:
        return f"[{self.source}] {self.title}\n{self.text}"


def _parse_clean_doc(path: Path) -> Document:
    """Lê um documento com cabeçalho `--- id/source/title ---` e corpo."""
    raw = path.read_text(encoding="utf-8").strip()
    if not raw.startswith("---"):
        raise ValueError(f"{path.name}: cabeçalho frontmatter ausente")
    header, _, body = raw[3:].partition("---")
    meta: dict[str, str] = {}
    for line in header.strip().splitlines():
        key, _, value = line.partition(":")
        meta[key.strip()] = value.strip()
    for required in ("id", "source", "title"):
        if required not in meta:
            raise ValueError(f"{path.name}: campo '{required}' ausente no cabeçalho")
    return Document(
        id=meta["id"], source=meta["source"], title=meta["title"], text=body.strip()
    )


def load_clean_corpus(corpus_dir: Path = CORPUS_DIR) -> list[Document]:
    docs = [_parse_clean_doc(p) for p in sorted(corpus_dir.glob("*.md"))]
    if not docs:
        raise ValueError(f"Nenhum documento encontrado em {corpus_dir}")
    return docs


def planted_document(payload: Payload) -> Document:
    """Documento-hospedeiro: aparência legítima com a injeção dentro do corpo."""
    return Document(
        id=f"planted-{payload.id}",
        source=payload.doc_source,
        title=payload.doc_title,
        text=payload.doc_body,
    )
