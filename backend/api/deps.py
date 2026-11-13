"""FastAPI dependency providers: the objects routes receive via `Depends(...)`.

Why dependency injection instead of importing globals: tests can swap any of these with
`app.dependency_overrides[get_gateway] = lambda: FakeGateway()`, so route tests never call a
real LLM (fast, free, deterministic). That's exactly how the step 9 chat tests will work.
"""

from collections.abc import Callable
from functools import lru_cache
from typing import Annotated

from fastapi import Depends
from langgraph.checkpoint.base import BaseCheckpointSaver
from sqlalchemy.ext.asyncio import AsyncSession

from agents.assistant import AssistantAgent
from agents.checkpoints import get_checkpointer
from agents.graph import build_graph
from agents.runner import AgentRunner
from agents.team import build_team_graph
from agents.team_agents import PlannerAgent, VerifierAgent
from core.agent_config import get_agent_config
from core.config import Settings, get_settings
from core.db import get_session, get_session_factory
from core.embeddings import get_embedder
from core.interfaces.retriever import Retriever
from core.interfaces.tool import Tool
from core.llm import LLMGateway
from core.memory_config import get_memory_config
from core.model_catalog import ModelCatalog
from core.multimodal_config import get_multimodal_config
from core.prompts import PromptRegistry
from core.rag_config import RagConfig, get_rag_config
from core.tracing import Tracer, get_tracer
from graph.store import GraphStore, get_graph_store
from ingestion.pipeline import IngestionPipeline
from ingestion.sources.uploads import UploadSource
from ingestion.vision import VisionReader
from retrieval import build_retriever, get_retriever
from services.chat_service import ChatService
from services.embedding_map import EmbeddingMapService
from services.intent import IntentClassifier
from services.memory import ConversationSummarizer, LongTermMemory
from services.query_rewriter import QueryRewriter
from simulated.store import SimulatedJira, SimulatedSlack
from tools import get_tools


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
        get_classifier(),
        get_agent_runner(),
        get_agent_config(),
        get_long_term_memory(),
        get_summarizer(),
        get_memory_config(),
        catalog=get_catalog(),
        multimodal=get_multimodal_config(),
    )


@lru_cache
def get_long_term_memory() -> LongTermMemory:
    """Facts about the user (Phase 4), extracted and recalled with the cheap model + BGE."""
    return LongTermMemory(
        get_gateway(),
        get_prompts(),
        get_embedder(),
        get_session_factory(),
        get_catalog().defaults.cheap,
        get_memory_config().long_term,
    )


@lru_cache
def get_summarizer() -> ConversationSummarizer:
    return ConversationSummarizer(get_gateway(), get_prompts(), get_catalog().defaults.cheap)


@lru_cache
def get_agent_runner() -> AgentRunner:
    """The agent for action requests: the Phase 5 team, or the Phase 4 single agent
    (`mode` in config/agent.yaml). Built on first use, after main.py's startup has opened the
    Postgres checkpointer, so paused runs survive restarts."""
    return build_agent_runner(get_agent_config().mode, list(get_tools()), get_checkpointer())


def build_agent_runner(
    mode: str, tools: list[Tool], checkpointer: BaseCheckpointSaver
) -> AgentRunner:
    gateway, prompts, settings = get_gateway(), get_prompts(), get_settings()
    config = get_agent_config()
    if mode == "single":
        assistant = AssistantAgent(gateway, prompts, settings, tools)
        return AgentRunner(build_graph(assistant, tools, checkpointer, config.max_model_calls))
    research_tools = [t for t in tools if not t.requires_approval and t.name != "calculator"]
    org_chart = [t for t in tools if t.name == "query_org_chart"]
    action_tools = [*org_chart, *(t for t in tools if t.requires_approval)]
    graph = build_team_graph(
        PlannerAgent(gateway, prompts, settings),
        AssistantAgent(gateway, prompts, settings, research_tools, name="researcher",
                       prompt_name="team_researcher", title="Researching"),
        AssistantAgent(gateway, prompts, settings, action_tools, name="action",
                       prompt_name="team_action", title="Acting"),
        VerifierAgent(gateway, prompts),
        research_tools,
        action_tools,
        checkpointer,
        config.team_max_model_calls,
    )  # fmt: skip
    return AgentRunner(graph)


@lru_cache
def get_jira() -> SimulatedJira:
    return SimulatedJira(get_session_factory())


@lru_cache
def get_slack() -> SimulatedSlack:
    return SimulatedSlack(get_session_factory())


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
    return IngestionPipeline(
        get_embedder(), get_rag_config().chunking, get_session_factory(), get_vision_reader()
    )


def get_vision_reader() -> VisionReader | None:
    """Reads scanned PDFs and images at import time; None if no vision model is configured
    (then scans fail with "no text found", as before Phase 6)."""
    vision = get_catalog().defaults.vision
    if vision is None:
        return None
    config = get_multimodal_config().ingestion
    return VisionReader(get_gateway(), get_prompts(), get_tracer(), vision, config)


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
MemoryDep = Annotated[LongTermMemory, Depends(get_long_term_memory)]
JiraDep = Annotated[SimulatedJira, Depends(get_jira)]
SlackDep = Annotated[SimulatedSlack, Depends(get_slack)]
GraphStoreDep = Annotated[GraphStore | None, Depends(get_graph_store)]
EmbeddingMapDep = Annotated[EmbeddingMapService, Depends(get_embedding_map)]
IngestionPipelineDep = Annotated[IngestionPipeline, Depends(get_ingestion_pipeline)]
UploadSourceDep = Annotated[UploadSource, Depends(get_upload_source)]
