from __future__ import annotations

import math
import os
import random
import time
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from google import genai
from google.genai import types

from .models import normalize_query


PROJECT_ROOT = Path(__file__).resolve().parents[3]
ENV_PATH = PROJECT_ROOT / ".env"
MODEL_EXPECTED = "gemini-embedding-2"
DIMENSION_EXPECTED = 768


class QueryEmbeddingError(RuntimeError):
    pass


def format_query_for_embedding(query: str) -> str:
    return f"task: search result | query: {normalize_query(query)}"


def extract_embeddings(response: Any) -> list[list[Any]]:
    embeddings = getattr(response, "embeddings", None)
    if embeddings is not None:
        return [list(getattr(embedding, "values")) for embedding in embeddings]
    embedding = getattr(response, "embedding", None)
    if embedding is not None:
        return [list(getattr(embedding, "values"))]
    raise QueryEmbeddingError("No embedding values returned")


def validate_embedding_vector(vector: list[Any], dimension: int = DIMENSION_EXPECTED) -> list[float]:
    if not vector:
        raise QueryEmbeddingError("Embedding vector is empty")
    values = [float(value) for value in vector]
    if len(values) != dimension:
        raise QueryEmbeddingError(f"Embedding dimension is {len(values)}, expected {dimension}")
    if any(math.isnan(value) for value in values):
        raise QueryEmbeddingError("Embedding vector contains NaN")
    if any(math.isinf(value) for value in values):
        raise QueryEmbeddingError("Embedding vector contains Infinity")
    return values


class GeminiQueryEmbedder:
    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        dimension: int | None = None,
        client: Any | None = None,
        max_retries: int = 5,
    ) -> None:
        if api_key is None or model is None or dimension is None:
            load_dotenv(ENV_PATH)
        self.api_key = api_key or os.getenv("GEMINI_API_KEY", "").strip()
        self.model = model or os.getenv("GEMINI_EMBEDDING_MODEL", MODEL_EXPECTED).strip()
        self.dimension = dimension or int(os.getenv("GEMINI_EMBEDDING_DIMENSION", str(DIMENSION_EXPECTED)))
        self.max_retries = max_retries
        if max_retries < 1:
            raise ValueError("max_retries must be at least one")
        if not self.api_key:
            raise QueryEmbeddingError("GEMINI_API_KEY is missing")
        if self.model != MODEL_EXPECTED:
            raise QueryEmbeddingError(f"GEMINI_EMBEDDING_MODEL must be {MODEL_EXPECTED}")
        if self.dimension != DIMENSION_EXPECTED:
            raise QueryEmbeddingError(f"GEMINI_EMBEDDING_DIMENSION must be {DIMENSION_EXPECTED}")
        self.client = client or genai.Client(
            api_key=self.api_key,
            http_options=types.HttpOptions(
                timeout=20000, retry_options=types.HttpRetryOptions(attempts=1)
            ),
        )

    def embed_query(self, query: str) -> list[float]:
        formatted = format_query_for_embedding(query)
        delay = 2.0
        for attempt in range(1, self.max_retries + 1):
            try:
                response = self.client.models.embed_content(
                    model=self.model,
                    contents=formatted,
                    config=types.EmbedContentConfig(
                        task_type="RETRIEVAL_QUERY",
                        output_dimensionality=self.dimension,
                    ),
                )
                vectors = extract_embeddings(response)
                if len(vectors) != 1:
                    raise QueryEmbeddingError(f"Expected one query embedding, got {len(vectors)}")
                return validate_embedding_vector(vectors[0], self.dimension)
            except Exception:
                if attempt == self.max_retries:
                    raise
                time.sleep(delay + random.uniform(0, 0.5))
                delay *= 2

        raise QueryEmbeddingError("Query embedding failed")
