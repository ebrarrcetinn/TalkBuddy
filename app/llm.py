# Claude ile konuşan katman: talimatı ve sohbeti gönderir, cevabı metin olarak döndürür.
from typing import Protocol

from anthropic import Anthropic


# Sözleşme: "complete" fonksiyonu olan her şey LLM olarak kullanılabilir.
# Koç sadece bunu tanır; testlerde gerçek Claude yerine sahte bir LLM verilebilir.
class LLMClient(Protocol):
    def complete(self, system: str, messages: list[dict[str, str]], context: str = "") -> str: ...


# Sözleşmenin gerçek Claude ile uygulanmış hâli.
class AnthropicClient:
    # Bağlantıyı bir kez kurar; model adını ve cevap uzunluğu sınırını saklar.
    def __init__(self, model: str, api_key: str | None = None, max_tokens: int = 1024):
        self._client = Anthropic(api_key=api_key)
        self._model = model
        self._max_tokens = max_tokens

    # system: koçun değişmeyen talimatları, context: her mesajda değişen oturum bilgisi,
    # messages: sohbetin tamamı (user/assistant sırayla).
    # Uzun talimat metni önbelleğe alınır; sonraki mesajlarda yeniden işlenmediği için
    # cevap daha hızlı gelir.
    def complete(self, system: str, messages: list[dict[str, str]], context: str = "") -> str:
        blocks = [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}]
        if context:
            blocks.append({"type": "text", "text": context})
        response = self._client.messages.create(
            model=self._model,
            max_tokens=self._max_tokens,
            system=blocks,
            messages=messages,
        )
        # Cevap bloklar hâlinde gelir; metin bloklarını birleştirip tek metin döndürür.
        return "".join(block.text for block in response.content if block.type == "text")
