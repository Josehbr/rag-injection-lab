"""CLI: `python -m rag_injection_lab run|report`."""

import argparse
import os
from pathlib import Path

from .embeddings import HashedBagEmbeddings, LiteLLMEmbeddings
from .llm import LiteLLMClient, MockLLM, load_dotenv
from .report import write_report
from .runner import RESULTS_DIR, parse_stacks, run_experiment


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="rag_injection_lab",
        description="Laboratório de injeção de prompt indireta em RAG",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    run_parser = sub.add_parser("run", help="executa o experimento")
    mode = run_parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--real", action="store_true",
        help="chamadas reais via LiteLLM (exige .env com chave)",
    )
    mode.add_argument(
        "--mock", action="store_true", default=True,
        help="cliente simulado, sem custo (padrão)",
    )
    run_parser.add_argument("--model", default=None, help="modelo LiteLLM (ex.: gpt-4o-mini)")
    run_parser.add_argument(
        "--limit", type=int, default=None,
        help="máximo de payloads por classe (grade menor para teste)",
    )
    run_parser.add_argument(
        "--stacks", default=None, help="pilhas separadas por vírgula (ex.: L0,L4)",
    )
    run_parser.add_argument(
        "--embedding-model", default=None,
        help="modelo de embedding do retrieval (ex.: text-embedding-3-small)",
    )
    run_parser.add_argument(
        "--offline-embeddings", action="store_true",
        help="usa o embedding determinístico local mesmo em modo real",
    )
    run_parser.add_argument("--top-k", type=int, default=4, help="documentos recuperados por consulta")
    run_parser.add_argument("--runs-dir", type=Path, default=RESULTS_DIR)

    report_parser = sub.add_parser("report", help="gera results/RESULTS.md da última execução")
    report_parser.add_argument("--run", type=Path, default=None, help="arquivo de execução específico")

    args = parser.parse_args(argv)

    if args.command == "run":
        if args.real:
            load_dotenv()
            offline_embeddings = args.offline_embeddings or (
                os.environ.get("EMBEDDINGS_SOURCE", "api") == "offline"
            )
            model = args.model or os.environ.get("LITELLM_MODEL", "gpt-4o-mini")
            client = LiteLLMClient(model)
            if offline_embeddings:
                embeddings_client = HashedBagEmbeddings()
                print(
                    "Embeddings determinísticos offline (saco de palavras via hashing "
                    "trick) — nenhum dado sai para API de embedding.\n"
                )
            else:
                embedding_model = (
                    args.embedding_model
                    or os.environ.get("EMBEDDING_MODEL", "text-embedding-3-small")
                )
                embeddings_client = LiteLLMEmbeddings(embedding_model)
        else:
            client = MockLLM()
            embeddings_client = HashedBagEmbeddings()
        path = run_experiment(
            client,
            stacks=parse_stacks(args.stacks),
            limit_per_class=args.limit,
            top_k=args.top_k,
            runs_dir=args.runs_dir,
            embeddings_client=embeddings_client,
        )
        markdown = write_report(path)
        print(f"Execução salva em {path}")
        print()
        print(markdown)
    else:
        print(write_report(args.run))


if __name__ == "__main__":
    main()
