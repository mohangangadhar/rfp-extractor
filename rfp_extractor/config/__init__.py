"""Configuration management"""

import json
import os
from pathlib import Path
from typing import Optional

import tomli
from pydantic import BaseModel

from rfp_extractor.models import LLMConfig, LLMProvider


class Settings(BaseModel):
    """Application settings loaded from config file + environment"""
    llm_provider: str = "openai"
    llm_model: str = "gpt-4o"
    llm_api_key: Optional[str] = None
    llm_base_url: Optional[str] = None
    llm_temperature: float = 0.0
    llm_max_tokens: int = 8192
    chunk_size: int = 8000
    chunk_overlap: int = 500
    min_confidence: float = 0.5
    extract_tables: bool = True
    extract_footnotes: bool = True
    extract_appendices: bool = True
    parallel_chunks: bool = False
    max_parallel: int = 3

    @classmethod
    def load(cls, config_path: Optional[Path] = None) -> "Settings":
        """Load settings from config file and environment"""
        settings = cls()

        # Load from config file
        if config_path and config_path.exists():
            with open(config_path, "rb") as f:
                data = tomli.load(f)
            for key, value in data.items():
                if hasattr(settings, key):
                    setattr(settings, key, value)

        # Environment variables override (case-insensitive)
        env_map = {
            "LLM_PROVIDER": "llm_provider",
            "LLM_MODEL": "llm_model",
            "LLM_API_KEY": "llm_api_key",
            "LLM_BASE_URL": "llm_base_url",
            "LLM_TEMPERATURE": "llm_temperature",
            "LLM_MAX_TOKENS": "llm_max_tokens",
            "CHUNK_SIZE": "chunk_size",
            "CHUNK_OVERLAP": "chunk_overlap",
            "MIN_CONFIDENCE": "min_confidence",
        }
        for env_key, attr in env_map.items():
            if env_key in os.environ:
                value = os.environ[env_key]
                current = getattr(settings, attr)
                if isinstance(current, bool):
                    value = value.lower() in ("true", "1", "yes")
                elif isinstance(current, int):
                    value = int(value)
                elif isinstance(current, float):
                    value = float(value)
                setattr(settings, attr, value)

        return settings

    def to_llm_config(self) -> LLMConfig:
        """Convert to LLMConfig"""
        return LLMConfig(
            provider=LLMProvider(self.llm_provider),
            model=self.llm_model,
            api_key=self.llm_api_key,
            base_url=self.llm_base_url,
            temperature=self.llm_temperature,
            max_tokens=self.llm_max_tokens,
        )

    def save(self, config_path: Path):
        """Save settings to config file"""
        import tomli_w
        data = self.model_dump(exclude_none=True)
        with open(config_path, "wb") as f:
            tomli_w.dump(data, f)


def find_config() -> Optional[Path]:
    """Search for config file in common locations"""
    candidates = [
        Path("rfp_extractor.toml"),
        Path("config.toml"),
        Path("~/.config/rfp_extractor/config.toml").expanduser(),
        Path.home() / ".config" / "rfp_extractor" / "config.toml",
    ]
    for p in candidates:
        if p.exists():
            return p
    return None