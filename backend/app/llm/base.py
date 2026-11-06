from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import AsyncIterator, Optional


@dataclass
class LLMMessage:
    role: str
    content: str


@dataclass
class LLMResponse:
    content: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    model: str = ""


class LLMProvider(ABC):
    @abstractmethod
    async def complete(
        self,
        messages: list[LLMMessage],
        *,
        max_tokens: Optional[int] = None,
        temperature: float = 0.2,
    ) -> LLMResponse:
        raise NotImplementedError

    @abstractmethod
    async def stream(
        self,
        messages: list[LLMMessage],
        *,
        max_tokens: Optional[int] = None,
        temperature: float = 0.2,
    ) -> AsyncIterator[str]:
        raise NotImplementedError
        yield  # pragma: no cover
