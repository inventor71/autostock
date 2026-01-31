"""LLM API client abstraction for Claude and OpenAI."""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from typing import Any

from loguru import logger


class BaseLLMClient(ABC):
    """Abstract base class for LLM API clients."""

    def __init__(self, api_key: str, model: str | None = None, temperature: float = 0.3):
        self.api_key = api_key
        self.model = model or self.default_model
        self.temperature = temperature
        self._validate_api_key()

    @property
    @abstractmethod
    def default_model(self) -> str:
        """Default model identifier for this provider."""
        pass

    @abstractmethod
    def _validate_api_key(self) -> None:
        """Validate that API key is present."""
        pass

    @abstractmethod
    def complete(
        self,
        system_prompt: str,
        user_message: str,
        max_tokens: int = 1024,
    ) -> str:
        """Send a completion request and return the response text.

        Args:
            system_prompt: System prompt for context.
            user_message: User message with market data.
            max_tokens: Maximum tokens in response.

        Returns:
            The LLM's response text.
        """
        pass

    def _retry_with_backoff(
        self,
        func: callable,
        max_retries: int = 3,
        base_delay: float = 1.0,
    ) -> Any:
        """Execute function with exponential backoff on failure."""
        last_exception = None
        for attempt in range(max_retries):
            try:
                return func()
            except Exception as e:
                last_exception = e
                if attempt < max_retries - 1:
                    delay = base_delay * (2 ** attempt)
                    logger.warning(f"LLM API error (attempt {attempt + 1}): {e}. Retrying in {delay}s...")
                    time.sleep(delay)
                else:
                    logger.error(f"LLM API failed after {max_retries} attempts: {e}")
        raise last_exception


class ClaudeClient(BaseLLMClient):
    """Anthropic Claude API client."""

    @property
    def default_model(self) -> str:
        return "claude-sonnet-4-20250514"

    def _validate_api_key(self) -> None:
        if not self.api_key:
            raise ValueError("ANTHROPIC_API_KEY is required for Claude client")

    def complete(
        self,
        system_prompt: str,
        user_message: str,
        max_tokens: int = 1024,
    ) -> str:
        import anthropic

        client = anthropic.Anthropic(api_key=self.api_key)

        def _call():
            response = client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                temperature=self.temperature,
                system=system_prompt,
                messages=[{"role": "user", "content": user_message}],
            )
            return response.content[0].text

        return self._retry_with_backoff(_call)


class OpenAIClient(BaseLLMClient):
    """OpenAI API client."""

    @property
    def default_model(self) -> str:
        return "gpt-4o"

    def _validate_api_key(self) -> None:
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY is required for OpenAI client")

    def complete(
        self,
        system_prompt: str,
        user_message: str,
        max_tokens: int = 1024,
    ) -> str:
        from openai import OpenAI

        client = OpenAI(api_key=self.api_key)

        def _call():
            response = client.chat.completions.create(
                model=self.model,
                max_tokens=max_tokens,
                temperature=self.temperature,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message},
                ],
            )
            return response.choices[0].message.content

        return self._retry_with_backoff(_call)


def create_llm_client(
    provider: str,
    api_key: str,
    model: str | None = None,
    temperature: float = 0.3,
) -> BaseLLMClient:
    """Factory function to create an LLM client.

    Args:
        provider: Either "claude" or "openai".
        api_key: API key for the provider.
        model: Optional model override.
        temperature: Sampling temperature (default 0.3).

    Returns:
        Configured LLM client instance.

    Raises:
        ValueError: If provider is not supported.
    """
    providers = {
        "claude": ClaudeClient,
        "openai": OpenAIClient,
    }

    if provider not in providers:
        raise ValueError(f"Unsupported LLM provider: {provider}. Choose from: {list(providers.keys())}")

    return providers[provider](api_key=api_key, model=model, temperature=temperature)
