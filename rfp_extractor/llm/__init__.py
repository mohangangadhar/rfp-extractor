"""LLM client abstraction layer"""

from __future__ import annotations

import json
import logging
import os
import time
from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel

from rfp_extractor.models import LLMConfig, LLMProvider

logger = logging.getLogger(__name__)


class LLMClient(ABC):
    """Abstract LLM client"""

    def __init__(self, config: LLMConfig):
        self.config = config

    @abstractmethod
    def complete(self, messages: list[dict[str, str]]) -> LLMResponse:
        """Complete a chat conversation"""
        pass

    def complete_with_retry(self, messages: list[dict[str, str]], max_retries: int | None = None) -> LLMResponse:
        """Complete with retry logic"""
        retries = max_retries or self.config.max_retries
        last_error = None

        for attempt in range(retries):
            try:
                return self.complete(messages)
            except Exception as e:
                last_error = e
                wait_time = 2 ** attempt  # exponential backoff
                logger.warning(f"LLM call failed (attempt {attempt + 1}/{retries}): {e}. Retrying in {wait_time}s...")
                time.sleep(wait_time)

        raise last_error


class LLMResponse(BaseModel):
    """Standardized LLM response"""
    content: str
    usage: dict[str, int] = {}


class OpenAIClient(LLMClient):
    """OpenAI API client"""

    def __init__(self, config: LLMConfig):
        super().__init__(config)
        try:
            from openai import OpenAI
            self.client = OpenAI(
                api_key=config.api_key or os.getenv("OPENAI_API_KEY"),
                base_url=config.base_url,
                timeout=config.timeout,
                max_retries=0  # We handle retries ourselves
            )
        except ImportError:
            raise ImportError("openai package not installed. Install with: pip install openai")

    def complete(self, messages: list[dict[str, str]]) -> LLMResponse:
        response = self.client.chat.completions.create(
            model=self.config.model,
            messages=messages,
            temperature=self.config.temperature,
            max_tokens=self.config.max_tokens,
            response_format={"type": "json_object"}
        )

        return LLMResponse(
            content=response.choices[0].message.content or "",
            usage={
                "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
                "completion_tokens": response.usage.completion_tokens if response.usage else 0,
                "total_tokens": response.usage.total_tokens if response.usage else 0,
            }
        )


class AnthropicClient(LLMClient):
    """Anthropic API client"""

    def __init__(self, config: LLMConfig):
        super().__init__(config)
        try:
            import anthropic
            self.client = anthropic.Anthropic(
                api_key=config.api_key or os.getenv("ANTHROPIC_API_KEY"),
                timeout=config.timeout,
                max_retries=0
            )
        except ImportError:
            raise ImportError("anthropic package not installed. Install with: pip install anthropic")

    def complete(self, messages: list[dict[str, str]]) -> LLMResponse:
        # Convert messages to Anthropic format
        system_prompt = ""
        user_messages = []

        for msg in messages:
            if msg["role"] == "system":
                system_prompt = msg["content"]
            else:
                user_messages.append({"role": msg["role"], "content": msg["content"]})

        response = self.client.messages.create(
            model=self.config.model,
            system=system_prompt,
            messages=user_messages,
            temperature=self.config.temperature,
            max_tokens=self.config.max_tokens,
        )

        content = ""
        if response.content:
            for block in response.content:
                if block.type == "text":
                    content += block.text

        return LLMResponse(
            content=content,
            usage={
                "prompt_tokens": response.usage.input_tokens if response.usage else 0,
                "completion_tokens": response.usage.output_tokens if response.usage else 0,
                "total_tokens": (response.usage.input_tokens + response.usage.output_tokens) if response.usage else 0,
            }
        )


class GeminiClient(LLMClient):
    """Google Gemini API client"""

    def __init__(self, config: LLMConfig):
        super().__init__(config)
        try:
            from google import genai
            self.client = genai.Client(
                api_key=config.api_key or os.getenv("GEMINI_API_KEY"),
                http_options={"timeout": config.timeout * 1000},
            )
        except ImportError:
            raise ImportError("google-genai package not installed. Install with: pip install google-genai")

    def complete(self, messages: list[dict[str, str]]) -> LLMResponse:
        from google.genai import types

        # Extract system instruction
        system_instruction = None
        contents = []
        for msg in messages:
            if msg["role"] == "system":
                system_instruction = msg["content"]
            else:
                contents.append(msg["content"])

        prompt = "\n\n".join(contents) if contents else ""

        config_kwargs = {
            "temperature": self.config.temperature,
            "max_output_tokens": self.config.max_tokens,
        }
        if system_instruction:
            config_kwargs["system_instruction"] = system_instruction

        # Gemini 3 models support adjustable thinking depth
        if self.config.thinking_level:
            config_kwargs["thinking_config"] = types.ThinkingConfig(
                include_thoughts=self.config.thinking_level != "minimal"
            )

        response = self.client.models.generate_content(
            model=self.config.model,
            contents=prompt,
            config=types.GenerateContentConfig(**config_kwargs),
        )

        return LLMResponse(
            content=response.text or "",
            usage={
                "prompt_tokens": response.usage_metadata.prompt_token_count if response.usage_metadata else 0,
                "completion_tokens": response.usage_metadata.candidates_token_count if response.usage_metadata else 0,
                "total_tokens": response.usage_metadata.total_token_count if response.usage_metadata else 0,
            }
        )


def create_llm_client(config: LLMConfig) -> LLMClient:
    """Factory function to create LLM client"""
    if config.provider == LLMProvider.OPENAI:
        return OpenAIClient(config)
    elif config.provider == LLMProvider.ANTHROPIC:
        return AnthropicClient(config)
    elif config.provider == LLMProvider.GEMINI:
        return GeminiClient(config)
    else:
        raise ValueError(f"Unsupported provider: {config.provider}")