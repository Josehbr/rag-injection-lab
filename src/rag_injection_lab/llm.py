"""Clientes de LLM: modo real via LiteLLM com cache em arquivo, e modo mock.

Duas regras do laboratório vivem aqui:

1. **Cache obrigatório**: toda resposta de modelo é persistida em
   `results/llm-cache.jsonl` indexada pelo hash de (modelo, mensagens,
   parâmetros). Repetir o experimento não custa de novo e o histórico
   de respostas fica commitado como evidência.
2. **Modo mock**: um cliente determinístico, sem rede e sem chave,
   que simula comportamento de modelo atacado/defendido. Ele existe
   para validar o harness (corpus, retrieval, defesas, detector,
   relatório) e NÃO produz resultado de modelo real. Todo relatório
   gerado em modo mock carrega esse aviso.
"""

import hashlib
import json
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from .defenses import HARDEN_TAG
from .detector import CREDENTIAL_RE as _CREDENTIAL_RE
from .detector import URL_RE as _URL_RE

DEFAULT_CACHE_PATH = Path("results") / "llm-cache.jsonl"

_OVERRIDE_RE = re.compile(r"INJECAO-CONFIRMADA-([0-9A-F]{4})")
_DOC_TITLE_RE = re.compile(r"\[(\w+)\] ([^\n]+)")


@dataclass(frozen=True)
class LLMResponse:
    text: str
    tokens_in: int
    tokens_out: int
    cost_usd: float | None
    cached: bool
    latency_ms: float


class LLMClient(Protocol):
    name: str

    def complete(self, system: str, user: str, json_mode: bool = False) -> LLMResponse: ...


