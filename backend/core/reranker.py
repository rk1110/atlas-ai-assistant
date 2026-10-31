"""The reranker gateway: the one place that runs the cross-encoder model.

Same shape as the embedding gateway (core/embeddings.py): callers ask for scores and never
touch sentence-transformers, so swapping the model is a config change (config/rag.yaml,
`reranker.model`). See retrieval/reranking.py for why a cross-encoder improves ranking.
"""

import logging
import threading
from abc import ABC, abstractmethod
from functools import lru_cache
from typing import TYPE_CHECKING

import anyio

from core.rag_config import RerankerConfig, get_rag_config

if TYPE_CHECKING:
    from sentence_transformers import CrossEncoder

logger = logging.getLogger(__name__)


class Reranker(ABC):
    @abstractmethod
    async def score(self, query: str, texts: list[str]) -> list[float]:
        """Relevance of each text to the query, 0..1 (higher = more relevant), same order."""


class CrossEncoderReranker(Reranker):
    def __init__(self, config: RerankerConfig):
        self._config = config
        self._model: CrossEncoder | None = None
        self._lock = threading.Lock()

    @property
    def model(self) -> "CrossEncoder":
        """Loaded on first use (like the embedder), so startup stays instant."""
        with self._lock:
            if self._model is None:
                from sentence_transformers import CrossEncoder

                logger.info("loading reranker model %s", self._config.model)
                self._model = CrossEncoder(
                    self._config.model, device="cpu", max_length=self._config.max_length
                )
        return self._model

    async def score(self, query: str, texts: list[str]) -> list[float]:
        if not texts:
            return []
        # CPU-heavy and synchronous: a worker thread keeps other requests streaming.
        return await anyio.to_thread.run_sync(self._predict, query, texts)

    def _predict(self, query: str, texts: list[str]) -> list[float]:
        import torch

        scores = self.model.predict(
            [(query, text) for text in texts],
            batch_size=self._config.batch_size,
            # The model outputs a raw logit (any real number). A sigmoid squashes it to 0..1,
            # so scores read like probabilities and compare across questions.
            activation_fn=torch.nn.Sigmoid(),
            show_progress_bar=False,
        )
        return [float(s) for s in scores]


@lru_cache
def get_reranker() -> Reranker:
    return CrossEncoderReranker(get_rag_config().reranker)
