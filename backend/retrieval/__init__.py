"""Retriever implementations (see core/interfaces/retriever.py for the contract).

    vector         VectorRetriever                          same meaning
    keyword        KeywordRetriever                         same words (BM25)
    hybrid         HybridRetriever(vector, keyword)         both, fused with RRF
    hybrid_rerank  RerankingRetriever(hybrid, cross-encoder) both, then precisely re-ordered
    graph          GraphRetriever                           facts from the knowledge graph
    hybrid_graph   HybridRetriever(vector, keyword, graph)  all three, fused with RRF

The chat uses `retrieval.strategy` from config/rag.yaml. Evals and the Knowledge Base's
retrieval tester can ask for any strategy by name, which is how they get compared.
"""

from functools import cache
from typing import get_args

from core.db import get_session_factory
from core.embeddings import get_embedder
from core.interfaces.retriever import Retriever
from core.rag_config import RetrievalStrategy, get_rag_config
from core.reranker import get_reranker
from graph.store import get_graph_store
from retrieval.graph import GraphRetriever
from retrieval.hybrid import HybridRetriever
from retrieval.keyword import KeywordRetriever
from retrieval.reranking import RerankingRetriever
from retrieval.vector import VectorRetriever

STRATEGIES: tuple[str, ...] = get_args(RetrievalStrategy)


@cache
def build_retriever(strategy: RetrievalStrategy) -> Retriever:
    """One retriever per strategy, built from the shared embedder, reranker and DB pool."""
    rag = get_rag_config()
    config = rag.retrieval
    match strategy:
        case "vector":
            return VectorRetriever(get_embedder(), get_session_factory())
        case "keyword":
            return KeywordRetriever(get_session_factory())
        case "hybrid":
            return HybridRetriever(
                [build_retriever("vector"), build_retriever("keyword")],
                candidates=config.candidates,
                rrf_k=config.rrf_k,
            )
        case "graph":
            return GraphRetriever(
                get_graph_store(), max_facts=rag.graph.max_facts, hops=rag.graph.hops
            )
        case "hybrid_graph":
            return HybridRetriever(
                [build_retriever("vector"), build_retriever("keyword"), build_retriever("graph")],
                candidates=config.candidates,
                rrf_k=config.rrf_k,
                name="hybrid_graph",
            )
        case "hybrid_rerank":
            return RerankingRetriever(
                build_retriever("hybrid"), get_reranker(), candidates=rag.reranker.candidates
            )


def get_retriever() -> Retriever:
    """The retriever the chat uses: `retrieval.strategy` in config/rag.yaml."""
    return build_retriever(get_rag_config().retrieval.strategy)


__all__ = [
    "STRATEGIES",
    "GraphRetriever",
    "HybridRetriever",
    "KeywordRetriever",
    "RerankingRetriever",
    "VectorRetriever",
    "build_retriever",
    "get_retriever",
]