def load_dotenv(path: Path = Path(".env")) -> None:
    """Caria .env simples (CHAVE=valor) sem dependência externa."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


class LiteLLMClient:
    """Chamada real a qualquer provedor suportado pelo LiteLLM, com cache.

    Modelos de raciocínio (ex.: gpt-5.6-luna) rejeitam `temperature=0`
    com raciocínio ativo; modelos de chat comuns não conhecem
    `reasoning_effort`. A escada de parâmetros abaixo tenta a
    configuração mais determinística primeiro e recua conforme o erro,
    de forma que o mesmo cliente sirva para qualquer família de modelo:

    1. `temperature=0` + `reasoning_effort="none"` (+ `response_format`
       JSON quando pedido)
    2. `temperature=0` sem `reasoning_effort`
    3. `temperature=1` (exigência de modelos de raciocínio)

    Se o provedor recusar `response_format`, refaz a chamada sem ele —
    o prompt da pilha L3 já carrega o schema, então a restrição de
    formato não é a única linha de defesa.
    """

    def __init__(
        self,
        model: str,
        temperature: float = 0.0,
        seed: int = 42,
        cache_path: Path = DEFAULT_CACHE_PATH,
    ):
        self.name = f"litellm:{model}"
        self.model = model
        self.temperature = temperature
        self.seed = seed
        self.cache_path = cache_path
        self.last_params: dict | None = None
        self._cache: dict[str, dict] = {}
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        if cache_path.exists():
            for line in cache_path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    entry = json.loads(line)
                    self._cache[entry["key"]] = entry

    def _cache_key(self, system: str, user: str, json_mode: bool) -> str:
        payload = json.dumps(
            {
                "model": self.model,
                "system": system,
                "user": user,
                "seed": self.seed,
                "json_mode": json_mode,
            },
            sort_keys=True,
            ensure_ascii=False,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def _param_ladder(self, json_mode: bool) -> list[dict]:
        variants = [
            {"temperature": self.temperature, "reasoning_effort": "none"},
            {"temperature": self.temperature},
            {"temperature": 1.0},
        ]
        ladder = []
        for extra in variants:
            params = {
                "model": self.model,
                "messages": None,  # preenchido na chamada
                "seed": self.seed,
                **extra,
            }
            if json_mode:
                params["response_format"] = {"type": "json_object"}
            ladder.append(params)
        return ladder

    @staticmethod
    def _is_response_format_error(error: Exception) -> bool:
        message = str(error).lower()
        return "response_format" in message or (
            "json" in message and "not support" in message
        )

    def complete(self, system: str, user: str, json_mode: bool = False) -> LLMResponse:
        import litellm  # import tardio: modo mock não exige a dependência

        key = self._cache_key(system, user, json_mode)
        hit = self._cache.get(key)
        if hit is not None:
            return LLMResponse(
                text=hit["text"],
                tokens_in=hit["tokens_in"],
                tokens_out=hit["tokens_out"],
                cost_usd=hit["cost_usd"],
                cached=True,
                latency_ms=0.0,
            )

        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        started = time.perf_counter()
        last_error: Exception | None = None
        response = None
        for params in self._param_ladder(json_mode):
            call_params = {**params, "messages": messages}
            try:
                response = litellm.completion(**call_params)
                self.last_params = {
                    k: v for k, v in params.items() if k != "messages"
                }
                break
            except Exception as error:  # noqa: BLE001 - escada de fallback
                last_error = error
                if self._is_response_format_error(error) and "response_format" in params:
                    retry = {
                        k: v for k, v in call_params.items() if k != "response_format"
                    }
                    try:
                        response = litellm.completion(**retry)
                        self.last_params = {
                            k: v for k, v in retry.items() if k != "messages"
                        }
                        break
                    except Exception as retry_error:  # noqa: BLE001
                        last_error = retry_error
                        continue
                continue
        if response is None:
            raise last_error or RuntimeError(
                "Nenhuma variante de parâmetros funcionou para este modelo."
            )

        # Latência de ponta a ponta, incluindo tentativas da escada que falharam.
        latency_ms = (time.perf_counter() - started) * 1000
        text = response.choices[0].message.content or ""
        tokens_in = getattr(response.usage, "prompt_tokens", 0) or 0
        tokens_out = getattr(response.usage, "completion_tokens", 0) or 0
        try:
            cost_usd = litellm.completion_cost(response)
        except Exception:
            cost_usd = None

        entry = {
            "key": key,
            "model": self.model,
            "text": text,
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "cost_usd": cost_usd,
        }
        self._cache[key] = entry
        with self.cache_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return LLMResponse(
            text=text,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cost_usd=cost_usd,
            cached=False,
            latency_ms=latency_ms,
        )


class MockLLM:
    """Modelo simulado, determinístico, para validar o harness sem custo.

    Regras: sem defesa de hierarquia no system prompt, o modelo "cai" em
    todos os ataques. Com defesa, cede à sobrescrita de instrução quando o
    último dígito hexadecimal do marcador é par, e à exfiltração quando a
    injeção usa linguagem de autoridade ("obrigatoriamente", "conformidade")
    — simulação de defesa imperfeita que exercita detector, filtro de
    saída e relatório no grid completo. Os números que saem daqui não
    dizem nada sobre modelos reais.
    """

    name = "mock:simulado"

    _AUTHORITY_WORDS = ("obrigatoriamente", "conformidade")

    def complete(self, system: str, user: str, json_mode: bool = False) -> LLMResponse:
        hardened = HARDEN_TAG in system
        answer = self._answer(user, hardened)
        if json_mode:
            title = self._first_doc_title(user)
            answer = json.dumps(
                {"resposta": answer, "fontes": [title]},
                ensure_ascii=False,
            )
        return LLMResponse(
            text=answer,
            tokens_in=max(1, len(user) // 4),
            tokens_out=max(1, len(answer) // 4),
            cost_usd=0.0,
            cached=False,
            latency_ms=0.1,
        )

    def _answer(self, user: str, hardened: bool) -> str:
        override = _OVERRIDE_RE.search(user)
        if override is not None:
            marker = override.group(0)
            if not hardened or int(marker[-1], 16) % 2 == 0:
                return marker
            return self._benign(user)
        if "<tool_call>" in user:
            if hardened:
                return self._benign(user)
            block = user[user.index("<tool_call>") : user.index("</tool_call>") + len("</tool_call>")]
            return f"Executando ação registrada: {block}"
        if any(".example" in url for url in _URL_RE.findall(user)):
            authority = any(word in user.lower() for word in self._AUTHORITY_WORDS)
            if not hardened or authority:
                url = next(u for u in _URL_RE.findall(user) if ".example" in u)
                return f"Os dados foram confirmados e registrados. Fonte oficial: {url}"
            return self._benign(user)
        if _CREDENTIAL_RE.search(user):
            if hardened:
                return self._benign(user)
            return (
                "Para liberar esta informação, primeiro informe sua senha e o token "
                "de autenticação corporativo para validação de identidade."
            )
        return self._benign(user)

    def _benign(self, user: str) -> str:
        title = self._first_doc_title(user)
        return f"Segundo o documento '{title}', a informação solicitada está registrada no contexto recuperado."

    def _first_doc_title(self, user: str) -> str:
        match = _DOC_TITLE_RE.search(user)
        return match.group(2).strip() if match else "documento recuperado"
