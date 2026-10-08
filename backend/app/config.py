"""Application settings, loaded from environment variables (and an optional .env file)."""

from __future__ import annotations

import json
from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

Provider = Literal["ollama", "openai", "gemini"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_ignore_empty=True, extra="ignore")

    # --- Database ---------------------------------------------------------------------------
    database_url: str = "postgresql://documind:documind@localhost:5432/documind"
    db_pool_min_size: int = Field(default=1, ge=1)
    db_pool_max_size: int = Field(default=10, ge=1)
    db_connect_timeout: int = Field(default=5, ge=1, le=120)

    # --- Model providers --------------------------------------------------------------------
    llm_provider: Provider = "ollama"
    llm_model: str | None = None  # defaults depend on the provider, see `resolved_llm_model`
    llm_temperature: float = Field(default=0.1, ge=0, le=2)

    embedding_provider: Provider = "ollama"
    embedding_model: str | None = None
    # Must match the embedding model's output size. Changing it requires a fresh database.
    embedding_dim: int = Field(default=768, ge=8, le=2000)

    ollama_base_url: str = "http://localhost:11434"
    openai_api_key: SecretStr | None = None
    openai_base_url: str | None = None
    google_api_key: SecretStr | None = None

    # --- Ingestion --------------------------------------------------------------------------
    chunk_size: int = Field(default=800, ge=100, le=8000)
    chunk_overlap: int = Field(default=120, ge=0, le=2000)
    max_upload_mb: int = Field(default=20, ge=1, le=200)

    # --- Retrieval --------------------------------------------------------------------------
    vector_top_k: int = Field(default=20, ge=1, le=200)
    keyword_top_k: int = Field(default=20, ge=1, le=200)
    rrf_k: int = Field(default=60, ge=1)
    reranker: Literal["flashrank", "none"] = "flashrank"
    reranker_model: str = "ms-marco-MiniLM-L-12-v2"
    reranker_cache_dir: str = ".cache/flashrank"
    final_top_k: int = Field(default=5, ge=1, le=50)
    prompt_style: Literal["grounded", "basic"] = "grounded"

    # --- API --------------------------------------------------------------------------------
    cors_origins: Annotated[list[str], NoDecode] = ["http://localhost:5173"]
    log_level: str = "INFO"

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            if value.strip().startswith("["):
                return json.loads(value)
            return [o.strip() for o in value.split(",") if o.strip()]
        return value

    @model_validator(mode="after")
    def _check(self) -> Settings:
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError("CHUNK_OVERLAP must be smaller than CHUNK_SIZE")
        if self.db_pool_min_size > self.db_pool_max_size:
            raise ValueError("DB_POOL_MIN_SIZE cannot exceed DB_POOL_MAX_SIZE")
        return self

    @property
    def resolved_llm_model(self) -> str:
        defaults = {"ollama": "llama3.2", "openai": "gpt-4o-mini", "gemini": "gemini-2.5-flash"}
        return self.llm_model or defaults[self.llm_provider]

    @property
    def resolved_embedding_model(self) -> str:
        defaults = {
            "ollama": "nomic-embed-text",
            "openai": "text-embedding-3-small",
            "gemini": "models/gemini-embedding-001",
        }
        return self.embedding_model or defaults[self.embedding_provider]

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    return Settings()
