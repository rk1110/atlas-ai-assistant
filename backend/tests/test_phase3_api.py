"""Phase 3 endpoints: strategy choice in search, embedding map, graph API, analytics."""

import uuid

import numpy as np
from httpx import AsyncClient
from sqlalchemy import func

from api.deps import get_embedding_map, get_graph_store, get_retriever_builder
from core.db import get_session_factory
from main import app
from models import EvalRun
from services.embedding_map import EmbeddingMapService, MapPoint, project
from tests.conftest import FakeRetriever, make_chunk
from tests.test_graph import FACTS, MATCHES, FakeGraphStore
from tests.test_keyword_hybrid_rerank import ScriptedRetriever
from tests.test_retrieval import ingest


async def test_search_uses_the_requested_strategy(client: AsyncClient):
    asked: list[str] = []

    def build(strategy: str):
        asked.append(strategy)
        return ScriptedRetriever(strategy, [make_chunk(1, "BM25 found me")])

    app.dependency_overrides[get_retriever_builder] = lambda: build
    response = await client.get("/api/knowledge/search", params={"q": "mvc", "strategy": "keyword"})
    body = response.json()
    assert asked == ["keyword"] and body["retriever"] == "keyword"
    assert body["chunks"][0]["text"] == "BM25 found me" and body["latency_ms"] >= 0

    default = (await client.get("/api/knowledge/search", params={"q": "mvc"})).json()
    assert default["retriever"] != "keyword"  # no strategy = the configured retriever
    bad = await client.get("/api/knowledge/search", params={"q": "mvc", "strategy": "magic"})
    assert bad.status_code == 422


async def test_config_lists_strategies(client: AsyncClient):
    config = (await client.get("/api/knowledge/config")).json()
    assert "hybrid_graph" in config["strategies"]
    assert config["default_strategy"] in config["strategies"]


def test_projection_keeps_neighbours_together_and_scales_to_unit_box():
    rng = np.random.default_rng(0)
    centres = rng.normal(size=(2, 16))
    vectors = np.vstack([c + 0.01 * rng.normal(size=(20, 16)) for c in centres]).astype("float32")
    points = project(vectors)
    assert points.shape == (40, 2) and np.abs(points).max() <= 1.0 + 1e-6
    first, second = points[:20].mean(axis=0), points[20:].mean(axis=0)
    spread = np.linalg.norm(points[:20] - first, axis=1).mean()
    assert np.linalg.norm(first - second) > 3 * spread  # two clusters stay two clusters


async def test_embedding_map_endpoint_returns_a_point_per_chunk(
    client: AsyncClient, tmp_path, fake_embedder
):
    docs = {f"d{n}.md": f"policy number {n} about topic {n % 2}" for n in range(6)}
    await ingest(tmp_path / "docs", "acme", docs, fake_embedder)
    app.dependency_overrides[get_embedding_map] = lambda: EmbeddingMapService(get_session_factory())
    body = (await client.get("/api/knowledge/map")).json()
    assert body["method"] == "t-SNE" and len(body["points"]) == 6
    point = MapPoint(**body["points"][0])
    assert point.source == "acme" and point.heading == "Policy"


async def test_graph_endpoints(client: AsyncClient):
    app.dependency_overrides[get_graph_store] = lambda: FakeGraphStore(MATCHES, FACTS)
    search = (await client.get("/api/graph/search", params={"q": "expense policy"})).json()
    assert search["seeds"] == ["expense policy"] and len(search["facts"]) == 3
    assert (await client.get("/api/graph")).json() == {"nodes": [], "edges": []}

    app.dependency_overrides[get_graph_store] = lambda: None
    assert (await client.get("/api/graph")).status_code == 503
    app.dependency_overrides[get_graph_store] = lambda: FakeGraphStore([], [], fail=True)
    assert (await client.get("/api/graph/search", params={"q": "x y"})).status_code == 503


async def test_analytics_summarises_eval_runs_and_daily_usage(
    client: AsyncClient, fake_retriever: FakeRetriever
):
    await client.post("/api/chat", json={"conversation_id": str(uuid.uuid4()), "message": "hi"})
    async with get_session_factory()() as session:
        run = EvalRun(model_id="m", golden_set_version=2, hit_rate=0.9, finished_at=func.now())
        session.add_all([run, EvalRun(model_id="unfinished", golden_set_version=2)])
        await session.commit()

    body = (await client.get("/api/analytics")).json()
    assert body["totals"]["answers"] == 1 and body["totals"]["conversations"] == 1
    assert body["usage"][0]["answers"] == 1 and body["usage"][0]["input_tokens"] == 10
    assert [r["hit_rate"] for r in body["eval_runs"]] == [0.9]  # unfinished runs are left out
