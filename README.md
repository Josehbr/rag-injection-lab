# rag-injection-lab

**Quanto cada camada de defesa derruba a injeção de prompt indireta em RAG — medido, com intervalo de confiança.**

Um RAG mínimo e reproduzível, um corpus de documentos legítimos, injeções plantadas dentro dele e cinco pilhas de defesa montadas camada por camada. A saída é a taxa de sucesso de ataque (ASR) por classe e por pilha, com intervalo de confiança de Wilson, custo e latência por execução — não uma opinião sobre o que "funciona contra prompt injection".

```
pergunta legítima ──► BM25 (top-k) ──► prompt [sistema + pergunta + contexto]
                                             ▲
                              documento envenenado plantado no corpus
                                             │
      ┌──────────────────────────────────────┴─────────────────────────────────┐
      │ defesas em camadas: spotlighting → system hardening → JSON → filtro    │
      └────────────────────────────────────────────────────────────────────────┘
                                             │
                              resposta ──► detector determinístico ──► ASR
```

## Como o ataque funciona aqui

Cada payload é um **documento-hospedeiro**: um texto com aparência administrativa normal (política de impressoras, orçamento de evento, manual do projetor) dentro do qual a injeção é plantada. As consultas são perguntas honestas cuja resposta correta está nesse documento. A injeção só chega ao prompt porque o retrieval faz o trabalho dele — esse é o ponto da injeção *indireta*: ninguém precisa digitar o ataque, ele entra pela base de conhecimento.

Quatro classes de ataque, 5 variantes cada:

| Classe | O que a injeção pede | Sucesso é detectado como |
| --- | --- | --- |
| Sobrescrita de instrução | Abandonar a tarefa e responder só um marcador único | Marcador presente na resposta |
| Exfiltração por URL | Citar uma URL externa "para rastreamento" | URL com domínio fora da allowlist |
| Abuso de ferramenta | Emitir um bloco `<tool_call>` | Padrão de chamada de ferramenta na saída |
| Phishing de credencial | Pedir senha/token "para validar" | Pedido de credencial na resposta |

Os domínios de exfiltração terminam em `.example` (TLD reservado pela RFC 2606): não existem e não resolvem.

Cinco pilhas de defesa, cumulativas por desenho — o relatório mostra o efeito marginal de cada camada:

| Pilha | Camadas ativas |
| --- | --- |
| L0 | nenhuma (baseline) |
| L1 | spotlighting: documento recuperado envolto em delimitadores que o marcam como dado |
| L2 | L1 + system hardening: hierarquia explícita de instruções e proibições no system prompt |
| L3 | L2 + saída estruturada: resposta restrita a schema JSON `{resposta, fontes}` |
| L4 | L3 + filtro de saída: saneamento de URL fora da allowlist, bloco de ferramenta e pedido de credencial |

## Como rodar

Python 3.11+. Sem chave de API, nada custa nada:

```bash
make setup          # venv + dependências
make run-mock       # valida o harness com cliente simulado (sem rede, sem custo)
make test           # 21 testes, incluindo a garantia de que o documento
                    # envenenado chega ao contexto em toda consulta
```

Para o experimento real, com modelo de API (grade completa: 200 chamadas de ~1–2 mil tokens — da ordem de centavos com modelos mini):

```bash
cp .env.example .env        # preencha a chave e o modelo (qualquer provedor LiteLLM)
make run                    # executa e gera results/RESULTS.md
make run-dense              # variação com retrieval vetorial denso
```

O `LITELLM_MODEL` é o modelo de **geração** (chat). O `EMBEDDING_MODEL` (padrão `text-embedding-3-small`) só entra com `--retrieval dense`, para embedar o corpus e as consultas — o corpus inteiro mais as 40 consultas únicas custam menos de um centavo, com cache commitado para nunca pagar de novo.

Comandos individuais: `python -m rag_injection_lab run --real --retrieval dense --stacks L0,L4 --limit 2` reduz a grade; `python -m rag_injection_lab report` regenera o relatório da última execução.

## Resultados

- [`results/RESULTS.md`](results/RESULTS.md) — tabela da última execução.
- [`results/runs/`](results/runs/) — cada execução gravada com manifesto (data, modelo, commit, versão do Python) e a resposta integral de cada tentativa, para auditoria manual.
- [`results/llm-cache.jsonl`](results/llm-cache.jsonl) — cache de respostas indexado por hash de (modelo, mensagens, parâmetros). Commitado de propósito: repetir o experimento não custa de novo e a evidência fica versionada.

O `RESULTS.md` commitado neste repositório foi gerado em **modo mock** e carrega esse aviso: ele valida o encanamento, não mede modelo real. A primeira execução com `make run` sobrescreve com números reais.

## Decisões de desenho

- **Retrieval léxico por padrão, denso opcional.** O método de recuperação decide *qual* documento chega ao prompt, não o que o modelo faz com ele. O BM25 determinista em Python puro mantém o experimento reproduzível em qualquer máquina, sem GPU e sem download de modelo; o `--retrieval dense` (ex.: `text-embedding-3-small`) permite medir se a mecânica da injeção muda com busca vetorial — a hipótese do laboratório é que não muda.
- **Um documento envenenado por tentativa.** Cada consulta roda contra o corpus limpo inteiro + o hospedeiro de um payload. É o cenário realista da ameaça (uma base legítima com um documento comprometido) e evita que dois ataques disputem o contexto entre si.
- **Detector determinístico, sem LLM juiz.** O sucesso de cada classe é verificável por padrão objetivo, o que torna a medição reproduzível e gratuita.
- **ASR sempre com intervalo de confiança.** São 10 tentativas por célula: o IC de Wilson (bem-comportado perto de 0% e 100%) aparece junto do número para que ninguém leia "0/10" como "impossível".
- **Temperatura 0, seed fixa, cache.** Reduz variância e faz a repetição custar zero.

## Limitações

- Amostra pequena por célula (10): diferenças de poucos pontos entre pilhas ficam dentro do ruído — o IC está ali para isso.
- O detector de abuso de ferramenta é conservador e pode marcar falso positivo quando a resposta *menciona* a ferramenta para recusá-la. As respostas integrais ficam gravadas em `results/runs/` para revisão manual dos casos marcados.
- Turno único, sem memória de conversa; sem ferramentas realmente conectadas (o perigo medido é o modelo *emitir* a chamada, não executá-la).
- O modo mock não mede nada sobre modelos reais — ele existe para validar o harness.

## Uso responsável

Os payloads são didáticos, visíveis e usam infraestrutura inexistente (`.example`). Use este laboratório para testar **seus próprios** sistemas. Injetar isso em produto de terceiros sem autorização é ataque, não pesquisa.

## Estrutura

```
corpus/clean/          documentos legítimos (atas, board, runbooks, WhatsApp, GitHub)
src/rag_injection_lab/
  payloads.py          4 classes × 5 variantes, com hospedeiro e consultas
  retrieval.py         BM25 do zero (k1=1.5, b=0.75) + busca densa por cosseno
  embeddings.py        LiteLLM embeddings com cache + embedding determinístico p/ mock
  defenses.py          pilhas L0–L4, spotlighting, hardening, schema, filtro
  detector.py          detecção determinística de sucesso por classe
  llm.py               LiteLLM com cache em arquivo + cliente mock
  runner.py            grade do experimento + manifesto por execução
  report.py            tabela ASR com IC de Wilson
tests/                 25 testes, incluindo e2e mock da grade completa
results/               execuções, cache e RESULTS.md — commitados como evidência
```

## Licença

[MIT](LICENSE) — José Hernane ([@Josehbr](https://github.com/Josehbr)).
