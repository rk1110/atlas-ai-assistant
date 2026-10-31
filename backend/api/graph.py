"""The Knowledge Graph API (Phase 3): the graph for the explorer page, and graph search.

    GET /api/graph               every entity and relation (the Acme graph is small)
    GET /api/graph/search?q=...  which entities a question names, and the facts around them

503 when Neo4j isn't configured or reachable: the page then explains how to start it.
"""

import logging

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel

from api.deps import GraphStoreDep, RagConfigDep
from graph.store import EntityMatch, Fact, GraphSnapshot, GraphStore
from retrieval.graph import SEED_SCORE_RATIO, SEED_TYPES_SKIPPED

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/graph", tags=["graph"])


class GraphSearch(BaseModel):
    entities: list[EntityMatch]  # what the question matched, best first
    seeds: list[str]  # the entity keys the walk started from
    facts: list[Fact]


def _require(store: GraphStore | None) -> GraphStore:
    if store is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Graph database not configured")
    return store


def _unreachable() -> HTTPException:
    logger.warning("graph database call failed", exc_info=True)
    return HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Graph database unreachable")


@router.get("")
async def graph(store: GraphStoreDep) -> GraphSnapshot:
    try:
        return await _require(store).snapshot()
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "Graph database unreachable"
        ) from exc


@router.get("/search")
async def graph_search(
    store: GraphStoreDep, config: RagConfigDep, q: str = Query(min_length=2, max_length=500)
) -> GraphSearch:
    """The same seed selection and walk as the GraphRetriever, but showing every step."""
    graph_store = _require(store)
    try:
        entities = await graph_store.find_entities(q, limit=5)
        seeds = [
            e.key for e in entities
            if e.type not in SEED_TYPES_SKIPPED and e.score >= SEED_SCORE_RATIO * entities[0].score
        ][:3]  # fmt: skip
        facts = await graph_store.facts_around(
            seeds, hops=config.graph.hops, limit=config.graph.max_facts
        )
    except Exception as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "Graph database unreachable"
        ) from exc
    return GraphSearch(entities=entities, seeds=seeds, facts=facts)
