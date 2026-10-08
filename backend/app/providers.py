"""Builds LangChain chat and embedding models for the configured provider.

Ollama is the default and needs no API key. OpenAI and Gemini are imported lazily and
only when selected, so the app starts without their keys.
"""

from __future__ import annotations

from langchain_core.embeddings import Embeddings
from langchain_core.language_models import BaseChatModel

from app.config import Settings


class ProviderConfigError(RuntimeError):
    """Raised when a provider is selected but not configured correctly."""


def _require(secret, name: str, provider: str) -> str:
    if secret is None or not secret.get_secret_value().strip():
        raise ProviderConfigError(f"{name} must be set to use the '{provider}' provider")
    return secret.get_secret_value()


def build_chat_model(settings: Settings, *, temperature: float | None = None) -> BaseChatModel:
    provider = settings.llm_provider
    model = settings.resolved_llm_model
    temp = settings.llm_temperature if temperature is None else temperature

    if provider == "ollama":
        from langchain_ollama import ChatOllama

        return ChatOllama(model=model, base_url=settings.ollama_base_url, temperature=temp)
    if provider == "openai":
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=model,
            temperature=temp,
            api_key=_require(settings.openai_api_key, "OPENAI_API_KEY", provider),
            base_url=settings.openai_base_url,
        )
    if provider == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI

        return ChatGoogleGenerativeAI(
            model=model,
            temperature=temp,
            google_api_key=_require(settings.google_api_key, "GOOGLE_API_KEY", provider),
        )
    raise ProviderConfigError(f"Unknown LLM provider: {provider}")


class _DimensionCheckedEmbeddings(Embeddings):
    """Wraps an embedding model and fails loudly if vectors do not match EMBEDDING_DIM."""

    def __init__(self, inner: Embeddings, dim: int) -> None:
        self.inner = inner
        self.dim = dim

    def _check(self, vectors: list[list[float]]) -> list[list[float]]:
        for v in vectors:
            if len(v) != self.dim:
                raise ProviderConfigError(
                    f"Embedding model returned {len(v)} dimensions but EMBEDDING_DIM={self.dim}. "
                    "Set EMBEDDING_DIM to the model's output size (and recreate the database)."
                )
        return vectors

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._check(self.inner.embed_documents(texts))

    def embed_query(self, text: str) -> list[float]:
        return self._check([self.inner.embed_query(text)])[0]


class _GeminiEmbeddings(Embeddings):
    """Requests EMBEDDING_DIM-sized vectors (gemini-embedding-001 defaults to 3072, which is
    above pgvector's 2000-dimension index limit)."""

    def __init__(self, inner, dim: int) -> None:
        self.inner = inner
        self.dim = dim

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self.inner.embed_documents(texts, output_dimensionality=self.dim)

    def embed_query(self, text: str) -> list[float]:
        return self.inner.embed_query(text, output_dimensionality=self.dim)


def build_embeddings(settings: Settings) -> Embeddings:
    provider = settings.embedding_provider
    model = settings.resolved_embedding_model

    if provider == "ollama":
        from langchain_ollama import OllamaEmbeddings

        inner: Embeddings = OllamaEmbeddings(model=model, base_url=settings.ollama_base_url)
    elif provider == "openai":
        from langchain_openai import OpenAIEmbeddings

        inner = OpenAIEmbeddings(
            model=model,
            # text-embedding-3-* models can shorten their output to the configured size.
            dimensions=settings.embedding_dim if model.startswith("text-embedding-3") else None,
            api_key=_require(settings.openai_api_key, "OPENAI_API_KEY", provider),
            base_url=settings.openai_base_url,
        )
    elif provider == "gemini":
        from langchain_google_genai import GoogleGenerativeAIEmbeddings

        inner = _GeminiEmbeddings(
            GoogleGenerativeAIEmbeddings(
                model=model,
                google_api_key=_require(settings.google_api_key, "GOOGLE_API_KEY", provider),
            ),
            settings.embedding_dim,
        )
    else:
        raise ProviderConfigError(f"Unknown embedding provider: {provider}")

    return _DimensionCheckedEmbeddings(inner, settings.embedding_dim)
