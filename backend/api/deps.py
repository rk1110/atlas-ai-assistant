"""FastAPI dependency providers: the objects routes receive via `Depends(...)`.

Why dependency injection instead of importing globals: tests can swap any of these with
`app.dependency_overrides[get_gateway] = lambda: FakeGateway()`, so route tests never call a
real LLM (fast, free, deterministic). That's exactly how the step 9 chat tests will work.
"""

from collections.abc import Callable
from functools import lru_cache
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import Settings, get_settings
from core.db import get_session, get_session_factory
from core.embeddings import get_embedder
from core.interfaces.retriever import Retriever
from core.llm import LLMGateway
from core.model_catalog import ModelCatalog
from core.prompts import PromptRegistry
from core.rag_config import RagConfig, get_rag_config
from core.tracing import Tracer, get_tracer
from graph.store import GraphStore, get_graph_store
from ingestion.pipeline import IngestionPipeline
from ingestion.sources.uploads import UploadSource
from retrieval import build_retriever, get_retriever
from services.chat_service import ChatService
from services.embedding_map import EmbeddingMapService
from services.intent import IntentClassifier
from services.query_rewriter import QueryRewriter


@lru_cache
def get_catalog() -> ModelCatalog:
    settings = get_settings()
    return ModelCatalog.from_yaml(settings.models_file, settings)


@lru_cache
def get_gateway() -> LLMGateway:
    return LLMGateway(get_catalog(), get_tracer())


@lru_cache
def get_prompts() -> PromptRegistry:
    return PromptRegistry.from_directory(get_settings().prompts_dir)


@lru_cache
def get_chat_service() -> ChatService:
    return make_chat_service()


def make_chat_service(retriever: Retriever | None = None, *, rewrite: bool = True) -> ChatService:
    """Overrides for the eval runner: `retriever` replaces config/rag.yaml's strategy
    (--retriever), `rewrite=False` turns query rewriting off (--no-rewrite)."""
    return ChatService(
        get_gateway(),
        get_prompts(),
        get_settings(),
        get_session_factory(),
        get_tracer(),
        retriever or get_retriever(),
        get_rag_config().retrieval.top_k,
        get_query_rewriter() if rewrite else None,
    )


def get_query_rewriter() -> QueryRewriter | None:
    """None when `query_rewriting.enabled` is false in config/rag.yaml."""
    config = get_rag_config().query_rewriting
    if not config.enabled:
        return None
    return QueryRewriter(get_gateway(), get_prompts(), config.model or get_catalog().defaults.cheap)


@lru_cache
def get_classifier() -> IntentClassifier:
    return IntentClassifier(get_gateway(), get_prompts(), get_catalog())


@lru_cache
def get_ingestion_pipeline() -> IngestionPipeline:
    return IngestionPipeline(get_embedder(), get_rag_config().chunking, get_session_factory())


@lru_cache
def get_upload_source() -> UploadSource:
    config = get_rag_config()
    uploads = config.source_of_kind("uploads")
    if uploads is None:
        raise RuntimeError("config/rag.yaml has no source of kind 'uploads'")
    return UploadSource(uploads.directory, config.uploads.extensions, uploads.name)


def get_retriever_builder() -> Callable[..., Retriever]:
    """Builds a retriever by strategy name. A dependency so tests can swap in fakes."""
    return build_retriever


@lru_cache
def get_embedding_map() -> EmbeddingMapService:
    return EmbeddingMapService(get_session_factory())


SettingsDep = Annotated[Settings, Depends(get_settings)]
CatalogDep = Annotated[ModelCatalog, Depends(get_catalog)]
GatewayDep = Annotated[LLMGateway, Depends(get_gateway)]
PromptsDep = Annotated[PromptRegistry, Depends(get_prompts)]
SessionDep = Annotated[AsyncSession, Depends(get_session)]
ChatServiceDep = Annotated[ChatService, Depends(get_chat_service)]
TracerDep = Annotated[Tracer, Depends(get_tracer)]
ClassifierDep = Annotated[IntentClassifier, Depends(get_classifier)]
RagConfigDep = Annotated[RagConfig, Depends(get_rag_config)]
RetrieverDep = Annotated[Retriever, Depends(get_retriever)]
RetrieverBuilderDep = Annotated[Callable[..., Retriever], Depends(get_retriever_builder)]
GraphStoreDep = Annotated[GraphStore | None, Depends(get_graph_store)]
EmbeddingMapDep = Annotated[EmbeddingMapService, Depends(get_embedding_map)]
IngestionPipelineDep = Annotated[IngestionPipeline, Depends(get_ingestion_pipeline)]
UploadSourceDep = Annotated[UploadSource, Depends(get_upload_source)]
