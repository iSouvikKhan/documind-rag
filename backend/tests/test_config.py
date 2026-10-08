from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.config import Settings
from app.providers import ProviderConfigError, build_chat_model, build_embeddings


def test_defaults_use_ollama_without_keys():
    s = Settings(_env_file=None)
    assert s.llm_provider == "ollama" and s.resolved_llm_model == "llama3.2"
    assert s.resolved_embedding_model == "nomic-embed-text"
    # Building Ollama clients does not contact the server.
    assert build_chat_model(s) is not None
    assert build_embeddings(s) is not None


def test_overlap_must_be_smaller_than_chunk_size():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, chunk_size=200, chunk_overlap=200)


@pytest.mark.parametrize("provider", ["openai", "gemini"])
def test_cloud_providers_require_keys(provider):
    s = Settings(_env_file=None, llm_provider=provider, embedding_provider=provider)
    with pytest.raises(ProviderConfigError, match="API_KEY"):
        build_chat_model(s)
    with pytest.raises(ProviderConfigError, match="API_KEY"):
        build_embeddings(s)


def test_openai_builds_with_key():
    s = Settings(
        _env_file=None,
        llm_provider="openai",
        embedding_provider="openai",
        openai_api_key="sk-test",
        embedding_dim=1536,
    )
    assert build_chat_model(s).model_name == "gpt-4o-mini"
    assert build_embeddings(s) is not None


def test_cors_origins_parsing(monkeypatch):
    monkeypatch.setenv("CORS_ORIGINS", "http://a.com, http://b.com")
    assert Settings(_env_file=None).cors_origins == ["http://a.com", "http://b.com"]


def test_embedding_dimension_check():
    from langchain_core.embeddings import DeterministicFakeEmbedding

    from app.providers import _DimensionCheckedEmbeddings

    checked = _DimensionCheckedEmbeddings(DeterministicFakeEmbedding(size=8), dim=16)
    with pytest.raises(ProviderConfigError, match="EMBEDDING_DIM"):
        checked.embed_query("hello")
