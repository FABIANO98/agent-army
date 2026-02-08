"""Shared LLM Service for Claude API integration."""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any, Optional

from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type


class LLMService:
    """
    Shared Claude API service for all agents.

    Features:
    - Async Anthropic client
    - Rate limiting via semaphore + token bucket
    - Token usage tracking per agent
    - Retry with exponential backoff
    - Structured JSON responses
    """

    def __init__(
        self,
        api_key: str,
        default_model: str = "claude-sonnet-4-5-20250929",
        fast_model: str = "claude-haiku-4-5-20251001",
        max_concurrent: int = 5,
        requests_per_minute: int = 50,
    ) -> None:
        self._api_key = api_key
        self._default_model = default_model
        self._fast_model = fast_model
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._requests_per_minute = requests_per_minute
        self._token_bucket_tokens = float(requests_per_minute)
        self._token_bucket_max = float(requests_per_minute)
        self._token_bucket_rate = requests_per_minute / 60.0
        self._token_bucket_last = time.monotonic()
        self._usage: dict[str, dict[str, int]] = {}
        self._client: Any = None
        self._logger = logger.bind(component="LLMService")

    async def initialize(self) -> None:
        """Initialize the Anthropic client."""
        try:
            import anthropic
            self._client = anthropic.AsyncAnthropic(api_key=self._api_key)
            self._logger.info("LLM Service initialized")
        except ImportError:
            self._logger.warning("anthropic package not installed - LLM features disabled")
        except Exception as e:
            self._logger.warning(f"Failed to initialize LLM service: {e}")

    @property
    def is_available(self) -> bool:
        """Check if the LLM service is available."""
        return self._client is not None and bool(self._api_key)

    async def _wait_for_token(self) -> None:
        """Token bucket rate limiting."""
        while True:
            now = time.monotonic()
            elapsed = now - self._token_bucket_last
            self._token_bucket_tokens = min(
                self._token_bucket_max,
                self._token_bucket_tokens + elapsed * self._token_bucket_rate,
            )
            self._token_bucket_last = now

            if self._token_bucket_tokens >= 1.0:
                self._token_bucket_tokens -= 1.0
                return

            await asyncio.sleep(0.1)

    def _track_usage(self, agent_id: str, input_tokens: int, output_tokens: int) -> None:
        """Track token usage per agent."""
        if agent_id not in self._usage:
            self._usage[agent_id] = {"input_tokens": 0, "output_tokens": 0, "requests": 0}
        self._usage[agent_id]["input_tokens"] += input_tokens
        self._usage[agent_id]["output_tokens"] += output_tokens
        self._usage[agent_id]["requests"] += 1

    def get_usage(self, agent_id: Optional[str] = None) -> dict[str, Any]:
        """Get token usage stats."""
        if agent_id:
            return self._usage.get(agent_id, {"input_tokens": 0, "output_tokens": 0, "requests": 0})
        return dict(self._usage)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        retry=retry_if_exception_type(Exception),
        reraise=True,
    )
    async def complete(
        self,
        prompt: str,
        system: str = "",
        model: Optional[str] = None,
        agent_id: str = "unknown",
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> str:
        """
        Get a text completion from Claude.

        Args:
            prompt: User prompt
            system: System prompt
            model: Model to use (defaults to default_model)
            agent_id: Agent ID for usage tracking
            max_tokens: Maximum tokens in response
            temperature: Sampling temperature

        Returns:
            Text response from Claude
        """
        if not self._client:
            raise RuntimeError("LLM service not initialized")

        await self._wait_for_token()

        async with self._semaphore:
            messages = [{"role": "user", "content": prompt}]
            kwargs: dict[str, Any] = {
                "model": model or self._default_model,
                "max_tokens": max_tokens,
                "messages": messages,
                "temperature": temperature,
            }
            if system:
                kwargs["system"] = system

            response = await self._client.messages.create(**kwargs)

            input_tokens = response.usage.input_tokens
            output_tokens = response.usage.output_tokens
            self._track_usage(agent_id, input_tokens, output_tokens)

            self._logger.debug(
                f"LLM call for {agent_id}: {input_tokens}in/{output_tokens}out tokens"
            )

            return response.content[0].text

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        retry=retry_if_exception_type(Exception),
        reraise=True,
    )
    async def complete_structured(
        self,
        prompt: str,
        system: str = "",
        response_schema: Optional[dict[str, Any]] = None,
        model: Optional[str] = None,
        agent_id: str = "unknown",
        max_tokens: int = 4096,
        temperature: float = 0.3,
    ) -> dict[str, Any]:
        """
        Get a structured JSON response from Claude.

        Args:
            prompt: User prompt (should describe expected JSON format)
            system: System prompt
            response_schema: Description of expected JSON structure
            model: Model to use
            agent_id: Agent ID for usage tracking
            max_tokens: Maximum tokens
            temperature: Sampling temperature

        Returns:
            Parsed JSON dict from Claude
        """
        schema_instruction = ""
        if response_schema:
            schema_instruction = f"\n\nRespond with valid JSON matching this schema:\n{json.dumps(response_schema, indent=2)}"

        full_system = (system or "") + schema_instruction + "\n\nIMPORTANT: Respond ONLY with valid JSON. No markdown, no explanation."

        text = await self.complete(
            prompt=prompt,
            system=full_system,
            model=model,
            agent_id=agent_id,
            max_tokens=max_tokens,
            temperature=temperature,
        )

        # Parse JSON from response, handling potential markdown wrapping
        text = text.strip()
        if text.startswith("```json"):
            text = text[7:]
        if text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # Try to find JSON in the response
            start = text.find("{")
            end = text.rfind("}") + 1
            if start >= 0 and end > start:
                return json.loads(text[start:end])
            raise

    async def complete_fast(
        self,
        prompt: str,
        system: str = "",
        agent_id: str = "unknown",
        max_tokens: int = 2048,
    ) -> str:
        """Quick completion using the fast model."""
        return await self.complete(
            prompt=prompt,
            system=system,
            model=self._fast_model,
            agent_id=agent_id,
            max_tokens=max_tokens,
        )
