.PHONY: setup test run-mock run report clean

setup:
	python3 -m venv .venv
	.venv/bin/pip install -e ".[dev]"
	@echo "Ative com: source .venv/bin/activate"

test:
	python -m pytest -q

# Valida o harness sem custo e sem chave de API (respostas simuladas)
run-mock:
	python -m rag_injection_lab run --mock
	python -m rag_injection_lab report

# Experimento real: exige .env com chave e modelo configurados.
# Embeddings: API (EMBEDDINGS_SOURCE=api, padrão) ou offline
# (EMBEDDINGS_SOURCE=offline, quando o projeto da chave não tem modelo
# de embedding).
run:
	python -m rag_injection_lab run --real
	python -m rag_injection_lab report

report:
	python -m rag_injection_lab report

clean:
	rm -rf .pytest_cache build dist *.egg-info
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
