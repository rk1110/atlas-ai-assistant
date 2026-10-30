"""Retriever implementations (see core/interfaces/retriever.py for the contract)."""

from functools import lru_cache

from core.db import get_session_factory
from core.embeddings import get_embedder
from core.interfaces.retriever import Retriever
from retrieval.vector import VectorRetriever


@lru_cache
def get_retriever() -> Retriever:
    """The retriever the chat uses. Phase 3 picks hybrid/reranking here, from config."""
    return VectorRetriever(get_embedder(), get_session_factory())


__all__ = ["VectorRetriever", "get_retriever"]
