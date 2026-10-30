"""The embedding gateway: the one place that turns text into vectors.

An embedding is a list of numbers (here 384) that represents what a text *means*. Texts with
similar meaning get vectors that point in similar directions, so "How many vacation days do I
get?" lands close to the paragraph about "22 paid vacation days" even though they share few
words. Retrieval is then just "find the stored vectors closest to the question's vector".

Same idea as the LLM gateway (core/llm.py): callers ask for embeddings and never touch the
library, so swapping the model (or moving to an API embedding model later) changes config and
this file only.

Why a local model (sentence-transformers + BGE): free, works offline, and fast enough on CPU
for a few thousand chunks. The model (~130 MB) downloads from Hugging Face on first use and is
cached (a Docker volume keeps it between container restarts).
"""

import logging
import threading
from abc import ABC, abstractmethod
from functools import lru_cache
from typing import TYPE_CHECKING

import anyio

from core.rag_config import EmbeddingConfig, get_rag_config

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)


class Embedder(ABC):
    """What the rest of Atlas needs from an embedding model. Tests use a fake implementation."""

    dimensions: int

    @abstractmethod
    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Vectors for passages being stored (ingestion)."""

    @abstractmethod
    async def embed_query(self, text: str) -> list[float]:
        """Vector for a search query. May differ from a passage embedding (see query_prefix)."""

    @abstractmethod
    def count_tokens(self, text: str) -> int:
        """Length in the model's own tokens: what chunk sizes are measured in."""


class SentenceTransformerEmbedder(Embedder):
    def __init__(self, config: EmbeddingConfig):
        self._config = config
        self.dimensions = config.dimensions
        self._model: SentenceTransformer | None = None
        self._lock = threading.Lock()

    @property
    def model(self) -> "SentenceTransformer":
        """Loaded on first use, not at import: the API starts instantly, and only code that
        actually embeds pays the few seconds it takes to load the model."""
        with self._lock:  # two threads asking at once must not load it twice
            if self._model is None:
                from sentence_transformers import SentenceTransformer  # heavy import (torch)

                logger.info("loading embedding model %s", self._config.model)
                model = SentenceTransformer(self._config.model, device="cpu")
                actual = model.get_embedding_dimension()
                if actual != self._config.dimensions:
                    raise ValueError(
                        f"{self._config.model} makes {actual}-number vectors, but rag.yaml says "
                        f"{self._config.dimensions} (and the database column must match)"
                    )
                self._model = model
        return self._model

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        # Encoding is CPU-heavy, synchronous work: run it in a worker thread so the event
        # loop keeps serving other requests (streaming chats) meanwhile.
        return await anyio.to_thread.run_sync(self._encode, texts)

    async def embed_query(self, text: str) -> list[float]:
        vectors = await anyio.to_thread.run_sync(self._encode, [self._config.query_prefix + text])
        return vectors[0]

    def count_tokens(self, text: str) -> int:
        # verbose=False: counting a text longer than the model's 512-token limit is exactly
        # what the chunker needs to do (to decide to split it), so skip the length warning.
        tokens = self.model.tokenizer(text, add_special_tokens=False, verbose=False)
        return len(tokens["input_ids"])

    def _encode(self, texts: list[str]) -> list[list[float]]:
        vectors = self.model.encode(
            texts,
            batch_size=self._config.batch_size,
            # Unit-length vectors: cosine similarity becomes a plain dot product, and every
            # score lands in [-1, 1], comparable across queries.
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        return vectors.tolist()


@lru_cache
def get_embedder() -> Embedder:
    return SentenceTransformerEmbedder(get_rag_config().embedding)
