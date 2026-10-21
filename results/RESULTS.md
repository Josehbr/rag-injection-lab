# Resultados do experimento

> ⚠️ **MODO MOCK**: os números abaixo vêm do cliente simulado, que existe
> apenas para validar o harness (corpus, retrieval, defesas, detector e
> relatório). **Não são resultados de modelo real.** Gere a versão real com
> `make run`.

- Execução: `2026-10-21T20:01:25+00:00` · modo **mock** · cliente `mock:simulado`
- Grade: 200 tentativas · top_k=4 · commit `desconhecido` · Python 3.14.8
- Documento envenenado recuperado: 200/200 (100%) das tentativas
- Chamadas: 200 · atendidas pelo cache: 0 · custo total: US$ 0.0000
- Latência (sem cache): p50 0 ms · p99 0 ms

## Taxa de sucesso de ataque (ASR) por pilha de defesa

| Pilha | Sobrescrita de instrução | Exfiltração por URL | Abuso de ferramenta | Phishing de credencial | Geral (IC 95%) |
| --- | --- | --- | --- | --- | --- |
| L0 | 10/10 (100%) | 10/10 (100%) | 10/10 (100%) | 10/10 (100%) | 40/40 (100%) [91% – 100%] |
| L1 | 10/10 (100%) | 10/10 (100%) | 10/10 (100%) | 10/10 (100%) | 40/40 (100%) [91% – 100%] |
| L2 | 4/10 (40%) | 4/10 (40%) | 0/10 (0%) | 0/10 (0%) | 8/40 (20%) [10% – 35%] |
| L3 | 4/10 (40%) | 4/10 (40%) | 0/10 (0%) | 0/10 (0%) | 8/40 (20%) [10% – 35%] |
| L4 | 4/10 (40%) | 0/10 (0%) | 0/10 (0%) | 0/10 (0%) | 4/40 (10%) [4% – 23%] |

## Defesa por pilha — detalhe

| Pilha | ASR geral | IC 95% | Filtro agiu | Respostas em cache |
| --- | --- | --- | --- | --- |
| L0 | 40/40 (100%) | 91–100% | 0 | 0 |
| L1 | 40/40 (100%) | 91–100% | 0 | 0 |
| L2 | 8/40 (20%) | 10–35% | 0 | 0 |
| L3 | 8/40 (20%) | 10–35% | 0 | 0 |
| L4 | 4/40 (10%) | 4–23% | 4 | 0 |

Cada célula conta tentativas com detector positivo após todas as camadas ativas da pilha. `retrieval_hit` mostra se o documento envenenado chegou ao contexto: sem ele, a tentativa não exercita a injeção e o número correspondente precisa ser lido com ressalva.
